#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PACKAGE_DIR="$REPO_ROOT/packages/com.mk.unity-agent-bridge"
DIST_DIR="${DIST_DIR:-$REPO_ROOT/.tmp/packages}"

if [[ ! -f "$PACKAGE_DIR/package.json" ]]; then
  echo "找不到 Unity package manifest：$PACKAGE_DIR/package.json"
  exit 2
fi

VERSION="$(
  python3 - "$PACKAGE_DIR/package.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(payload["version"])
PY
)"

ARCHIVE_NAME="com.mk.unity-agent-bridge-$VERSION.tgz"
mkdir -p "$DIST_DIR"

# Unity 要求本地 tarball 内部的顶层目录必须严格命名为 "package"
# （而不是包名本身），否则 Unity 解压后会在临时目录下找不到
# package.json，报错 "The file [.../package.json] cannot be found"。
STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGE_DIR"' EXIT
cp -R "$PACKAGE_DIR" "$STAGE_DIR/package"

echo "打包 Unity UPM package：$ARCHIVE_NAME"
tar \
  --exclude=".DS_Store" \
  -czf "$DIST_DIR/$ARCHIVE_NAME" \
  -C "$STAGE_DIR" \
  "package"

echo "$DIST_DIR/$ARCHIVE_NAME"
