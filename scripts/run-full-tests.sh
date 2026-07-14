#!/usr/bin/env bash
# 发布前全量校验：Python 单测 + Unity EditMode 全量矩阵（9 种 UGUI/TMP/InputSystem 组合）。
#
# 原本这部分测试跑在 GitHub Actions 的 self-hosted runner 上作为 release 门禁；
# 现在挪到本地执行（由 scripts/bump-version.sh 在打 tag 前调用），
# 不再依赖任何 self-hosted runner 是否在线。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SKIP_UNITY=false

usage() {
  cat <<'EOF'
用法：scripts/run-full-tests.sh [--skip-unity]

依次运行：
  1. Python 单测（scripts/run-python-tests.sh）
  2. Unity EditMode 全量矩阵，9 种 UGUI/TMP/InputSystem 组合（scripts/run-unity-matrix.sh --set full）

选项：
  --skip-unity   仅跑 Python 单测，跳过 Unity 矩阵（需要显式传入，不会静默跳过）

环境变量：
  UNITY_BIN              Unity Editor 可执行文件路径（默认：
                          /Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity）
  UNITY_FIXTURE_ROOT      Unity fixture 工程根目录（默认：.tmp/unity-fixtures）
  UNITY_MATRIX_RESULTS    测试结果 XML 输出目录（默认：.tmp/test-results/matrix）
  UNITY_MATRIX_LOGS       Unity 日志输出目录（默认：.tmp/logs/matrix）
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-unity)
      SKIP_UNITY=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "未知参数：$1"
      usage
      exit 2
      ;;
  esac
done

echo "==> [1/2] Python 单测"
bash "$SCRIPT_DIR/run-python-tests.sh"

if [[ "$SKIP_UNITY" == true ]]; then
  echo ""
  echo "已跳过 Unity 全量矩阵（--skip-unity）。"
  exit 0
fi

: "${UNITY_BIN:=/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity}"
export UNITY_BIN
export UNITY_FIXTURE_ROOT="${UNITY_FIXTURE_ROOT:-$REPO_ROOT/.tmp/unity-fixtures}"
export UNITY_MATRIX_RESULTS="${UNITY_MATRIX_RESULTS:-$REPO_ROOT/.tmp/test-results/matrix}"
export UNITY_MATRIX_LOGS="${UNITY_MATRIX_LOGS:-$REPO_ROOT/.tmp/logs/matrix}"

if [[ ! -x "$UNITY_BIN" ]]; then
  echo ""
  echo "UNITY_BIN 不可执行：$UNITY_BIN"
  echo "请安装对应版本的 Unity Editor 并激活 license，或显式传入 --skip-unity 跳过（不推荐）。"
  exit 2
fi

echo ""
echo "==> [2/2] Unity EditMode 全量矩阵"
bash "$SCRIPT_DIR/run-unity-matrix.sh" --set full
