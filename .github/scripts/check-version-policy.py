"""Validate synchronized package versions and declared change types in CI."""

import argparse
import json
import os
import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = "packages/com.mk.unity-agent-bridge/package.json"
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
CHANGE = re.compile(r"^(?P<kind>[a-z]+)(?:\([^()\r\n]+\))?(?P<breaking>!)?:")
BREAKING = re.compile(r"^BREAKING[ -]CHANGE:", re.MULTILINE)


def parse_version(value):
    if not isinstance(value, str) or not (match := VERSION.fullmatch(value)):
        raise ValueError("版本必须为 X.Y.Z")
    return tuple(map(int, match.groups()))


def required_bump(messages):
    level = 0
    for message in messages:
        first_line = message.partition("\n")[0]
        match = CHANGE.match(first_line)
        if (match and match["breaking"]) or BREAKING.search(message):
            return 3
        if match:
            level = max(level, {"fix": 1, "feat": 2}.get(match["kind"], 0))
    return level


def validate_bump(base, current, level):
    if current < base:
        raise ValueError("版本不能低于基线")
    major, minor, patch = base
    minimum = (base, (major, minor, patch + 1), (major, minor + 1, 0), (major + 1, 0, 0))[level]
    if current < minimum:
        kind = ("", "Patch", "Minor", "Major")[level]
        raise ValueError(f"此次变更最低要求 {kind} 升版：至少升到 {'.'.join(map(str, minimum))}")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, encoding="utf-8")


def sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("无效的 Git 提交 SHA")
    return value


def read_versions():
    package = ROOT / "packages/com.mk.unity-agent-bridge"
    cli = ROOT / "src/unityctl"
    bridge = re.search(r'public const string Version = "([^"]+)";',
                       (package / "Editor/Core/BridgeConfig.cs").read_text(encoding="utf-8"))
    fallback = re.search(r'^__version__ = "([^"]+)"$',
                         (cli / "unityctl/__init__.py").read_text(encoding="utf-8"), re.MULTILINE)
    lock = tomllib.loads((cli / "uv.lock").read_text(encoding="utf-8"))
    return {
        "UPM": json.loads((ROOT / MANIFEST).read_text(encoding="utf-8"))["version"],
        "Bridge": bridge[1] if bridge else None,
        "CLI": tomllib.loads((cli / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"],
        "__init__": fallback[1] if fallback else None,
        "uv.lock": next((p["version"] for p in lock["package"] if p["name"] == "unity-run-bridge"), None),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=sha, help="本地对比基线（使用完整 SHA）")
    parser.add_argument("--github-event", type=Path, help="GitHub 事件 JSON")
    args = parser.parse_args()
    try:
        versions = read_versions()
        current = parse_version(versions["UPM"])
        if any(value != versions["UPM"] for value in versions.values()):
            raise ValueError(f"组件版本不一致：{versions}")
        base, head = args.base, git("rev-parse", "HEAD").strip()
        messages = []
        if args.github_event:
            event = json.loads(args.github_event.read_text(encoding="utf-8"))
            if os.environ.get("GITHUB_EVENT_NAME") == "pull_request":
                pr = event["pull_request"]
                base, head = sha(pr["base"]["sha"]), sha(pr["head"]["sha"])
                messages.append(pr["title"])
            elif os.environ.get("GITHUB_EVENT_NAME") == "push":
                base, head = sha(event["before"]), sha(event["after"])
        if base and base != "0" * 40:
            previous = parse_version(json.loads(git("show", f"{base}:{MANIFEST}"))["version"])
            messages.extend(git("log", "-z", "--format=%B", f"{base}..{head}").split("\0"))
            validate_bump(previous, current, required_bump(messages))
        print(f"版本门禁通过：{versions['UPM']}")
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"版本门禁失败：{exc}\n")


if __name__ == "__main__":
    main()
