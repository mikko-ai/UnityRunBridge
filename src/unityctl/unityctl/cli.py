import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from unityctl.client import BridgeClient, BridgeClientError
from unityctl.editor import start_editor
from unityctl.session import create_session, format_time, update_session_status, utc_now
from unityctl.summary import build_summary, load_log_rules, read_jsonl, write_summary


DEFAULT_BASE_URL = "http://127.0.0.1:17890"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="unityctl")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    subparsers = parser.add_subparsers(dest="command", required=True)

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
        if args.command == "start-editor":
            Path(args.log_file).expanduser().parent.mkdir(parents=True, exist_ok=True)
            process = start_editor(args.unity_path, args.project_path, args.log_file)
            print_json({"ok": True, "pid": process.pid, "logFile": args.log_file})
            return 0

        client = BridgeClient(args.base_url)

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
    except (BridgeClientError, ValueError) as exc:
        print_json({"ok": False, "error": str(exc)}, stream=sys.stderr)
        return 1


def print_json(payload: dict, stream=None) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream or sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
