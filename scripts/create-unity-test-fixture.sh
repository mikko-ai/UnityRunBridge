#!/usr/bin/env bash
# 生成独立 Unity EditMode 测试 fixture（Packages/manifest + ProjectSettings + 结果路径约定）。
# 用法：
#   bash scripts/create-unity-test-fixture.sh --ui nougui|ugui|ugui-tmp --input legacy|inputsystem|both [--force]
#   bash scripts/create-unity-test-fixture.sh --name ugui-legacy [--force]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PACKAGE_PATH="$REPO_ROOT/packages/com.mk.unity-agent-bridge"
FIXTURE_ROOT="${UNITY_FIXTURE_ROOT:-$REPO_ROOT/.tmp/unity-fixtures}"
TEMPLATE_SETTINGS="${UNITY_SETTINGS_TEMPLATE:-$REPO_ROOT/.tmp/unity-test-project/ProjectSettings}"

UI_KIND=""
INPUT_KIND=""
FIXTURE_NAME=""
FORCE=0

usage() {
  cat <<'EOF'
用法:
  create-unity-test-fixture.sh --ui nougui|ugui|ugui-tmp --input legacy|inputsystem|both [--force]
  create-unity-test-fixture.sh --name <ui>-<input> [--force]

名称约定:
  nougui-legacy | nougui-inputsystem | nougui-both
  ugui-legacy   | ugui-inputsystem   | ugui-both
  ugui-tmp-legacy | ugui-tmp-inputsystem | ugui-tmp-both
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ui) UI_KIND="$2"; shift 2 ;;
    --input) INPUT_KIND="$2"; shift 2 ;;
    --name) FIXTURE_NAME="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数: $1"; usage; exit 2 ;;
  esac
done

if [[ -n "$FIXTURE_NAME" ]]; then
  case "$FIXTURE_NAME" in
    nougui-legacy) UI_KIND=nougui; INPUT_KIND=legacy ;;
    nougui-inputsystem) UI_KIND=nougui; INPUT_KIND=inputsystem ;;
    nougui-both) UI_KIND=nougui; INPUT_KIND=both ;;
    ugui-legacy) UI_KIND=ugui; INPUT_KIND=legacy ;;
    ugui-inputsystem) UI_KIND=ugui; INPUT_KIND=inputsystem ;;
    ugui-both) UI_KIND=ugui; INPUT_KIND=both ;;
    ugui-tmp-legacy) UI_KIND=ugui-tmp; INPUT_KIND=legacy ;;
    ugui-tmp-inputsystem) UI_KIND=ugui-tmp; INPUT_KIND=inputsystem ;;
    ugui-tmp-both) UI_KIND=ugui-tmp; INPUT_KIND=both ;;
    *) echo "未知 --name: $FIXTURE_NAME"; usage; exit 2 ;;
  esac
fi

if [[ -z "$UI_KIND" || -z "$INPUT_KIND" ]]; then
  usage
  exit 2
fi

case "$UI_KIND" in
  nougui|ugui|ugui-tmp) ;;
  *) echo "无效 --ui: $UI_KIND"; exit 2 ;;
esac
case "$INPUT_KIND" in
  legacy|inputsystem|both) ;;
  *) echo "无效 --input: $INPUT_KIND"; exit 2 ;;
esac

FIXTURE_NAME="${UI_KIND}-${INPUT_KIND}"
PROJECT_PATH="$FIXTURE_ROOT/$FIXTURE_NAME"

if [[ -d "$PROJECT_PATH" && "$FORCE" != "1" ]]; then
  echo "fixture 已存在：$PROJECT_PATH（使用 --force 重建 ProjectSettings/manifest，保留 Library）"
else
  mkdir -p "$PROJECT_PATH"
fi

mkdir -p "$PROJECT_PATH/Assets" "$PROJECT_PATH/Packages" "$PROJECT_PATH/ProjectSettings"

# 种子化 ProjectSettings：优先复制完整模板，避免 Unity 当作全新工程注入默认 UPM。
if [[ -d "$TEMPLATE_SETTINGS" ]]; then
  rsync -a --delete "$TEMPLATE_SETTINGS/" "$PROJECT_PATH/ProjectSettings/"
