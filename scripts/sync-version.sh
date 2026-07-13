#!/usr/bin/env bash
# 将仓库内各组件版本字段同步到指定版本（无 git commit / tag / push）。
# 用法：bash scripts/sync-version.sh <version>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PACKAGE_JSON="$REPO_ROOT/packages/com.mk.unity-agent-bridge/package.json"
BRIDGE_CONFIG="$REPO_ROOT/packages/com.mk.unity-agent-bridge/Editor/Core/BridgeConfig.cs"
PYPROJECT="$REPO_ROOT/src/unityctl/pyproject.toml"
INIT_PY="$REPO_ROOT/src/unityctl/unityctl/__init__.py"
UNITYCTL_DIR="$REPO_ROOT/src/unityctl"

usage() {
  cat <<'EOF'
用法：scripts/sync-version.sh <version>

将 package.json、BridgeConfig.Version、pyproject.toml、__init__.__version__
与 uv.lock 同步到指定语义化版本。不执行 git commit / tag / push。

示例：
  scripts/sync-version.sh 0.3.0
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

case "$1" in
  -h|--help)
    usage
    exit 0
    ;;
esac

NEW_VERSION="$1"
if [[ ! "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]]; then
  echo "无效版本号：$NEW_VERSION（期望如 0.3.0）"
  exit 2
fi

for path in "$PACKAGE_JSON" "$BRIDGE_CONFIG" "$PYPROJECT" "$INIT_PY"; do
  if [[ ! -f "$path" ]]; then
    echo "找不到文件：$path"
    exit 2
  fi
done

echo "同步版本 -> ${NEW_VERSION}"

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

for name, value in versions.items():
    print(f"  {name}: {value}")
print(f"版本一致：{expected}")
PY

echo "完成：已同步到 ${NEW_VERSION}（未执行 git 操作）"
