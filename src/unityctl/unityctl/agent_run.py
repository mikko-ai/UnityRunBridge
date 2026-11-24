"""Explicit one-command-at-a-time Agent trace, consumed by the read-only Watch UI."""

import argparse
import json
import os
import re
import shlex
from contextlib import contextmanager
from pathlib import Path

from unityctl.run_events import RunEvents, frame_name
from unityctl.session import create_session, format_time, update_session_status, utc_now
from unityctl.watch import read_events, select_session

_ALLOWED = {"status", "play", "stop", "snapshot", "click-at", "hierarchy", "hit-test", "gameplay"}
_READ_ONLY = {"status", "hierarchy", "hit-test"}


class AgentRunError(ValueError):
    pass


def add_parser(subparsers):
    root = subparsers.add_parser("agent-run", help="记录 Agent 直接执行的 Unity 步骤，供 watch 实时查看")
    commands = root.add_subparsers(dest="agent_action", required=True)
    start = commands.add_parser("start")
    start.add_argument("--name", required=True)
    step = commands.add_parser("step")
    step.add_argument("--session-id", required=True)
    step.add_argument("--why", required=True, help="可公开的操作目的；不要填写秘密或私有推理")
    step.add_argument("--frame", help="click-at 所使用的本次运行最新截图文件名")
    step.add_argument("--expect", help="对 CLI JSON 返回值做精确比较，例如 result=\"confirm\"")
    step.add_argument("step_args", nargs=argparse.REMAINDER)
    finish = commands.add_parser("finish")
    finish.add_argument("--session-id", required=True)


@contextmanager
def _lock(session):
    path = session / "agent-step.lock"
    try:
        path.mkdir()
    except FileExistsError as exc:
        raise AgentRunError("此记录有步骤在执行；若进程异常退出，请创建新会话，不要重放点击") from exc
    try:
        yield
    finally:
        path.rmdir()


def _expectation(text):
    if text is None:
        return None
    field, sep, raw = text.partition("=")
    if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,80}", field):
        raise AgentRunError("--expect 需要 FIELD=JSON")
    try:
        expected = json.loads(raw)
        if not (expected is None or type(expected) in {str, bool, int, float}):
            raise ValueError
        # Reject NaN and infinity which are not JSON values.
        json.dumps(expected, allow_nan=False)
        return field, expected
    except ValueError as exc:
        raise AgentRunError("--expect 只接受 JSON 标量（字符串需要引号）") from exc


def _check(result, expectation):
    field, expected = expectation
    actual = result
    found = True
    for key in field.split("."):
        if not isinstance(actual, dict) or key not in actual:
            found, actual = False, None
            break
        actual = actual[key]
    # Comparisons are typed: Python otherwise conflates booleans and numbers.
    match = found and type(expected) is type(actual) and actual == expected
    verification = {"field": field, "expected": expected, "found": found, "passed": match}
    if actual is None or type(actual) in {str, bool, int, float}:
        verification["actual"] = actual
    return verification


