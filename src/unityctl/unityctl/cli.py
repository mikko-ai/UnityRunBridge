import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from unityctl import __version__
from unityctl.client import BridgeClient, BridgeClientError
from unityctl.config import (
    ConfigError,
    UNITY_AGENT_BRIDGE_PACKAGE_ID,
    find_latest_session_path,
    find_unity_project_root,
    init_project_config,
    is_bridge_package_installed,
    read_json,
    resolve_effective_config,
    validate_project_config,
    write_json,
)
from unityctl.convergence import (
    ConvergenceEditorExited,
    ConvergenceFailed,
    ConvergenceTimeout,
    parse_utc_timestamp,
    poll_until,
)
from unityctl.discovery import (
    BridgeInfo,
    DiscoveryError,
    bridge_info_path,
    discover,
    is_pid_alive,
    read_bridge_info,
)
from unityctl.editor import start_editor
from unityctl.session import (
    create_session,
    format_time,
    mark_session_failed,
    update_session_status,
    utc_now,
)
from unityctl.summary import build_summary, classify_log, load_log_rules, read_jsonl, write_summary


class CliError(RuntimeError):
    def __init__(self, code: str, message: str, extra: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.extra = extra or {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="unityctl")
    parser.add_argument("--version", action="version", version=f"unityctl {__version__}")
    parser.add_argument("--project", dest="global_project_path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init")
    init.add_argument("--unity", dest="unity_path")
    init.add_argument("--unity-version")
    init.add_argument("--port", dest="preferred_port", type=int, default=17890)
    init.add_argument("--scene", dest="default_scene")
    init.add_argument("--yes", action="store_true")
    init.add_argument("--force", action="store_true")

    config = subparsers.add_parser("config")
    config.add_argument("--project", dest="project_path")
    config_subparsers = config.add_subparsers(dest="config_command", required=True)
    config_subparsers.add_parser("show")
    config_subparsers.add_parser("validate")
    set_local = config_subparsers.add_parser("set-local")
    set_local.add_argument("key")
    set_local.add_argument("value")

    status = subparsers.add_parser("status")
    status.add_argument("--project", dest="project_path")

    play = subparsers.add_parser("play")
    play.add_argument("--project", dest="project_path")
    play.add_argument("--session", dest="session_name")
    play.add_argument("--scene", dest="scene_path")
    play.add_argument("--task", default="")
    play.add_argument("--trigger", default="agent")
    play.add_argument("--timeout", type=float, default=None)
    play.add_argument("--no-wait", action="store_true")

    stop = subparsers.add_parser("stop")
    stop.add_argument("--project", dest="project_path")
    stop.add_argument("--session-path")
    stop.add_argument("--latest", action="store_true")
    stop.add_argument("--timeout", type=float, default=None)
    stop.add_argument("--no-wait", action="store_true")

    pause = subparsers.add_parser("pause")
    pause.add_argument("--project", dest="project_path")

    resume = subparsers.add_parser("resume")
    resume.add_argument("--project", dest="project_path")

    open_scene = subparsers.add_parser("open-scene")
    open_scene.add_argument("--project", dest="project_path")
    open_scene.add_argument("scene_path")

    start = subparsers.add_parser("start")
    start.add_argument("--project", dest="project_path")
    start.add_argument("--unity", dest="unity_path")
    start.add_argument("--log-file")
    start.add_argument("--no-wait", action="store_true")

    logs = subparsers.add_parser("logs")
    logs.add_argument("--project", dest="project_path")
    logs.add_argument("--session-path")
    logs.add_argument("--latest", action="store_true")
    logs.add_argument("--limit", type=int, default=100)

    errors = subparsers.add_parser("errors")
    errors.add_argument("--project", dest="project_path")
    errors.add_argument("--session-path")
    errors.add_argument("--latest", action="store_true")

    summary = subparsers.add_parser("summary")
    summary.add_argument("--project", dest="project_path")
    summary.add_argument("--session-path")
    summary.add_argument("--latest", action="store_true")

    refresh = subparsers.add_parser("refresh")
    refresh.add_argument("--project", dest="project_path")
    refresh.add_argument("--timeout", type=float, default=None)

    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--project", dest="project_path")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.project_path = getattr(args, "project_path", None) or args.global_project_path

    try:
        payload = dispatch(args)
        print_json(payload)
        return 0 if payload.get("ok", True) else 1
    except (CliError, BridgeClientError, DiscoveryError, ConfigError, ValueError) as exc:
        payload = {"ok": False, "code": _error_code(exc), "error": str(exc)}
        if isinstance(exc, CliError):
            payload.update(exc.extra)
        print_json(payload, stream=sys.stderr)
        return 1


def dispatch(args: argparse.Namespace) -> dict[str, Any]:
    handlers = {
        "init": cmd_init,
        "config": cmd_config,
        "status": cmd_status,
        "play": cmd_play,
        "stop": cmd_stop,
        "pause": cmd_pause,
        "resume": cmd_resume,
        "open-scene": cmd_open_scene,
        "start": cmd_start,
        "logs": cmd_logs,
        "errors": cmd_errors,
        "summary": cmd_summary,
        "refresh": cmd_refresh,
        "doctor": cmd_doctor,
    }
    handler = handlers.get(args.command)
    if handler is None:
        raise CliError("not_found", f"unsupported command: {args.command}")
    return handler(args)


def cmd_init(args: argparse.Namespace) -> dict[str, Any]:
    project = find_unity_project_root(args.project_path or Path.cwd())
    if not args.yes:
        confirm_init(project, force=args.force)
    result = init_project_config(
        project_path=project,
        unity_path=args.unity_path,
        unity_version=args.unity_version,
        preferred_port=args.preferred_port,
        default_scene=args.default_scene,
        force=args.force,
    )
    return {
        "ok": True,
        "code": "ok",
        "projectPath": str(result.project_path),
        "configPath": str(result.config_path),
        "localConfigPath": str(result.local_config_path),
        "preferredPort": result.preferred_port,
        "packageInstalled": result.package_installed,
        "alreadyInitialized": bool(result.kept_paths),
        "createdPaths": [str(path) for path in result.created_paths],
        "keptPaths": [str(path) for path in result.kept_paths],
        "updatedIgnore": result.updated_ignore,
        "nextSteps": [
            "Edit .unity-agent/config.local.json and set unityExecutablePath",
            "Run unityctl config validate",
            "Run unityctl start",
        ],
    }


def cmd_config(args: argparse.Namespace) -> dict[str, Any]:
    if args.config_command == "validate":
        project = find_unity_project_root(args.project_path or Path.cwd())
        result = validate_project_config(project)
        return {
            "ok": result.ok,
            "code": "ok" if result.ok else "invalid_request",
            "projectPath": str(result.project_path),
            "errors": [
                {"field": issue.field, "message": issue.message} for issue in result.errors
            ],
            "warnings": [
                {"field": issue.field, "message": issue.message} for issue in result.warnings
            ],
        }

    effective = resolve_effective_config(project_path=args.project_path)
    if args.config_command == "show":
        return {
            "ok": True,
            "code": "ok",
            "projectPath": str(effective.project_path),
            "preferredPort": effective.preferred_port,
            "unityVersion": effective.unity_version,
            "unityExecutablePath": (
                str(effective.unity_executable_path)
                if effective.unity_executable_path
                else None
            ),
            "defaultScene": effective.default_scene,
            "timeouts": {
                "playSeconds": effective.timeouts.play_seconds,
                "stopSeconds": effective.timeouts.stop_seconds,
                "startEditorSeconds": effective.timeouts.start_editor_seconds,
            },
            "sources": {
                "projectConfig": str(effective.project_config_path),
                "localConfig": str(effective.local_config_path),
            },
        }
    if args.config_command == "set-local":
        payload = read_json(effective.local_config_path)
        payload[args.key] = args.value
        write_json(effective.local_config_path, payload)
        return {"ok": True, "code": "ok", args.key: args.value}

    raise CliError("not_found", f"unsupported config command: {args.config_command}")


def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    project_path = args.project_path or Path.cwd()
    info = discover(project_path)
    client = BridgeClient(info.base_url, info.token)
    return client.get_status()


def cmd_pause(args: argparse.Namespace) -> dict[str, Any]:
    project_path = args.project_path or Path.cwd()
    info = discover(project_path)
    client = BridgeClient(info.base_url, info.token)
    return client.post("pause")


def cmd_resume(args: argparse.Namespace) -> dict[str, Any]:
    project_path = args.project_path or Path.cwd()
    info = discover(project_path)
    client = BridgeClient(info.base_url, info.token)
    return client.post("resume")


def cmd_open_scene(args: argparse.Namespace) -> dict[str, Any]:
    project_path = args.project_path or Path.cwd()
    info = discover(project_path)
    client = BridgeClient(info.base_url, info.token)
    return client.open_scene(args.scene_path)


def cmd_play(args: argparse.Namespace) -> dict[str, Any]:
    effective = resolve_effective_config(project_path=args.project_path)
    timeout_seconds = (
        args.timeout if args.timeout is not None else effective.timeouts.play_seconds
    )

    info = discover(effective.project_path)
    client = BridgeClient(info.base_url, info.token)
    status = client.get_status()

    # 正在编译/更新时先等它结束，再基于最新状态判断编译结果：
    # 此刻的 compilationSucceeded 是上一轮编译的陈旧值，直接快速失败会误杀正在修复的编译。
    if status.get("editorState") in {"compiling", "updating"}:
        try:
            wait_result = poll_until(
                effective.project_path,
                predicate=lambda current: current.get("editorState") not in {"compiling", "updating"},
                timeout_seconds=timeout_seconds,
                initial_info=info,
            )
        except ConvergenceTimeout as exc:
            raise CliError("timeout", "等待 Unity 编译或资源更新完成超时") from exc
        except ConvergenceEditorExited as exc:
            raise CliError("editor_exited", str(exc)) from exc
        status = wait_result.status
        info, client = _refresh_client(info, client, wait_result.info)

    if not status.get("compilationSucceeded", True):
        raise CliError(
            "compilation_failed",
            "Unity 项目当前存在编译错误，无法进入 Play Mode",
            extra={"compilationErrors": status.get("compilationErrors", [])},
        )

    session = None
    if args.session_name:
        session = create_session(
            project_path=effective.project_path,
            name=args.session_name,
            scene_path=args.scene_path,
            trigger=args.trigger,
            task=args.task,
            created_at=utc_now(),
            editor_pid=info.pid,
            unity_version=info.unity_version,
        )
        client.start_session(session.session_id, str(session.session_path))

    try:
        if args.scene_path:
            open_scene_response = client.post("open-scene", {"scenePath": args.scene_path})
            if not open_scene_response.get("ok", False):
                raise CliError(
                    open_scene_response.get("code", "invalid_request"),
                    open_scene_response.get("message", "打开场景失败"),
                )
            if not args.no_wait:
                scene_result = poll_until(
                    effective.project_path,
                    predicate=lambda current: current.get("activeScenePath") == args.scene_path,
                    timeout_seconds=timeout_seconds,
                    initial_info=info,
                )
                info, client = _refresh_client(info, client, scene_result.info)

        request_time = utc_now().replace(microsecond=0)
        play_response = client.post("play")
        if not play_response.get("ok", False) and play_response.get("code") != "already_playing":
            raise CliError(
                play_response.get("code", "internal_error"),
                play_response.get("message", "进入 Play Mode 失败"),
            )

        def predicate(current_status: dict[str, Any]) -> bool:
            editor_state = current_status.get("editorState")
            if editor_state == "playing":
                return True
            if editor_state in {"enteringPlay", "compiling", "updating"}:
                return False
            if editor_state == "idle":
                finished_at = current_status.get("compilationFinishedAt") or ""
                if (
                    finished_at
                    and not current_status.get("compilationSucceeded", True)
                    and parse_utc_timestamp(finished_at) >= request_time
                ):
                    raise ConvergenceFailed("compilation_failed", status=current_status)
            return False

        if args.no_wait:
            payload: dict[str, Any] = {
                "ok": True,
                "code": play_response.get("code", "ok"),
                "play": play_response,
            }
            if session is not None:
                update_session_status(session.session_path, "running", started_at=format_time(utc_now()))
                payload["sessionId"] = session.session_id
                payload["sessionPath"] = str(session.session_path)
            return payload

        poll_result = poll_until(
            effective.project_path,
            predicate=predicate,
            timeout_seconds=timeout_seconds,
            initial_info=info,
        )
    except CliError as exc:
        if session is not None:
            _abort_bridge_session(client)
            _finalize_failed_session(session.session_path, effective.project_path, exc.code)
        raise
    except ConvergenceFailed as exc:
        if session is not None:
            _abort_bridge_session(client)
            _finalize_failed_session(session.session_path, effective.project_path, exc.reason)
        raise CliError(
            exc.reason,
            "编译失败，无法进入 Play Mode" if exc.reason == "compilation_failed" else exc.reason,
            extra={"compilationErrors": (exc.status or {}).get("compilationErrors", [])},
        ) from exc
    except ConvergenceTimeout as exc:
        if session is not None:
            _abort_bridge_session(client)
            _finalize_failed_session(session.session_path, effective.project_path, "timeout")
        raise CliError("timeout", "等待进入 Play Mode 超时") from exc
    except ConvergenceEditorExited as exc:
        if session is not None:
            _finalize_failed_session(session.session_path, effective.project_path, "editor_exited")
        raise CliError("editor_exited", str(exc)) from exc

    payload: dict[str, Any] = {"ok": True, "code": "ok", "status": poll_result.status}
    if session is not None:
        update_session_status(session.session_path, "running", started_at=format_time(utc_now()))
        payload["sessionId"] = session.session_id
        payload["sessionPath"] = str(session.session_path)
    return payload


def cmd_stop(args: argparse.Namespace) -> dict[str, Any]:
    effective = resolve_effective_config(project_path=args.project_path)
    timeout_seconds = (
        args.timeout if args.timeout is not None else effective.timeouts.stop_seconds
    )

    info = discover(effective.project_path)
    client = BridgeClient(info.base_url, info.token)

    session_path = None
    if args.session_path or args.latest:
        session_path = resolve_session_path(args, effective.project_path)

    stop_response = client.post("stop")
    if not stop_response.get("ok", False) and stop_response.get("code") != "already_stopped":
        raise CliError(
            stop_response.get("code", "internal_error"),
            stop_response.get("message", "退出 Play Mode 失败"),
        )

    result: dict[str, Any] = {"ok": True, "code": stop_response.get("code", "ok"), "stop": stop_response}

    if not args.no_wait:
        try:
            poll_result = poll_until(
                effective.project_path,
                predicate=lambda current: current.get("editorState") == "idle",
                timeout_seconds=timeout_seconds,
                initial_info=info,
            )
            result["status"] = poll_result.status
            info, client = _refresh_client(info, client, poll_result.info)
        except ConvergenceTimeout as exc:
            if session_path is not None:
                _abort_bridge_session(client)
                _finalize_failed_session(session_path, effective.project_path, "timeout")
            raise CliError("timeout", "等待退出 Play Mode 超时") from exc
        except ConvergenceEditorExited as exc:
            if session_path is not None:
                _finalize_failed_session(session_path, effective.project_path, "editor_exited")
            raise CliError("editor_exited", str(exc)) from exc

    end_response = client.end_session()
    result["sessionEnd"] = end_response

    if session_path is not None:
        update_session_status(session_path, "stopped", ended_at=format_time(utc_now()))
        summary_payload = build_summary(session_path, load_log_rules(effective.project_path))
        write_summary(session_path, summary_payload)
        result["summary"] = summary_payload

    return result


def cmd_start(args: argparse.Namespace) -> dict[str, Any]:
    effective = resolve_effective_config(project_path=args.project_path, unity_path=args.unity_path)
    unity_executable = effective.unity_executable_path
    if unity_executable is None:
        raise CliError(
            "invalid_request",
            "Unity executable path is required. 请编辑 .unity-agent/config.local.json 或运行 "
            'unityctl config set-local unityExecutablePath "..."',
        )
    log_file = (
        Path(args.log_file).expanduser()
        if args.log_file
        else effective.project_path / ".unity-agent" / "unity-editor.log"
    )
    log_file.parent.mkdir(parents=True, exist_ok=True)
    process = start_editor(str(unity_executable), effective.project_path, log_file)

    payload: dict[str, Any] = {
        "ok": True,
        "code": "ok",
        "pid": process.pid,
        "projectPath": str(effective.project_path),
        "unityExecutablePath": str(unity_executable),
        "logFile": str(log_file),
        "bridgeReady": False,
    }

    if not args.no_wait:
        info = wait_for_handshake(
            effective.project_path,
            expected_pid=process.pid,
            timeout_seconds=effective.timeouts.start_editor_seconds,
        )
        payload["bridgeReady"] = True
        payload["bridgeUrl"] = info.base_url
        payload["unityVersion"] = info.unity_version

    return payload


def cmd_logs(args: argparse.Namespace) -> dict[str, Any]:
    project_path = _resolve_optional_project(args)
    session_path = resolve_session_path(args, project_path)
    rows = read_jsonl(session_path / "unity-console.jsonl")
    return {"ok": True, "code": "ok", "logs": rows[-args.limit :]}


def cmd_errors(args: argparse.Namespace) -> dict[str, Any]:
    project_path = _resolve_optional_project(args)
    session_path = resolve_session_path(args, project_path)
    rules = load_log_rules(project_path)
    rows = read_jsonl(session_path / "unity-console.jsonl")
    problems = []
    for row in rows:
        severity = classify_log(row, rules)
        if severity in {"problem", "blocking"}:
            problems.append({**row, "severity": severity})
    return {"ok": True, "code": "ok", "errors": problems}


def cmd_summary(args: argparse.Namespace) -> dict[str, Any]:
    project_path = _resolve_optional_project(args)
    session_path = resolve_session_path(args, project_path)
    summary_path = session_path / "summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    payload.setdefault("ok", True)
    return payload


def cmd_refresh(args: argparse.Namespace) -> dict[str, Any]:
    effective = resolve_effective_config(project_path=args.project_path)
    timeout_seconds = (
        args.timeout if args.timeout is not None else effective.timeouts.play_seconds
    )

    info = discover(effective.project_path)
    client = BridgeClient(info.base_url, info.token)
    refresh_response = client.refresh()
    if not refresh_response.get("ok", False):
        raise CliError(
            refresh_response.get("code", "internal_error"),
            refresh_response.get("message", "触发 refresh 失败"),
        )

    try:
        poll_result = poll_until(
            effective.project_path,
            predicate=lambda current: current.get("editorState") not in {"compiling", "updating"},
            timeout_seconds=timeout_seconds,
            initial_info=info,
        )
    except ConvergenceTimeout as exc:
        raise CliError("timeout", "等待编译完成超时") from exc
    except ConvergenceEditorExited as exc:
        raise CliError("editor_exited", str(exc)) from exc

    status = poll_result.status
    return {
        "ok": True,
        "code": "ok",
        "compilationSucceeded": status.get("compilationSucceeded", True),
        "compilationErrors": status.get("compilationErrors", []),
        "editorState": status.get("editorState"),
    }


def cmd_doctor(args: argparse.Namespace) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": passed, "detail": detail})

    project_path: Path | None = None
    try:
        project_path = find_unity_project_root(args.project_path or Path.cwd())
        add("project_root", True, str(project_path))
    except ConfigError as exc:
        add("project_root", False, str(exc))

    effective = None
    if project_path is not None:
        try:
            effective = resolve_effective_config(project_path=project_path)
            add("config_json", True, str(effective.project_config_path))
        except (json.JSONDecodeError, ValueError) as exc:
            add("config_json", False, str(exc))

    if effective is not None:
        executable = effective.unity_executable_path
        if executable is not None and executable.is_file():
            add("unity_executable_path", True, str(executable))
        else:
            add("unity_executable_path", False, str(executable) if executable else "未配置")

    if project_path is not None:
        add(
            "upm_package_installed",
            is_bridge_package_installed(project_path),
            UNITY_AGENT_BRIDGE_PACKAGE_ID,
        )

    info: BridgeInfo | None = None
    if project_path is not None:
        try:
            info = read_bridge_info(project_path)
            add("bridge_json", True, str(bridge_info_path(project_path)))
        except DiscoveryError as exc:
            add("bridge_json", False, str(exc))

    if info is not None:
        alive = is_pid_alive(info.pid)
        add("editor_pid_alive", alive, f"pid={info.pid}")
        if alive:
            try:
                BridgeClient(info.base_url, info.token).get_status()
                add("bridge_reachable", True, info.base_url)
            except BridgeClientError as exc:
                add("bridge_reachable", False, str(exc))
        else:
            add("bridge_reachable", False, "editor process not alive")

    overall_ok = all(check["ok"] for check in checks)
    return {"ok": overall_ok, "code": "ok" if overall_ok else "internal_error", "checks": checks}


def _refresh_client(
    info: BridgeInfo, client: Any, latest_info: BridgeInfo | None
) -> tuple[BridgeInfo, Any]:
    """收敛轮询期间若发生 domain reload，bridge.json 可能被覆盖写出新端口，
    以 poll_until 返回的最新握手信息为准重建 client。"""
    if latest_info is None or latest_info == info:
        return info, client
    return latest_info, BridgeClient(latest_info.base_url, latest_info.token)


def _abort_bridge_session(client: Any) -> None:
    """失败路径下尽力通知 Unity 侧结束 session，让日志文件落盘并停止继续写入；
    通知失败不影响本地的失败记录。"""
    try:
        client.end_session()
    except BridgeClientError:
        pass


def _finalize_failed_session(session_path: Path, project_path: Path, reason: str) -> None:
    mark_session_failed(session_path, reason)
    summary_payload = build_summary(session_path, load_log_rules(project_path))
    write_summary(session_path, summary_payload)


def _resolve_optional_project(args: argparse.Namespace) -> Path:
    try:
        effective = resolve_effective_config(project_path=args.project_path)
        return effective.project_path
    except ConfigError:
        if args.project_path:
            raise
        return Path.cwd()


def _error_code(exc: Exception) -> str:
    if isinstance(exc, CliError):
        return exc.code
    if isinstance(exc, BridgeClientError):
        return exc.code
    if isinstance(exc, DiscoveryError):
        return exc.code
    return "internal_error"


def print_json(payload: dict[str, Any], stream: Any = None) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream or sys.stdout)


