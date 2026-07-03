#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PACKAGE_JSON="$REPO_ROOT/packages/com.mk.unity-agent-bridge/package.json"
BRIDGE_CONFIG="$REPO_ROOT/packages/com.mk.unity-agent-bridge/Editor/BridgeConfig.cs"
PYPROJECT="$REPO_ROOT/src/unityctl/pyproject.toml"
INIT_PY="$REPO_ROOT/src/unityctl/unityctl/__init__.py"
UNITYCTL_DIR="$REPO_ROOT/src/unityctl"

usage() {
  cat <<'EOF'
用法：scripts/bump-version.sh {patch|minor|major} [--no-push]

  patch   递增 patch 版本（0.1.0 -> 0.1.1）
  minor   递增 minor 版本（0.1.0 -> 0.2.0）
  major   递增 major 版本（0.1.0 -> 1.0.0）
  --no-push  仅本地 commit + tag，不 push

示例：
  scripts/bump-version.sh patch
  scripts/bump-version.sh minor --no-push
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

BUMP_KIND="$1"
NO_PUSH=false
shift

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-push)
      NO_PUSH=true
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

case "$BUMP_KIND" in
  patch|minor|major) ;;
  *)
    echo "无效的 bump 类型：$BUMP_KIND（应为 patch、minor 或 major）"
    usage
    exit 2
    ;;
esac

if [[ ! -f "$PACKAGE_JSON" ]]; then
  echo "找不到 Unity package manifest：$PACKAGE_JSON"
  exit 2
fi

if ! git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "当前目录不是 git 仓库：$REPO_ROOT"
  exit 2
fi

if [[ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]]; then
  echo "工作区不干净，请先提交或 stash 本地改动。"
  git -C "$REPO_ROOT" status --short
  exit 2
fi

CURRENT_BRANCH="$(git -C "$REPO_ROOT" branch --show-current)"
if [[ "$CURRENT_BRANCH" != "main" ]]; then
  echo "当前分支为 $CURRENT_BRANCH，bump 必须在 main 分支执行。"
  exit 2
fi

echo "同步远端 main..."
git -C "$REPO_ROOT" fetch origin main

LOCAL_HEAD="$(git -C "$REPO_ROOT" rev-parse HEAD)"
REMOTE_HEAD="$(git -C "$REPO_ROOT" rev-parse origin/main)"
if [[ "$LOCAL_HEAD" != "$REMOTE_HEAD" ]]; then
  echo "本地 main 与 origin/main 不一致。"
  echo "  local:  $LOCAL_HEAD"
  echo "  remote: $REMOTE_HEAD"
  echo "请先 pull 或 push，使 main 与远端同步后再 bump。"
  exit 2
fi

read -r CURRENT_VERSION NEW_VERSION <<< "$(python3 - "$BUMP_KIND" "$PACKAGE_JSON" <<'PY'
import json
import re
import sys
from pathlib import Path

bump_kind = sys.argv[1]
package_json = Path(sys.argv[2])

payload = json.loads(package_json.read_text(encoding="utf-8"))
match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", payload["version"])
if not match:
    raise SystemExit(f"无法解析 package.json 版本：{payload['version']}")

major, minor, patch = (int(part) for part in match.groups())
if bump_kind == "patch":
    patch += 1
elif bump_kind == "minor":
    minor += 1
    patch = 0
elif bump_kind == "major":
    major += 1
    minor = 0
    patch = 0
else:
    raise SystemExit(f"无效的 bump 类型：{bump_kind}")

current = payload["version"]
new_version = f"{major}.{minor}.{patch}"
print(f"{current} {new_version}")
PY
)"

TAG_NAME="v${NEW_VERSION}"

if git -C "$REPO_ROOT" rev-parse "$TAG_NAME" >/dev/null 2>&1; then
  echo "tag 已存在：$TAG_NAME"
  exit 2
fi

echo "版本升级：${CURRENT_VERSION} -> ${NEW_VERSION} (${BUMP_KIND})"

python3 - "$NEW_VERSION" "$PACKAGE_JSON" "$BRIDGE_CONFIG" "$PYPROJECT" "$INIT_PY" <<'PY'
import json
import re
import sys
from pathlib import Path

