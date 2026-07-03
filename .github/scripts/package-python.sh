#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DIST_DIR="${DIST_DIR:-$REPO_ROOT/.tmp/packages}"

mkdir -p "$DIST_DIR"

echo "构建 Python wheel 和 sdist..."
(
  cd "$REPO_ROOT/src/unityctl"
  uv build --out-dir "$DIST_DIR"
)

WHEEL_PATH="$(ls -t "$DIST_DIR"/*.whl | head -n 1)"
SDIST_PATH="$(ls -t "$DIST_DIR"/*.tar.gz | head -n 1)"

if [[ ! -f "$WHEEL_PATH" || ! -f "$SDIST_PATH" ]]; then
  echo "Python 打包产物不完整：$DIST_DIR"
  ls -la "$DIST_DIR"
  exit 1
fi

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "wheel_path=${WHEEL_PATH}" >> "$GITHUB_OUTPUT"
  echo "sdist_path=${SDIST_PATH}" >> "$GITHUB_OUTPUT"
fi

echo "wheel: $WHEEL_PATH"
echo "sdist: $SDIST_PATH"
