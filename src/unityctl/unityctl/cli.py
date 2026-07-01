import argparse
import json
import sys
from pathlib import Path

from unityctl.client import BridgeClient, BridgeClientError
from unityctl.editor import start_editor


DEFAULT_BASE_URL = "http://127.0.0.1:17890"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="unityctl")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status")
    subparsers.add_parser("play")
    subparsers.add_parser("stop")
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
            print_json(client.post("play"))
            return 0
        if args.command == "stop":
            print_json(client.post("stop"))
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

        parser.error(f"unsupported command: {args.command}")
        return 2
    except (BridgeClientError, ValueError) as exc:
        print_json({"ok": False, "error": str(exc)}, stream=sys.stderr)
        return 1


def print_json(payload: dict, stream=None) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream or sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
