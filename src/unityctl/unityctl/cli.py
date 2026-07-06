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
    default_bridge_package_ref,
    find_latest_session_path,
    find_unity_project_root,
    init_project_config,
    install_bridge_package,
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
    is_unity_project_locked,
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
from unityctl.skills import (
    DEFAULT_SKILLS_DIRNAME,
    SkillError,
    install_skill,
    resolve_skills_dir,
)
from unityctl.summary import build_summary, classify_log, load_log_rules, read_jsonl, write_summary


class CliError(RuntimeError):
    def __init__(self, code: str, message: str, extra: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.extra = extra or {}


class _HelpFormatter(argparse.RawDescriptionHelpFormatter, argparse.ArgumentDefaultsHelpFormatter):
    pass


def _add_project_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project",
        dest="project_path",
        metavar="PATH",
        help="Unity 项目根目录（默认从当前目录向上查找）",
    )


def _add_session_options(parser: argparse.ArgumentParser) -> None:
    session = parser.add_mutually_exclusive_group(required=True)
    session.add_argument(
        "--session-path",
        metavar="PATH",
        help="session 目录的绝对路径（.unity-agent/sessions/<sessionId>/）",
    )
    session.add_argument(
        "--latest",
        action="store_true",
        help="使用最近创建的 session",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="unityctl",
        description=(
            "通过 Unity Agent Bridge 控制 Unity Editor 的 CLI 工具。"
            "所有命令以 JSON 输出到 stdout；失败时 stderr 输出 {\"ok\": false, ...}。"
        ),
        epilog=(
            "示例:\n"
            "  unityctl init --yes\n"
            "  unityctl config validate\n"
            "  unityctl start\n"
            "  unityctl play --session login-flow --scene Assets/Scenes/Login.unity\n"
            "  unityctl stop --latest\n"
            "  unityctl doctor\n"
            "\n"
            "使用 unityctl <命令> --help 查看单个命令的详细参数。"
        ),
        formatter_class=_HelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"unityctl {__version__}")
    parser.add_argument(
        "--project",
        dest="global_project_path",
        metavar="PATH",
        help="Unity 项目根目录；可作为各子命令 --project 的全局默认值",
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        title="命令",
        metavar="COMMAND",
    )

    init = subparsers.add_parser(
        "init",
        help="初始化 .unity-agent 配置目录",
        description=(
            "在 Unity 项目根目录创建 .unity-agent/config.json、config.local.json 和 schema 文件。"
            "同时检测 Packages/manifest.json 是否包含 bridge 包依赖；"
            "缺失时在交互终端中询问是否写入，或使用 --install-package 直接写入。"
        ),
        formatter_class=_HelpFormatter,
    )
    _add_project_option(init)
    init.add_argument(
        "--unity",
        dest="unity_path",
        metavar="PATH",
        help="Unity 可执行文件路径（写入 config.local.json）",
    )
    init.add_argument("--unity-version", help="Unity 版本号（写入 config.json）")
    init.add_argument(
        "--port",
        dest="preferred_port",
        type=int,
        default=17890,
        help="Bridge 期望监听端口",
    )
    init.add_argument(
        "--scene",
        dest="default_scene",
        metavar="PATH",
        help="默认场景路径，例如 Assets/Scenes/Main.unity",
    )
    init.add_argument(
        "--yes",
        action="store_true",
        help="跳过交互确认（脚本/CI 使用）",
    )
    init.add_argument(
        "--force",
        action="store_true",
        help="重新生成缺失的配置文件（不覆盖已有 config.json / config.local.json）",
    )
    package_group = init.add_mutually_exclusive_group()
    package_group.add_argument(
        "--install-package",
        action="store_true",
        help="若 Packages/manifest.json 缺少 bridge 包依赖，直接写入（不询问）",
    )
    package_group.add_argument(
        "--no-install-package",
        action="store_true",
        help="跳过 Packages/manifest.json 依赖检测与写入",
    )
    init.add_argument(
        "--package-ref",
        metavar="REF",
        help=(
            "写入 manifest 的依赖引用，例如 git URL 或 file: 路径"
            "（默认指向与 unityctl 版本一致的 upm tag）"
        ),
    )

    config = subparsers.add_parser(
        "config",
        help="查看或校验项目配置",
        formatter_class=_HelpFormatter,
    )
    _add_project_option(config)
    config_subparsers = config.add_subparsers(
        dest="config_command",
        required=True,
        title="子命令",
        metavar="SUBCOMMAND",
    )
    config_subparsers.add_parser(
        "show",
        help="输出合并后的有效配置（项目配置 + 本机配置）",
        formatter_class=_HelpFormatter,
    )
    config_subparsers.add_parser(
        "validate",
        help="校验 config.json 与 config.local.json",
        formatter_class=_HelpFormatter,
    )
    set_local = config_subparsers.add_parser(
        "set-local",
        help="更新 config.local.json 中的单个字段",
        formatter_class=_HelpFormatter,
    )
    set_local.add_argument(
        "key",
        help="字段名，例如 unityExecutablePath",
    )
    set_local.add_argument(
        "value",
        help="字段值",
    )

    status = subparsers.add_parser(
        "status",
        help="查询 Unity Editor 当前状态",
        description="通过 Bridge 获取 editorState、编译结果、当前场景等信息。",
        formatter_class=_HelpFormatter,
    )
    _add_project_option(status)

    play = subparsers.add_parser(
        "play",
        help="进入 Play Mode",
        description=(
            "可选打开场景并创建 session 记录运行日志。"
            "默认等待进入 Play Mode；若存在编译错误则失败。"
        ),
        formatter_class=_HelpFormatter,
    )
    _add_project_option(play)
    play.add_argument(
        "--session",
        dest="session_name",
        metavar="NAME",
        help="创建 session 并记录 unity-console.jsonl（位于 .unity-agent/sessions/）",
    )
    play.add_argument(
        "--scene",
        dest="scene_path",
        metavar="PATH",
        help="进入 Play Mode 前打开的场景路径",
    )
    play.add_argument("--task", default="", help="session 任务描述（写入 session.json）")
    play.add_argument(
        "--trigger",
        default="agent",
        help="session 触发来源（写入 session.json）",
    )
    play.add_argument(
        "--timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="等待收敛的超时秒数（默认读取 config.json 中的 playSeconds）",
    )
    play.add_argument(
        "--no-wait",
        action="store_true",
        help="发送 play 请求后立即返回，不等待进入 Play Mode",
    )

    stop = subparsers.add_parser(
        "stop",
        help="退出 Play Mode",
        description="可选关联 session：退出后生成 summary.json。",
        formatter_class=_HelpFormatter,
    )
    _add_project_option(stop)
    stop.add_argument(
        "--session-path",
        metavar="PATH",
        help="关联的 session 目录；与 --latest 二选一",
    )
    stop.add_argument(
        "--latest",
        action="store_true",
        help="关联最近创建的 session",
    )
    stop.add_argument(
        "--timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="等待退出 Play Mode 的超时秒数（默认读取 config.json 中的 stopSeconds）",
    )
    stop.add_argument(
        "--no-wait",
        action="store_true",
        help="发送 stop 请求后立即返回，不等待 Editor 回到 idle",
    )

    pause = subparsers.add_parser(
        "pause",
        help="暂停 Play Mode",
        description="暂停当前 Play Mode（等同 Editor 中的暂停按钮），用 resume 恢复。",
        formatter_class=_HelpFormatter,
    )
    _add_project_option(pause)

    resume = subparsers.add_parser(
        "resume",
        help="恢复 Play Mode",
        description="恢复被 pause 暂停的 Play Mode。",
        formatter_class=_HelpFormatter,
    )
    _add_project_option(resume)

    open_scene = subparsers.add_parser(
        "open-scene",
        help="在 Editor 中打开场景",
        formatter_class=_HelpFormatter,
    )
    _add_project_option(open_scene)
    open_scene.add_argument(
        "scene_path",
        metavar="PATH",
        help="场景路径，例如 Assets/Scenes/Login.unity",
    )

    start = subparsers.add_parser(
        "start",
        help="启动 Unity Editor 进程",
        description="默认等待 Bridge 握手完成（写出 bridge.json 并可连接）。",
        formatter_class=_HelpFormatter,
    )
    _add_project_option(start)
    start.add_argument(
        "--unity",
        dest="unity_path",
        metavar="PATH",
        help="覆盖 config.local.json 中的 Unity 可执行文件路径",
    )
    start.add_argument(
        "--log-file",
        metavar="PATH",
        help="Editor 日志文件路径（默认 .unity-agent/unity-editor.log）",
    )
    start.add_argument(
        "--no-wait",
        action="store_true",
        help="启动进程后立即返回，不等待 Bridge 握手",
    )

    logs = subparsers.add_parser(
        "logs",
        help="读取 session 的 Unity 控制台日志",
        description=(
            "从 session 目录的 unity-console.jsonl 读取 Unity Console 日志，"
            "按时间顺序返回过滤后最近的 N 条（含 type、message、stackTrace 等字段）。"
            "每条日志附带 line 字段（在 unity-console.jsonl 中的 1-based 行号），"
            "便于回到完整日志中查看上下文。"
        ),
        formatter_class=_HelpFormatter,
    )
    _add_project_option(logs)
    _add_session_options(logs)
    logs.add_argument(
        "--limit",
        type=int,
        default=100,
        metavar="N",
        help="返回过滤后最近的 N 条日志",
    )
    logs.add_argument(
        "--grep",
        metavar="TEXT",
        help="只返回 message 包含该子串的日志（不区分大小写）",
    )
    logs.add_argument(
        "--type",
        dest="types",
        metavar="TYPES",
        help="按日志类型过滤，逗号分隔（如 Error,Exception,Warning,Log,Assert）",
    )
    logs.add_argument(
        "--after-sequence",
        type=int,
        metavar="N",
        help="只返回 sequence 大于 N 的日志（用于跳过已读日志、只看增量）",
    )

    errors = subparsers.add_parser(
        "errors",
        help="读取 session 中的错误与阻塞日志",
        description="按 .unity-agent/log-rules.json 中的 ignore 规则过滤后返回 problem/blocking 级别条目。",
        formatter_class=_HelpFormatter,
    )
    _add_project_option(errors)
    _add_session_options(errors)

    summary = subparsers.add_parser(
        "summary",
        help="读取 session 的 summary.json",
        description=(
            "读取 session 的运行结果汇总。status 取值："
            "passed（无问题）、problem_detected（出现普通 Error 日志，需结合日志判断）、"
            "failed（出现 Exception/Assert 等 blocking problem，或进程级失败，"
            "原因见 failedReason）。"
        ),
        formatter_class=_HelpFormatter,
    )
    _add_project_option(summary)
    _add_session_options(summary)

    refresh = subparsers.add_parser(
        "refresh",
        help="触发脚本重编译并等待完成",
        description=(
            "触发 AssetDatabase.Refresh() 并轮询直到编译结束，"
            "返回 compilationSucceeded 与 compilationErrors。"
            "改完代码后用它验证编译是否通过。"
        ),
        formatter_class=_HelpFormatter,
    )
    _add_project_option(refresh)
    refresh.add_argument(
        "--timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="等待编译完成的超时秒数（默认读取 config.json 中的 playSeconds）",
    )

    doctor = subparsers.add_parser(
        "doctor",
        help="诊断项目配置与 Bridge 连通性",
        description="检查项目根目录、配置文件、UPM 包、bridge.json 和 Bridge HTTP 可达性。",
        formatter_class=_HelpFormatter,
    )
    _add_project_option(doctor)

    skills = subparsers.add_parser(
        "skills",
        help="安装或更新 agent skill（SKILL.md）",
        description=(
            "把 CLI 内置的 unityctl skill 安装到项目的 skills 目录，"
            f"默认 {DEFAULT_SKILLS_DIRNAME}/，供 coding agent 学习 Unity 验证流程。"
        ),
        formatter_class=_HelpFormatter,
    )
    _add_project_option(skills)
    skills_subparsers = skills.add_subparsers(
        dest="skills_command",
        required=True,
        title="子命令",
        metavar="SUBCOMMAND",
    )
    skills_init = skills_subparsers.add_parser(
        "init",
        help="安装 skill（已存在时不覆盖）",
        formatter_class=_HelpFormatter,
    )
    skills_update = skills_subparsers.add_parser(
        "update",
        help="把 skill 刷新为当前 CLI 版本内置内容（总是覆盖；未安装则直接安装）",
        formatter_class=_HelpFormatter,
    )
    for sub in (skills_init, skills_update):
        sub.add_argument(
            "--target",
            metavar="PATH",
            default=None,
            help=(
                "skills 根目录；相对路径基于 Unity 项目根目录解析，也可用绝对路径"
                f"（默认 {DEFAULT_SKILLS_DIRNAME}）"
            ),
        )

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
        "skills": cmd_skills,
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

    package_ref = args.package_ref or default_bridge_package_ref(__version__)
    package_action, package_installed = _handle_bridge_package_install(
        project=result.project_path,
        package_ref=package_ref,
        install=args.install_package,
        skip=args.no_install_package,
        assume_yes=args.yes,
    )

    next_steps = [
        "Edit .unity-agent/config.local.json and set unityExecutablePath",
        "Run unityctl config validate",
        "Run unityctl start",
    ]
    if not package_installed:
        next_steps.insert(
            0,
            f"Add {UNITY_AGENT_BRIDGE_PACKAGE_ID} to Packages/manifest.json "
            "(or rerun unityctl init --install-package)",
        )

    return {
        "ok": True,
        "code": "ok",
        "projectPath": str(result.project_path),
        "configPath": str(result.config_path),
        "localConfigPath": str(result.local_config_path),
        "preferredPort": result.preferred_port,
        "packageInstalled": package_installed,
        "packageAction": package_action,
        "packageRef": package_ref if package_action == "installed" else None,
        "alreadyInitialized": bool(result.kept_paths),
        "createdPaths": [str(path) for path in result.created_paths],
        "keptPaths": [str(path) for path in result.kept_paths],
        "updatedIgnore": result.updated_ignore,
        "nextSteps": next_steps,
    }


