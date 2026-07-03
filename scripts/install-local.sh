#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="${DIST_DIR:-$REPO_ROOT/.tmp/packages}"
UNITY_PROJECT_PATH="${1:-}"

usage() {
  cat <<'EOF'
用法：scripts/install-local.sh [UNITY_PROJECT_PATH]

本地模拟正式安装：
  1. 打包 Unity UPM .tgz
  2. 构建 Python wheel
  3. 用 wheel 安装 unityctl（与 Release 安装路径一致）
  4. 可选：将 Unity 项目的 manifest 依赖改为 file:<tgz绝对路径>

示例：
  scripts/install-local.sh
  scripts/install-local.sh /absolute/path/to/UnityProject
  DIST_DIR=/tmp/release scripts/install-local.sh
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "未找到 uv，请先安装：https://docs.astral.sh/uv/"
  exit 2
fi

mkdir -p "$DIST_DIR"

echo "==> 打包 Unity UPM package"
ARCHIVE_PATH="$(DIST_DIR="$DIST_DIR" bash "$REPO_ROOT/scripts/package-upm.sh" | tail -n 1)"
if [[ ! -f "$ARCHIVE_PATH" ]]; then
  echo "UPM 打包失败：$ARCHIVE_PATH"
  exit 2
fi
echo "UPM 产物：$ARCHIVE_PATH"

echo "==> 构建 Python wheel"
(
  cd "$REPO_ROOT/src/unityctl"
  uv build --out-dir "$DIST_DIR"
)
WHEEL_PATH="$(ls -t "$DIST_DIR"/*.whl | head -n 1)"
if [[ ! -f "$WHEEL_PATH" ]]; then
  echo "wheel 构建失败"
  exit 2
fi
echo "wheel 产物：$WHEEL_PATH"

echo "==> 安装 unityctl（模拟 Release wheel 安装）"
uv tool install --force "$WHEEL_PATH"

echo "==> 验证 unityctl 版本"
unityctl --version

if [[ -n "$UNITY_PROJECT_PATH" ]]; then
  MANIFEST="$UNITY_PROJECT_PATH/Packages/manifest.json"
  if [[ ! -f "$MANIFEST" ]]; then
    echo "找不到 Unity manifest：$MANIFEST"
    exit 2
  fi

  echo "==> 更新 Unity manifest 依赖为 tarball 引用"
  python3 - "$MANIFEST" "$ARCHIVE_PATH" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
archive_path = Path(sys.argv[2]).resolve()
package_id = "com.mk.unity-agent-bridge"

payload = json.loads(manifest_path.read_text(encoding="utf-8"))
dependencies = payload.setdefault("dependencies", {})
dependencies[package_id] = f"file:{archive_path}"
manifest_path.write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(f"已写入 {manifest_path}:")
print(f'  "{package_id}": "file:{archive_path}"')
PY
else
  cat <<EOF

未指定 Unity 项目路径，manifest 未修改。
如需模拟正式 UPM 安装，可在 Unity 项目 manifest.json 中添加：

  "com.mk.unity-agent-bridge": "file:${ARCHIVE_PATH}"

或重新运行：

  scripts/install-local.sh /absolute/path/to/UnityProject
EOF
fi

echo
echo "本地模拟安装完成。"
