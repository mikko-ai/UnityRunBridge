#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UNITY_BIN="${UNITY_BIN:-}"
UNITY_PROJECT="${UNITY_PROJECT:-$REPO_ROOT/.tmp/unity-test-project}"
RESULTS_PATH="${UNITY_TEST_RESULTS:-$REPO_ROOT/.tmp/test-results/unity-agent-bridge-editmode.xml}"
LOG_PATH="${UNITY_LOG_FILE:-$REPO_ROOT/.tmp/logs/unity-agent-bridge-editmode.log}"
PACKAGE_PATH="$REPO_ROOT/packages/com.mk.unity-agent-bridge"
DEFAULT_FIXTURE="$REPO_ROOT/.tmp/unity-test-project"
NOUGUI_FIXTURE="$REPO_ROOT/.tmp/unity-nougui-fixture"

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

# 空 ProjectSettings 会被 Unity 当成新工程并注入默认 UPM（含 ugui/TMP）。
# 用已初始化的完整 fixture 的 ProjectSettings 种子化，再覆盖成目标 manifest。
seed_project_settings() {
  local target="$1"
  mkdir -p "$target/Assets" "$target/Packages" "$target/ProjectSettings"
  if [[ -d "$DEFAULT_FIXTURE/ProjectSettings" && "$target" != "$DEFAULT_FIXTURE" ]]; then
    rsync -a --delete "$DEFAULT_FIXTURE/ProjectSettings/" "$target/ProjectSettings/"
  elif [[ ! -f "$target/ProjectSettings/ProjectVersion.txt" ]]; then
    cat > "$target/ProjectSettings/ProjectVersion.txt" <<'EOF'
m_EditorVersion: 2022.3.62f2
m_EditorVersionWithRevision: 2022.3.62f2 (7670c08855a9)
EOF
  fi
  # 避免沿用旧 lock 把 ugui 等依赖重新钉死。
  rm -f "$target/Packages/packages-lock.json"
}

# 默认完整 fixture：显式安装 ugui，保证 interaction/recording Adapter 可编译（33 routes / 9 capabilities）。
if [[ "$UNITY_PROJECT" == "$DEFAULT_FIXTURE" ]]; then
  echo "使用仓库内临时 Unity project（完整 UGUI fixture）：$UNITY_PROJECT"
  seed_project_settings "$UNITY_PROJECT"
  cat > "$UNITY_PROJECT/Packages/manifest.json" <<JSON
{
  "dependencies": {
    "com.mk.unity-agent-bridge": "file:$PACKAGE_PATH",
    "com.unity.test-framework": "1.1.33",
    "com.unity.ugui": "1.0.0"
  },
  "testables": [
    "com.mk.unity-agent-bridge"
  ]
}
JSON
  mkdir -p "$UNITY_PROJECT/Assets"
  printf 'legacy\n' > "$UNITY_PROJECT/Assets/MkBridgeInputFixture.txt"
fi

# 真实 NoUGUI fixture：不安装 ugui/TMP/InputSystem，验证 25 routes / 7 capabilities。
if [[ "$UNITY_PROJECT" == "$NOUGUI_FIXTURE" ]]; then
  echo "使用仓库内临时 Unity project（NoUGUI fixture）：$UNITY_PROJECT"
  seed_project_settings "$UNITY_PROJECT"
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
  mkdir -p "$UNITY_PROJECT/Assets"
  printf 'legacy\n' > "$UNITY_PROJECT/Assets/MkBridgeInputFixture.txt"
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