def _handle_bridge_package_install(
    project: Path,
    package_ref: str,
    install: bool,
    skip: bool,
    assume_yes: bool,
) -> tuple[str, bool]:
    """检测 Packages/manifest.json 中的 bridge 包依赖，按需写入。

    返回 (packageAction, packageInstalled)。packageAction 取值：
    already_installed / installed / declined / skipped。
    """
    if is_bridge_package_installed(project):
        return "already_installed", True
    if skip:
        return "skipped", False
    if not install:
        # 未显式指定时：交互终端里询问用户；非交互（含 --yes）不擅自改 manifest。
        if assume_yes or not sys.stdin.isatty():
            return "skipped", False
        if not confirm_install_package(project, package_ref):
            return "declined", False
    manifest_path = install_bridge_package(project, package_ref)
    print(f"已写入 {manifest_path}", file=sys.stderr)
    return "installed", True


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
    project_path = effective.project_path

    info: BridgeInfo | None = None
    try:
        candidate = discover(project_path)
        BridgeClient(candidate.base_url, candidate.token).get_status()
        info = candidate
    except (DiscoveryError, BridgeClientError):
        info = None

    if info is not None:
        return {
            "ok": True,
            "code": "already_running",
            "pid": info.pid,
            "projectPath": str(project_path),
            "unityExecutablePath": (
                str(effective.unity_executable_path)
                if effective.unity_executable_path
                else None
            ),
            "logFile": None,
            "bridgeReady": True,
            "bridgeUrl": info.base_url,
            "unityVersion": info.unity_version,
        }

    if is_unity_project_locked(project_path):
        raise CliError(
            "editor_already_running",
            "检测到该 Unity 项目已被另一个 Editor 实例占用（Temp/UnityLockfile），"
            "但 Bridge 尚未就绪，可能卡在多实例提示框或正在握手中。"
            "请先处理已有的 Unity 窗口（关闭弹窗或退出该实例）后再运行 unityctl start。",
        )

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
        handshake_info = wait_for_handshake(
            effective.project_path,
            expected_pid=process.pid,
            timeout_seconds=effective.timeouts.start_editor_seconds,
        )
        payload["bridgeReady"] = True
        payload["bridgeUrl"] = handshake_info.base_url
        payload["unityVersion"] = handshake_info.unity_version

    return payload


