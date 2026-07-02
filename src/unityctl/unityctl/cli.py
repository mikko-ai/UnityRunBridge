import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from unityctl.client import BridgeClient, BridgeClientError
from unityctl.config import (
    ConfigError,
    init_project_config,
    read_json,
    resolve_effective_config,
    write_json,
)
from unityctl.editor import start_editor
from unityctl.session import create_session, format_time, update_session_status, utc_now
from unityctl.summary import build_summary, load_log_rules, read_jsonl, write_summary


DEFAULT_BASE_URL = "http://127.0.0.1:17890"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="unityctl")
    parser.add_argument("--base-url")
    parser.add_argument("--project", dest="project_path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init")
    init.add_argument("--unity", dest="unity_path")
    init.add_argument("--unity-version")
    init.add_argument("--host", default="127.0.0.1")
    init.add_argument("--port", type=int, default=17890)
    init.add_argument("--scene", dest="default_scene")
    init.add_argument("--install-package", action="store_true")

    config = subparsers.add_parser("config")
    config_subparsers = config.add_subparsers(dest="config_command", required=True)
    config_subparsers.add_parser("show")
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

    logs = subparsers.add_parser("logs")
    logs.add_argument("--session-path", required=True)
    logs.add_argument("--limit", type=int, default=100)

    errors = subparsers.add_parser("errors")
    errors.add_argument("--session-path", required=True)

    summary = subparsers.add_parser("summary")
    summary.add_argument("--session-path", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "init":
            result = init_project_config(
                project_path=args.project_path or Path.cwd(),
                unity_path=args.unity_path,
                unity_version=args.unity_version,
                host=args.host,
                port=args.port,
                default_scene=args.default_scene,
            )
            print_json(
                {
                    "ok": True,
                    "projectPath": str(result.project_path),
                    "configPath": str(result.config_path),
                    "localConfigPath": str(result.local_config_path),
                    "bridgeUrl": result.bridge_url,
                    "packageInstalled": result.package_installed,
                    "nextSteps": [
                        "Add com.elex.unity-agent-bridge to Packages/manifest.json",
                        "Run unityctl start",
                        "Run unityctl status",
                    ],
                }
            )
            return 0

        if args.command == "config":
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

        client = BridgeClient(args.base_url or DEFAULT_BASE_URL)

        if args.command == "status":
            print_json(client.get_status())
            return 0
        if args.command == "play":
            if args.session_name:
                if not args.project_path:
                    raise ValueError("--project is required when --session is used")
                session = create_session(
                    project_path=args.project_path,
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
            if args.session_path:
                ended_at = format_time(utc_now())
                update_session_status(args.session_path, "stopped", ended_at=ended_at)
                project_for_rules = args.project or Path(args.session_path).parents[2]
                summary_payload = build_summary(
                    args.session_path,
                    load_log_rules(project_for_rules),
                )
                write_summary(args.session_path, summary_payload)
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
            rows = read_jsonl(Path(args.session_path) / "unity-console.jsonl")
            print_json({"ok": True, "logs": rows[-args.limit :]})
            return 0
        if args.command == "errors":
            rows = read_jsonl(Path(args.session_path) / "unity-console.jsonl")
            problems = [
                row
                for row in rows
                if row.get("type") in {"Error", "Exception", "Assert"}
            ]
            print_json({"ok": True, "errors": problems})
            return 0
        if args.command == "summary":
            summary_path = Path(args.session_path) / "summary.json"
            print(summary_path.read_text(encoding="utf-8"), end="")
            return 0

        parser.error(f"unsupported command: {args.command}")
        return 2
    except (BridgeClientError, ConfigError, ValueError) as exc:
        print_json({"ok": False, "error": str(exc)}, stream=sys.stderr)
        return 1


def print_json(payload: dict, stream=None) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream or sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