def confirm_init(project_path: Path, force: bool = False) -> None:
    if not sys.stdin.isatty():
        raise ValueError("init 需要确认项目路径；在脚本中请添加 --yes")
    action = "重新生成缺失或已有配置" if force else "初始化缺失配置"
    print(f"将为以下 Unity 项目{action}：", file=sys.stderr)
    print(str(project_path), file=sys.stderr)
    answer = input("是否继续？[y/N] ").strip().lower()
    if answer not in {"y", "yes"}:
        raise ValueError("用户取消 init")


def resolve_session_path(args: argparse.Namespace, project_path: Path) -> Path:
    if getattr(args, "latest", False):
        return find_latest_session_path(project_path)
    if args.session_path:
        return Path(args.session_path).expanduser().resolve()
    raise ValueError("--session-path or --latest is required")


def wait_for_handshake(
    project_path: Path,
    expected_pid: int,
    timeout_seconds: float,
    poll_interval: float = 0.5,
) -> BridgeInfo:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while True:
        try:
            info = discover(project_path)
            if info.pid == expected_pid:
                return info
        except DiscoveryError as exc:
            last_error = exc
        if time.monotonic() > deadline:
            detail = f"：{last_error}" if last_error else ""
            raise CliError("timeout", f"等待 Unity Editor 完成握手超时{detail}")
        time.sleep(poll_interval)


if __name__ == "__main__":
    raise SystemExit(main())