def cmd_logs(args: argparse.Namespace) -> dict[str, Any]:
    project_path = _resolve_optional_project(args)
    session_path = resolve_session_path(args, project_path)
    rows = read_jsonl(session_path / "unity-console.jsonl")
    # line 是该条日志在 unity-console.jsonl 中的 1-based 行号，
    # 过滤后仍保留，便于回到完整日志中查看前后上下文。
    numbered = [{"line": index, **row} for index, row in enumerate(rows, start=1)]

    filtered = numbered
    if args.grep:
        needle = args.grep.lower()
        filtered = [
            row for row in filtered if needle in str(row.get("message", "")).lower()
        ]
    if args.types:
        wanted = {item.strip().lower() for item in args.types.split(",") if item.strip()}
        filtered = [
            row for row in filtered if str(row.get("type", "")).lower() in wanted
        ]
    if args.after_sequence is not None:
        filtered = [
            row
            for row in filtered
            if isinstance(row.get("sequence"), int)
            and row["sequence"] > args.after_sequence
        ]

    return {
        "ok": True,
        "code": "ok",
        "totalCount": len(numbered),
        "matchedCount": len(filtered),
        "logs": filtered[-args.limit :],
    }


def cmd_errors(args: argparse.Namespace) -> dict[str, Any]:
    project_path = _resolve_optional_project(args)
    session_path = resolve_session_path(args, project_path)
    rules = load_log_rules(project_path)
    rows = read_jsonl(session_path / "unity-console.jsonl")
    problems = []
    for line, row in enumerate(rows, start=1):
        severity = classify_log(row, rules)
        if severity in {"problem", "blocking"}:
            problems.append({"line": line, **row, "severity": severity})
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

    bridge_reachable = False
    if info is not None:
        alive = is_pid_alive(info.pid)
        add("editor_pid_alive", alive, f"pid={info.pid}")
        if alive:
            try:
                BridgeClient(info.base_url, info.token).get_status()
                bridge_reachable = True
                add("bridge_reachable", True, info.base_url)
            except BridgeClientError as exc:
                add("bridge_reachable", False, str(exc))
        else:
            add("bridge_reachable", False, "editor process not alive")

    if project_path is not None:
        locked = is_unity_project_locked(project_path)
        if bridge_reachable:
            add(
                "project_lock",
                True,
                f"项目由存活且可达的 Editor 进程持有（pid={info.pid}）",
            )
        elif locked:
            add(
                "project_lock",
                False,
                "检测到 Temp/UnityLockfile 被占用（或无法确认未被占用），但没有可达的 Bridge；"
                "Unity 可能卡在多实例提示框、正在启动/编译中，或锁文件权限异常。"
                "此时执行 unityctl start 会导致新实例卡死，建议先手动确认 Unity 窗口状态",
            )
        else:
            add("project_lock", True, "项目未被占用，可以运行 unityctl start")

    overall_ok = all(check["ok"] for check in checks)
    return {"ok": overall_ok, "code": "ok" if overall_ok else "internal_error", "checks": checks}


