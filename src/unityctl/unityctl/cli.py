import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from unityctl.client import BridgeClient, BridgeClientError
from unityctl.config import (
    ConfigError,
    find_latest_session_path,
    find_unity_project_root,
    init_project_config,
    read_json,
    resolve_effective_config,
    validate_project_config,
    write_json,
)
from unityctl.editor import start_editor
from unityctl.session import create_session, format_time, update_session_status, utc_now
from unityctl.summary import build_summary, load_log_rules, read_jsonl, write_summary


DEFAULT_BASE_URL = "http://127.0.0.1:17890"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="unityctl")
    parser.add_argument("--base-url")
    parser.add_argument("--project", dest="global_project_path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init")
    init.add_argument("--unity", dest="unity_path")
    init.add_argument("--unity-version")
    init.add_argument("--host", default="127.0.0.1")
    init.add_argument("--port", type=int, default=17890)
    init.add_argument("--scene", dest="default_scene")
    init.add_argument("--install-package", action="store_true")
    init.add_argument("--yes", action="store_true")
    init.add_argument("--force", action="store_true")

    config = subparsers.add_parser("config")
    config_subparsers = config.add_subparsers(dest="config_command", required=True)
    config_subparsers.add_parser("show")
    config_subparsers.add_parser("validate")
    set_local = config_subparsers.add_parser("set-local")
    set_local.add_argument("key")
    set_local.add_argument("value")

    subparsers.add_parser("status")
    play = subparsers.add_parser("play")
    play.add_argument("--project", dest="project_path")
    play.add_argument("--session", dest="session_name")
    play.add_argument("--scene", dest="scene_path")
    play.add_argument("--task", default="")
    play.add_argument("--trigger", default="agent")

    stop = subparsers.add_parser("stop")
    stop.add_argument("--session-path")
    stop.add_argument("--project")
    stop.add_argument("--latest", action="store_true")

    subparsers.add_parser("pause")
    subparsers.add_parser("resume")

    open_scene = subparsers.add_parser("open-scene")
    open_scene.add_argument("scene_path")

    start = subparsers.add_parser("start-editor")
    start.add_argument("--unity", required=True, dest="unity_path")
    start.add_argument("--project", required=True, dest="project_path")
    start.add_argument(
        "--log-file",
        default=str(Path.home() / ".unity-agent" / "unity-editor.log"),
    )

    start = subparsers.add_parser("start")
    start.add_argument("--unity", dest="unity_path")
    start.add_argument("--log-file")
    start.add_argument("--no-wait", action="store_true")

    logs = subparsers.add_parser("logs")
    logs.add_argument("--session-path")
    logs.add_argument("--latest", action="store_true")
    logs.add_argument("--limit", type=int, default=100)

    errors = subparsers.add_parser("errors")
    errors.add_argument("--session-path")
    errors.add_argument("--latest", action="store_true")

    summary = subparsers.add_parser("summary")
    summary.add_argument("--session-path")
    summary.add_argument("--latest", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.project_path = (
        getattr(args, "project_path", None)
        or getattr(args, "project", None)
        or args.global_project_path
    )

    try:
        if args.command == "init":
            project = find_unity_project_root(args.project_path or Path.cwd())
            if not args.yes:
                confirm_init(project, force=args.force)
            result = init_project_config(
                project_path=project,
                unity_path=args.unity_path,
                unity_version=args.unity_version,
                host=args.host,
                port=args.port,
                default_scene=args.default_scene,
                force=args.force,
            )
            print_json(
                {
                    "ok": True,
                    "projectPath": str(result.project_path),
                    "configPath": str(result.config_path),
                    "localConfigPath": str(result.local_config_path),
                    "bridgeUrl": result.bridge_url,
                    "packageInstalled": result.package_installed,
                    "alreadyInitialized": bool(result.kept_paths),
                    "createdPaths": [str(path) for path in result.created_paths],
                    "keptPaths": [str(path) for path in result.kept_paths],
                    "updatedIgnore": result.updated_ignore,
                    "nextSteps": [
                        "Edit .unity-agent/config.local.jsonc and set unityExecutablePath",
                        "Run unityctl config validate",
                        "Run unityctl start",
                    ],
                }
            )
            return 0

        if args.command == "config":
            if args.config_command == "validate":
                project = find_unity_project_root(args.project_path or Path.cwd())
                result = validate_project_config(project)
                print_json(
                    {
                        "ok": result.ok,
                        "projectPath": str(result.project_path),
                        "errors": [
                            {"field": issue.field, "message": issue.message}
                            for issue in result.errors
                        ],
                        "warnings": [
                            {"field": issue.field, "message": issue.message}
                            for issue in result.warnings
                        ],
                    }
                )
                return 0 if result.ok else 1
            effective = resolve_effective_config(
                project_path=args.project_path,
                base_url=args.base_url,
            )
            if args.config_command == "show":
                print_json(
                    {
                        "ok": True,
                        "projectPath": str(effective.project_path),
                        "bridgeUrl": effective.bridge_url,
                        "unityVersion": effective.unity_version,
                        "unityExecutablePath": (
                            str(effective.unity_executable_path)
                            if effective.unity_executable_path
                            else None
                        ),
                        "sources": {
                            "projectConfig": str(effective.project_config_path),
                            "localConfig": str(effective.local_config_path),
                        },
                    }
                )
                return 0
            if args.config_command == "set-local":
                payload = read_json(effective.local_config_path)
                payload[args.key] = args.value
                write_json(effective.local_config_path, payload)
                print_json({"ok": True, args.key: args.value})
                return 0

        if args.command == "start-editor":
            Path(args.log_file).expanduser().parent.mkdir(parents=True, exist_ok=True)
            process = start_editor(args.unity_path, args.project_path, args.log_file)
            print_json({"ok": True, "pid": process.pid, "logFile": args.log_file})
            return 0

        effective = None
        try:
            effective = resolve_effective_config(
                project_path=args.project_path,
                base_url=args.base_url,
            )
        except ConfigError:
            if args.project_path or command_requires_project(args):
                raise

        bridge_url = effective.bridge_url if effective else args.base_url or DEFAULT_BASE_URL
        client = BridgeClient(bridge_url)

        if args.command == "start":
            unity_executable = args.unity_path or effective.unity_executable_path
            if unity_executable is None:
                raise ValueError(
                    "Unity executable path is required. Edit "
                    ".unity-agent/config.local.jsonc or run unityctl config set-local "
                    "unityExecutablePath "
                    '"/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity"'
                )
            log_file = (
                Path(args.log_file).expanduser()
                if args.log_file
                else effective.project_path / ".unity-agent" / "unity-editor.log"
            )
            log_file.parent.mkdir(parents=True, exist_ok=True)
            process = start_editor(
                str(unity_executable),
                effective.project_path,
                log_file,
            )
            ready_payload = None if args.no_wait else wait_for_bridge(effective.bridge_url)
            payload = {
                "ok": True,
                "pid": process.pid,
                "projectPath": str(effective.project_path),
                "unityExecutablePath": str(unity_executable),
                "bridgeUrl": effective.bridge_url,
                "bridgeReady": ready_payload is not None,
                "logFile": str(log_file),
            }
            if ready_payload is not None:
                payload["status"] = ready_payload
            print_json(payload)
            return 0
        if args.command == "status":
            print_json(client.get_status())
            return 0
        if args.command == "play":
            if args.session_name:
                project_path = effective.project_path
                session = create_session(
                    project_path=project_path,
                    name=args.session_name,
                    scene_path=args.scene_path,
                    trigger=args.trigger,
                    task=args.task,
                    created_at=utc_now(),
                )
                started_at = format_time(utc_now())
                update_session_status(
                    session.session_path,
                    "running",
                    started_at=started_at,
                )
                client.start_session(session.session_id, str(session.session_path))
                play_response = client.post("play")
                print_json(
                    {
                        "ok": bool(play_response.get("ok", False)),
                        "sessionId": session.session_id,
                        "sessionPath": str(session.session_path),
                        "play": play_response,
                    }
                )
                return 0
            print_json(client.post("play"))
            return 0
        if args.command == "stop":
            stop_response = client.post("stop")
            end_response = client.end_session()
            payload = {
                "ok": bool(stop_response.get("ok", False)),
                "stop": stop_response,
                "sessionEnd": end_response,
            }
            session_path = None
            if args.session_path or getattr(args, "latest", False):
                session_path = resolve_session_path(
                    args,
                    effective.project_path if effective else Path.cwd(),
                )
            if session_path:
                ended_at = format_time(utc_now())
                update_session_status(session_path, "stopped", ended_at=ended_at)
                project_for_rules = (
                    effective.project_path if effective else args.project or session_path.parents[2]
                )
                summary_payload = build_summary(
                    session_path,
                    load_log_rules(project_for_rules),
                )
                write_summary(session_path, summary_payload)
                payload["summary"] = summary_payload
            print_json(payload)
            return 0
        if args.command == "pause":
            print_json(client.post("pause"))
            return 0
        if args.command == "resume":
            print_json(client.post("resume"))
            return 0
        if args.command == "open-scene":
            print_json(client.open_scene(args.scene_path))
            return 0
        if args.command == "logs":
            session_path = resolve_session_path(
                args,
                effective.project_path if effective else Path.cwd(),
            )
            rows = read_jsonl(session_path / "unity-console.jsonl")
            print_json({"ok": True, "logs": rows[-args.limit :]})
            return 0
        if args.command == "errors":
            session_path = resolve_session_path(
                args,
                effective.project_path if effective else Path.cwd(),
            )
            rows = read_jsonl(session_path / "unity-console.jsonl")
            problems = [
                row
                for row in rows
                if row.get("type") in {"Error", "Exception", "Assert"}
            ]
            print_json({"ok": True, "errors": problems})
            return 0
        if args.command == "summary":
            session_path = resolve_session_path(
                args,
                effective.project_path if effective else Path.cwd(),
            )
            summary_path = session_path / "summary.json"
            print(summary_path.read_text(encoding="utf-8"), end="")
            return 0

        parser.error(f"unsupported command: {args.command}")
        return 2
    except (BridgeClientError, ConfigError, ValueError) as exc:
        print_json({"ok": False, "error": str(exc)}, stream=sys.stderr)
        return 1


def print_json(payload: dict, stream=None) -> None:
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


def command_requires_project(args) -> bool:
    return (
        args.command == "start"
        or (args.command == "play" and bool(args.session_name))
        or bool(getattr(args, "latest", False))
    )


def resolve_session_path(args, project_path: Path) -> Path:
    if getattr(args, "latest", False):
        return find_latest_session_path(project_path)
    if args.session_path:
        return Path(args.session_path).expanduser().resolve()
    raise ValueError("--session-path or --latest is required")


def wait_for_bridge(base_url: str, timeout_seconds: int = 60) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            status = BridgeClient(base_url).get_status()
            if status.get("ok", False):
                return status
        except BridgeClientError as exc:
            last_error = exc
        time.sleep(1)
    detail = f": {last_error}" if last_error else ""
    raise ValueError(f"Bridge did not become ready at {base_url}{detail}")


if __name__ == "__main__":
    raise SystemExit(main())
