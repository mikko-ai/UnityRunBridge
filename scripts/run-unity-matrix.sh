#!/usr/bin/env bash
# 按矩阵运行 Unity EditMode 测试。
# 用法：
#   UNITY_BIN=... bash scripts/run-unity-matrix.sh --set pr
#   UNITY_BIN=... bash scripts/run-unity-matrix.sh --set full
#   UNITY_BIN=... bash scripts/run-unity-matrix.sh --name ugui-legacy
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UNITY_BIN="${UNITY_BIN:-}"
FIXTURE_ROOT="${UNITY_FIXTURE_ROOT:-$REPO_ROOT/.tmp/unity-fixtures}"
RESULTS_ROOT="${UNITY_MATRIX_RESULTS:-$REPO_ROOT/.tmp/test-results/matrix}"
LOGS_ROOT="${UNITY_MATRIX_LOGS:-$REPO_ROOT/.tmp/logs/matrix}"

SET_NAME=""
ONLY_NAME=""

usage() {
  cat <<'EOF'
用法:
  run-unity-matrix.sh --set pr|full
  run-unity-matrix.sh --name <fixture>

PR 集 (4):
  nougui-legacy, ugui-legacy, ugui-inputsystem, ugui-tmp-both

Full 集 (9):
  NoUGUI/UGUI/UGUI+TMP × Legacy/InputSystem/Both
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --set) SET_NAME="$2"; shift 2 ;;
    --name) ONLY_NAME="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数: $1"; usage; exit 2 ;;
  esac
done

if [[ -z "$UNITY_BIN" ]]; then
  echo "请先设置 UNITY_BIN"
  exit 2
fi
if [[ "$UNITY_BIN" == *.app ]]; then
  UNITY_BIN="$UNITY_BIN/Contents/MacOS/Unity"
fi
if [[ ! -x "$UNITY_BIN" ]]; then
  echo "UNITY_BIN 不可执行：$UNITY_BIN"
  exit 2
fi

PR_FIXTURES=(
  nougui-legacy
  ugui-legacy
  ugui-inputsystem
  ugui-tmp-both
)

FULL_FIXTURES=(
  nougui-legacy
  nougui-inputsystem
  nougui-both
  ugui-legacy
  ugui-inputsystem
  ugui-both
  ugui-tmp-legacy
  ugui-tmp-inputsystem
  ugui-tmp-both
)

FIXTURES=()
if [[ -n "$ONLY_NAME" ]]; then
  FIXTURES=("$ONLY_NAME")
elif [[ "$SET_NAME" == "pr" ]]; then
  FIXTURES=("${PR_FIXTURES[@]}")
elif [[ "$SET_NAME" == "full" ]]; then
  FIXTURES=("${FULL_FIXTURES[@]}")
else
  usage
  exit 2
fi

mkdir -p "$RESULTS_ROOT" "$LOGS_ROOT"

parse_xml_counts() {
  local xml="$1"
  /usr/bin/python3 - "$xml" <<'PY'
import sys, xml.etree.ElementTree as ET
path = sys.argv[1]
root = ET.parse(path).getroot()
# NUnit 3 result root attributes
passed = root.attrib.get("passed", "0")
failed = root.attrib.get("failed", "0")
total = root.attrib.get("total", "0")
result = root.attrib.get("result", "?")
print(f"{result}\t{passed}\t{failed}\t{total}")
PY
}

FAILED_FIXTURES=()
declare -a SUMMARY_LINES=()
TOTAL_FAILED=0

for name in "${FIXTURES[@]}"; do
  echo ""
  echo "======== matrix: $name ========"
  bash "$SCRIPT_DIR/create-unity-test-fixture.sh" --name "$name" --force

  PROJECT_PATH="$FIXTURE_ROOT/$name"
  RESULTS_PATH="$RESULTS_ROOT/$name.xml"
  LOG_PATH="$LOGS_ROOT/$name.log"

  # 禁止并行共享：每个 fixture 独立 projectPath / Library / 结果 / 日志。
  set +e
  "$UNITY_BIN" \
    -batchmode \
    -nographics \
    -projectPath "$PROJECT_PATH" \
    -runTests \
    -testPlatform EditMode \
    -testResults "$RESULTS_PATH" \
    -logFile "$LOG_PATH"
  unity_exit=$?
  set -e

  if [[ ! -f "$RESULTS_PATH" ]]; then
    echo "ERROR: 缺少结果 XML：$RESULTS_PATH（unity_exit=$unity_exit）"
    echo "日志：$LOG_PATH"
    FAILED_FIXTURES+=("$name")
    SUMMARY_LINES+=("$name	MISSING	0	1	0")
    TOTAL_FAILED=$((TOTAL_FAILED + 1))
    continue
  fi

  counts="$(parse_xml_counts "$RESULTS_PATH")"
  result="$(echo "$counts" | cut -f1)"
  passed="$(echo "$counts" | cut -f2)"
  failed="$(echo "$counts" | cut -f3)"
  total="$(echo "$counts" | cut -f4)"
  SUMMARY_LINES+=("$name	$result	$passed	$failed	$total")
  TOTAL_FAILED=$((TOTAL_FAILED + failed))

  echo "XML: result=$result passed=$passed failed=$failed total=$total"
  if [[ "$failed" != "0" ]]; then
    echo "FAIL: $name failed=$failed"
    FAILED_FIXTURES+=("$name")
    # 列出失败用例
    /usr/bin/python3 - "$RESULTS_PATH" <<'PY' || true
import sys, xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
for tc in root.iter("test-case"):
    if tc.attrib.get("result") == "Failed":
        print("  FAIL", tc.attrib.get("fullname"))
PY
  elif [[ "$unity_exit" -ne 0 ]]; then
    # XML failed=0 为准；若 Unity 非零但无失败用例，仍记警告但不算矩阵失败
    echo "WARN: Unity exit=$unity_exit 但 XML failed=0，按门禁视为通过"
  fi
done

echo ""
echo "======== matrix summary ========"
printf '%s\n' "fixture	result	passed	failed	total"
for line in "${SUMMARY_LINES[@]}"; do
  printf '%s\n' "$line"
done
echo "sum_failed=$TOTAL_FAILED"

if [[ "$TOTAL_FAILED" -ne 0 || ${#FAILED_FIXTURES[@]} -ne 0 ]]; then
  echo "矩阵失败：${FAILED_FIXTURES[*]:-unknown}"
  exit 1
fi

echo "矩阵全部通过（XML failed 合计为 0）"
exit 0