def cmd_skills(args: argparse.Namespace) -> dict[str, Any]:
    # 绝对路径 --target 不依赖项目根目录，找不到项目也允许安装
    project_path: Path | None = None
    try:
        project_path = find_unity_project_root(args.project_path or Path.cwd())
    except ConfigError:
        pass

    try:
        skills_dir = resolve_skills_dir(project_path, args.target)
        result = install_skill(
            skills_dir,
            version=__version__,
            overwrite=args.skills_command == "update",
        )
    except SkillError as exc:
        raise CliError("invalid_request", str(exc)) from exc

    payload: dict[str, Any] = {
        "ok": True,
        "code": result.action,
        "skillPath": str(result.skill_path),
        "version": result.version,
    }
    if result.previous_version is not None and result.previous_version != result.version:
        payload["previousVersion"] = result.previous_version
    if result.action == "already_installed":
        payload["hint"] = "skill 已存在且未被覆盖；如需刷新请运行 unityctl skills update"
    return payload


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


def confirm_install_package(project_path: Path, package_ref: str) -> bool:
    print(
        f"检测到 {project_path / 'Packages' / 'manifest.json'} 中缺少 "
        f"{UNITY_AGENT_BRIDGE_PACKAGE_ID} 依赖。",
        file=sys.stderr,
    )
    print(f"将写入引用：{package_ref}", file=sys.stderr)
    answer = input("是否写入 Packages/manifest.json？[y/N] ").strip().lower()
    return answer in {"y", "yes"}


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