def run_agent(project: Path, args, parse, execute, error_payload):
    if args.agent_action == "start":
        if not args.name.strip() or len(args.name) > 100:
            raise AgentRunError("名称长度应为 1–100 个字符")
        session = create_session(project, args.name, None, "agent", "")
        (session.session_path / "artifacts").mkdir()
        update_session_status(session.session_path, "running", started_at=format_time(utc_now()))
        RunEvents(session.session_path).emit("run-started", {
            "kind": "agent", "name": args.name, "status": "running",
        })
        return {"ok": True, "sessionId": session.session_id, "sessionPath": str(session.session_path)}

    session = select_session(project, args.session_id)
    if session is None:
        raise AgentRunError("找不到 Agent 会话")
    with _lock(session):
        records = read_events(session)
        if not records or records[0].get("kind") != "agent" or records[-1].get("type") == "run-finished":
            raise AgentRunError("只可追加到未结束的 Agent 会话")
        events = RunEvents(session)
        events.sequence = records[-1]["sequence"]
        if args.agent_action == "finish":
            finished = [row for row in records if row.get("type") == "step-finished"]
            # A series of successful commands is not by itself a verified result.
            verified = any(row.get("verification", {}).get("passed") is True for row in finished)
            failed = any(row["status"] != "passed" for row in finished)
            last_started = records[-1].get("type") == "step-started"
            status = "failed" if failed or last_started else ("passed" if verified else "unverified")
            events.emit("run-finished", {"status": status})
            update_session_status(session, "failed" if status == "failed" else "stopped",
                                  ended_at=format_time(utc_now()))
            return {"ok": status == "passed", "status": status, "sessionId": session.name}

        argv = args.step_args[1:] if args.step_args[:1] == ["--"] else args.step_args
        if not argv or argv[0] not in _ALLOWED or any(x.split("=")[0] in {"--project", "-h", "--help"} for x in argv):
            raise AgentRunError("步骤只允许运行本工程白名单中的 unityctl 命令，不接受 shell 或 --project")
        if not args.why.strip() or len(args.why) > 240 or sum(map(len, argv)) > 1000:
            raise AgentRunError("操作理由限 1–240 字，命令参数总长限 1000 字")
        action = argv[0]
        expectation = _expectation(args.expect)
        if action == "gameplay" and (len(argv) != 3 or argv[1] != "invoke"):
            raise AgentRunError("监看只支持无参数的 gameplay invoke 探针，避免记录敏感参数")
        if action == "play" and any(token.split("=")[0] in {"--session", "--task"} for token in argv):
            raise AgentRunError("Agent 会话的 play 步骤不能再传 --session 或 --task")
        if action == "snapshot":
            if any(token.split("=")[0] in {"--target-directory", "--reason", "--annotate"} for token in argv):
                raise AgentRunError("snapshot 的文件目录和截图策略由当前 Agent 会话管理")
            argv = [*argv, "--target-directory", str(session / "artifacts")]
        try:
            nested = parse(["--project", str(project), *argv])
        except SystemExit as exc:
            raise AgentRunError("子命令参数无效") from exc
        nested.project_path = project
        if action == "snapshot" and (nested.reason != "agent" or nested.annotate):
            raise AgentRunError("Agent 截图必须遵守独立截图权限，不能改用其他 reason")
        if action == "play" and (nested.session_name or nested.task):
            raise AgentRunError("Agent 会话的 play 步骤不能再传 --session 或 --task")

        frame = None
        marker = None
        if action == "click-at":
            shot = None
            for row in reversed(records):
                if row.get("type") != "step-finished" or row.get("action") in _READ_ONLY:
                    continue
                if row.get("action") == "snapshot" and row.get("status") == "passed":
                    shot = row
                break
            if not shot or not args.frame or args.frame != shot.get("frame"):
                raise AgentRunError("click-at 需要 --frame 指定本会话最新截图；操作后请重新截图")
            if shot.get("imageSize") != [nested.image_width, nested.image_height] or shot.get("referenceSize") != [
                nested.reference_width, nested.reference_height
            ]:
                raise AgentRunError("点击尺寸必须与选定截图一致")
            frame = frame_name(session, {"path": str(session / "artifacts" / args.frame)})
            if not frame:
                raise AgentRunError("该帧已不存在，请重新截图")
            if 0 <= nested.x < nested.image_width and 0 <= nested.y < nested.image_height:
                marker = {"x": nested.x / nested.image_width, "y": nested.y / nested.image_height}
        elif args.frame:
            raise AgentRunError("--frame 只用于 click-at")

        index = sum(row.get("type") == "step-started" for row in records)
        step = {"stepIndex": index, "action": action, "id": f"agent-{index + 1}", "why": args.why,
                "command": shlex.join(["unityctl", *argv])}
        events.emit("step-started", {**step, "status": "running", "stepPid": os.getpid()})
        try:
            result = execute(nested)
        except Exception as exc:
            result = error_payload(exc)
        except KeyboardInterrupt:
            result = {"ok": False, "code": "agent_step_interrupted", "message": "步骤中断；检查现场，不自动重试"}
        if action == "snapshot" and result.get("ok") is True:
            if result.get("agentImageAccess") != "allow":
                result = {"ok": False, "code": "agent_image_denied", "message": "项目未允许 Agent 读取截图"}
            else:
                image = frame_name(session, result)
                if image:
                    step["frame"] = image
                    step["imageSize"] = [result.get("width"), result.get("height")]
                    reference = result.get("referenceScreen") or {}
                    step["referenceSize"] = [reference.get("width"), reference.get("height")]
        if action == "click-at" and result.get("ok") is True and frame and marker:
            step.update(frame=frame, marker=marker)
        passed = result.get("ok") is True
        if expectation and passed:
            verification = _check(result, expectation)
            step["verification"] = verification
            passed = verification["passed"]
        if isinstance(result.get("clicked"), str):
            step["clicked"] = result["clicked"]
        step["code"] = ("agent_expectation_failed" if result.get("ok") is True and not passed
                        else result.get("code") or ("ok" if passed else "failed"))
        events.emit("step-finished", {**step, "status": "passed" if passed else "failed"})
        return {**result, "ok": passed, "code": step["code"], "sessionId": session.name,
                **({"verification": step["verification"]} if "verification" in step else {})}