else
  cat > "$PROJECT_PATH/ProjectSettings/ProjectVersion.txt" <<'EOF'
m_EditorVersion: 2022.3.62f2
m_EditorVersionWithRevision: 2022.3.62f2 (7670c08855a9)
EOF
fi

# 覆盖 Editor 版本钉死。
cat > "$PROJECT_PATH/ProjectSettings/ProjectVersion.txt" <<'EOF'
m_EditorVersion: 2022.3.62f2
m_EditorVersionWithRevision: 2022.3.62f2 (7670c08855a9)
EOF

# activeInputHandler: Legacy=0, InputSystem=1, Both=2
case "$INPUT_KIND" in
  legacy) ACTIVE_INPUT=0; INPUT_MARKER=legacy ;;
  inputsystem) ACTIVE_INPUT=1; INPUT_MARKER=inputsystem ;;
  both) ACTIVE_INPUT=2; INPUT_MARKER=both ;;
esac

SETTINGS_ASSET="$PROJECT_PATH/ProjectSettings/ProjectSettings.asset"
if [[ -f "$SETTINGS_ASSET" ]]; then
  /usr/bin/python3 - "$SETTINGS_ASSET" "$ACTIVE_INPUT" <<'PY'
import re, sys
path, value = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
new_text, n = re.subn(r"(activeInputHandler:\s*)\d+", r"\g<1>" + value, text)
if n == 0:
    # 模板缺字段时追加到 PlayerSettings 段末尾附近
    new_text = text.rstrip() + f"\n  activeInputHandler: {value}\n"
open(path, "w", encoding="utf-8").write(new_text)
print(f"activeInputHandler -> {value} (replacements={n})")
PY
else
  echo "警告：缺少 ProjectSettings.asset，Unity 首次打开时会生成默认设置"
fi

# 输入模式标记：Composition.InputDefinesProbeTests 读取
printf '%s\n' "$INPUT_MARKER" > "$PROJECT_PATH/Assets/MkBridgeInputFixture.txt"

# ugui-tmp fixture 需要 TMP Essential Resources，否则 TextMeshProUGUI.Awake 会在 batchmode
# 弹导入窗口并报 "No graphic device is available"。
if [[ "$UI_KIND" == "ugui-tmp" ]]; then
  TMP_SEED="$REPO_ROOT/scripts/fixtures/tmp-essential-resources"
  if [[ ! -d "$TMP_SEED" ]]; then
    echo "缺少 TMP Essential Resources 种子：$TMP_SEED"
    exit 2
  fi
  mkdir -p "$PROJECT_PATH/Assets/TextMesh Pro"
  rsync -a --delete "$TMP_SEED/" "$PROJECT_PATH/Assets/TextMesh Pro/"
  echo "已注入 TMP Essential Resources -> Assets/TextMesh Pro"
fi

# 组装 manifest dependencies
DEPS=$(/usr/bin/python3 - "$PACKAGE_PATH" "$UI_KIND" "$INPUT_KIND" <<'PY'
import json, sys
package_path, ui, input_kind = sys.argv[1], sys.argv[2], sys.argv[3]
deps = {
    "com.mk.unity-agent-bridge": f"file:{package_path}",
    "com.unity.test-framework": "1.1.33",
}
if ui in ("ugui", "ugui-tmp"):
    deps["com.unity.ugui"] = "1.0.0"
if ui == "ugui-tmp":
    deps["com.unity.textmeshpro"] = "3.0.6"
if input_kind in ("inputsystem", "both"):
    deps["com.unity.inputsystem"] = "1.7.0"
print(json.dumps({
    "dependencies": deps,
    "testables": ["com.mk.unity-agent-bridge"],
}, indent=2))
PY
)

printf '%s\n' "$DEPS" > "$PROJECT_PATH/Packages/manifest.json"
rm -f "$PROJECT_PATH/Packages/packages-lock.json"

echo "已生成 fixture：$PROJECT_PATH"
echo "  ui=$UI_KIND input=$INPUT_KIND activeInputHandler=$ACTIVE_INPUT"
echo "  marker=Assets/MkBridgeInputFixture.txt ($INPUT_MARKER)"
