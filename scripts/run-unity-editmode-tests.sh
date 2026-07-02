#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UNITY_BIN="${UNITY_BIN:-}"
UNITY_PROJECT="${UNITY_PROJECT:-$REPO_ROOT/.tmp/unity-test-project}"
RESULTS_PATH="${UNITY_TEST_RESULTS:-$REPO_ROOT/.tmp/test-results/unity-agent-bridge-editmode.xml}"
LOG_PATH="${UNITY_LOG_FILE:-$REPO_ROOT/.tmp/logs/unity-agent-bridge-editmode.log}"
PACKAGE_PATH="$REPO_ROOT/packages/com.mk.unity-agent-bridge"

if [[ -z "$UNITY_BIN" ]]; then
  echo "请先设置 UNITY_BIN，例如："
  echo "export UNITY_BIN=\"/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity\""
  exit 2
fi

if [[ "$UNITY_BIN" == *.app ]]; then
  UNITY_BIN="$UNITY_BIN/Contents/MacOS/Unity"
fi

if [[ ! -x "$UNITY_BIN" ]]; then
  echo "UNITY_BIN 不可执行：$UNITY_BIN"
  exit 2
fi

mkdir -p "$(dirname "$RESULTS_PATH")" "$(dirname "$LOG_PATH")"

if [[ "$UNITY_PROJECT" == "$REPO_ROOT/.tmp/unity-test-project" ]]; then
  echo "使用仓库内临时 Unity project：$UNITY_PROJECT"
  mkdir -p "$UNITY_PROJECT/Assets" "$UNITY_PROJECT/Packages" "$UNITY_PROJECT/ProjectSettings"
  cat > "$UNITY_PROJECT/Packages/manifest.json" <<JSON
{
  "dependencies": {
    "com.mk.unity-agent-bridge": "file:$PACKAGE_PATH",
    "com.unity.test-framework": "1.1.33"
  },
  "testables": [
    "com.mk.unity-agent-bridge"
  ]
}
JSON
fi

echo "运行 Unity EditMode tests..."
"$UNITY_BIN" \
  -batchmode \
  -projectPath "$UNITY_PROJECT" \
  -runTests \
  -testPlatform EditMode \
  -testResults "$RESULTS_PATH" \
  -logFile "$LOG_PATH"

echo "Unity EditMode results: $RESULTS_PATH"
echo "Unity log: $LOG_PATH"
