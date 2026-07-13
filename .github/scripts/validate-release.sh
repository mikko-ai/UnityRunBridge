#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TAG_NAME="${1:-${GITHUB_REF_NAME:-}}"

if [[ -z "$TAG_NAME" ]]; then
  echo "缺少 release tag：请传入 tag，或在 GitHub Actions 中设置 GITHUB_REF_NAME。"
  exit 2
fi

if [[ "$TAG_NAME" != v* ]]; then
  echo "release tag 必须以 v 开头：$TAG_NAME"
  exit 2
fi

git -C "$REPO_ROOT" fetch origin main:refs/remotes/origin/main

TAG_COMMIT="$(git -C "$REPO_ROOT" rev-list -n 1 "$TAG_NAME")"
if ! git -C "$REPO_ROOT" merge-base --is-ancestor "$TAG_COMMIT" origin/main; then
  echo "Tag ${TAG_NAME} (${TAG_COMMIT}) 不在 origin/main 历史上，拒绝发布。"
  exit 1
fi
echo "Tag ${TAG_NAME} 位于 main 历史上。"

TAG_VERSION="${TAG_NAME#v}"

read -r PACKAGE_VERSION BRIDGE_CONFIG_VERSION PYPROJECT_VERSION INIT_VERSION <<< "$(python3 - "$REPO_ROOT" <<'PY'
import json
import re
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])

package_json = repo_root / "packages/com.mk.unity-agent-bridge/package.json"
bridge_config = repo_root / "packages/com.mk.unity-agent-bridge/Editor/Core/BridgeConfig.cs"
pyproject = repo_root / "src/unityctl/pyproject.toml"
init_py = repo_root / "src/unityctl/unityctl/__init__.py"

package_version = json.loads(package_json.read_text(encoding="utf-8"))["version"]

bridge_match = re.search(
    r'public const string Version = "([^"]+)";',
    bridge_config.read_text(encoding="utf-8"),
)
if bridge_match is None:
    raise SystemExit("无法读取 BridgeConfig.cs Version")

pyproject_match = re.search(
    r'^version = "([^"]+)"$',
    pyproject.read_text(encoding="utf-8"),
    flags=re.MULTILINE,
)
if pyproject_match is None:
    raise SystemExit("无法读取 pyproject.toml version")

init_match = re.search(
    r'^__version__ = "([^"]+)"$',
    init_py.read_text(encoding="utf-8"),
    flags=re.MULTILINE,
)
if init_match is None:
    raise SystemExit("无法读取 __init__.py __version__")

print(
    f"{package_version} {bridge_match.group(1)} "
    f"{pyproject_match.group(1)} {init_match.group(1)}"
)
PY
)"

echo "TAG=${TAG_VERSION}"
echo "package=${PACKAGE_VERSION}"
echo "BridgeConfig=${BRIDGE_CONFIG_VERSION}"
echo "pyproject=${PYPROJECT_VERSION}"
echo "init=${INIT_VERSION}"

if [[ "$TAG_VERSION" != "$PACKAGE_VERSION" ]] \
  || [[ "$TAG_VERSION" != "$BRIDGE_CONFIG_VERSION" ]] \
  || [[ "$TAG_VERSION" != "$PYPROJECT_VERSION" ]] \
  || [[ "$TAG_VERSION" != "$INIT_VERSION" ]]; then
  echo "版本不一致：tag=${TAG_VERSION}, package.json=${PACKAGE_VERSION}, BridgeConfig.cs=${BRIDGE_CONFIG_VERSION}, pyproject.toml=${PYPROJECT_VERSION}, __init__.py=${INIT_VERSION}"
  exit 1
fi

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "version=${TAG_VERSION}" >> "$GITHUB_OUTPUT"
fi

echo "Validated release version: ${TAG_VERSION}"
