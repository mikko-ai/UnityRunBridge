#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "运行 Python tests..."
cd "$REPO_ROOT/src/unityctl"
uv sync
uv run pytest tests -v "$@"