new_version = sys.argv[1]
paths = {
    "package.json": Path(sys.argv[2]),
    "BridgeConfig.cs": Path(sys.argv[3]),
    "pyproject.toml": Path(sys.argv[4]),
    "__init__.py": Path(sys.argv[5]),
}

package_payload = json.loads(paths["package.json"].read_text(encoding="utf-8"))
package_payload["version"] = new_version
paths["package.json"].write_text(
    json.dumps(package_payload, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

bridge_config = paths["BridgeConfig.cs"].read_text(encoding="utf-8")
bridge_config, count = re.subn(
    r'public const string Version = "[^"]+";',
    f'public const string Version = "{new_version}";',
    bridge_config,
    count=1,
)
if count != 1:
    raise SystemExit("未能更新 BridgeConfig.cs 中的 Version 常量")
paths["BridgeConfig.cs"].write_text(bridge_config, encoding="utf-8")

pyproject = paths["pyproject.toml"].read_text(encoding="utf-8")
pyproject, count = re.subn(
    r'^version = "[^"]+"$',
    f'version = "{new_version}"',
    pyproject,
    count=1,
    flags=re.MULTILINE,
)
if count != 1:
    raise SystemExit("未能更新 pyproject.toml 中的 version")
paths["pyproject.toml"].write_text(pyproject, encoding="utf-8")

init_py = paths["__init__.py"].read_text(encoding="utf-8")
init_py, count = re.subn(
    r'^__version__ = "[^"]+"$',
    f'__version__ = "{new_version}"',
    init_py,
    count=1,
    flags=re.MULTILINE,
)
if count != 1:
    raise SystemExit("未能更新 __init__.py 中的 __version__")
paths["__init__.py"].write_text(init_py, encoding="utf-8")
PY

echo "更新 uv.lock..."
(
  cd "$UNITYCTL_DIR"
  uv lock
)

echo "校验版本一致性..."
python3 - "$NEW_VERSION" "$PACKAGE_JSON" "$BRIDGE_CONFIG" "$PYPROJECT" "$INIT_PY" <<'PY'
import json
import re
import sys
from pathlib import Path

expected = sys.argv[1]
package_json = Path(sys.argv[2])
bridge_config = Path(sys.argv[3])
pyproject = Path(sys.argv[4])
init_py = Path(sys.argv[5])

package_version = json.loads(package_json.read_text(encoding="utf-8"))["version"]
bridge_match = re.search(
    r'public const string Version = "([^"]+)";',
    bridge_config.read_text(encoding="utf-8"),
)
pyproject_match = re.search(
    r'^version = "([^"]+)"$',
    pyproject.read_text(encoding="utf-8"),
    flags=re.MULTILINE,
)
init_match = re.search(
    r'^__version__ = "([^"]+)"$',
    init_py.read_text(encoding="utf-8"),
    flags=re.MULTILINE,
)

if bridge_match is None or pyproject_match is None or init_match is None:
    raise SystemExit("版本校验失败：未能读取某个版本字段")

versions = {
    "package.json": package_version,
    "BridgeConfig.cs": bridge_match.group(1),
    "pyproject.toml": pyproject_match.group(1),
    "__init__.py": init_match.group(1),
}

mismatch = {name: value for name, value in versions.items() if value != expected}
if mismatch:
    print("版本不一致：")
    for name, value in mismatch.items():
        print(f"  {name}: {value} (expected {expected})")
    raise SystemExit(1)

print(f"版本一致：{expected}")
PY

git -C "$REPO_ROOT" add \
  "$PACKAGE_JSON" \
  "$BRIDGE_CONFIG" \
  "$PYPROJECT" \
  "$INIT_PY" \
  "$UNITYCTL_DIR/uv.lock"

git -C "$REPO_ROOT" commit -m "release: ${TAG_NAME}"
git -C "$REPO_ROOT" tag "$TAG_NAME"

echo "已创建 commit 与 tag：${TAG_NAME}"

if [[ "$NO_PUSH" == true ]]; then
  cat <<EOF

未 push。确认无误后执行：
  git push origin main
  git push origin ${TAG_NAME}
EOF
  exit 0
fi

echo "推送 main 与 tag..."
git -C "$REPO_ROOT" push origin main
git -C "$REPO_ROOT" push origin "$TAG_NAME"

echo "完成：${TAG_NAME} 已推送，GitHub Actions 将自动发布 Release。"
