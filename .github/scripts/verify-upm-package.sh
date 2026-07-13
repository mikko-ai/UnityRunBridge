#!/usr/bin/env bash
# 校验：仓库根 schemas/ 与 unityctl 打包 schemas/ 字节一致；UPM tgz 含全部 asmdef+.meta。
# 用法：
#   bash .github/scripts/verify-upm-package.sh
#   bash .github/scripts/verify-upm-package.sh /path/to/com.mk.unity-agent-bridge-VERSION.tgz
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PACKAGE_DIR="$REPO_ROOT/packages/com.mk.unity-agent-bridge"
ROOT_SCHEMAS="$REPO_ROOT/schemas"
PKG_SCHEMAS="$REPO_ROOT/src/unityctl/unityctl/schemas"

echo "== 校验 schema 两份字节一致 =="
missing=0
for schema in "$ROOT_SCHEMAS"/*.json; do
  [[ -f "$schema" ]] || continue
  name="$(basename "$schema")"
  other="$PKG_SCHEMAS/$name"
  if [[ ! -f "$other" ]]; then
    echo "缺少打包副本：$other"
    missing=1
    continue
  fi
  if ! cmp -s "$schema" "$other"; then
    echo "字节不一致：$name"
    missing=1
  else
    echo "  OK $name"
  fi
done

for schema in "$PKG_SCHEMAS"/*.json; do
  [[ -f "$schema" ]] || continue
  name="$(basename "$schema")"
  other="$ROOT_SCHEMAS/$name"
  if [[ ! -f "$other" ]]; then
    echo "根 schemas 缺少：$name（打包侧存在）"
    missing=1
  fi
done

if [[ "$missing" -ne 0 ]]; then
  exit 1
fi
echo "schema 校验通过"

ARCHIVE="${1:-}"
if [[ -z "$ARCHIVE" ]]; then
  VERSION="$(
    python3 - "$PACKAGE_DIR/package.json" <<'PY'
import json, sys
from pathlib import Path
print(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["version"])
PY
  )"
  ARCHIVE="$REPO_ROOT/.tmp/packages/com.mk.unity-agent-bridge-$VERSION.tgz"
fi

if [[ ! -f "$ARCHIVE" ]]; then
  echo "找不到 tarball：$ARCHIVE（请先运行 scripts/package-upm.sh）"
  exit 2
fi

echo "== 校验 tgz 含全部 asmdef + .meta =="
EXPECTED_FILE="$(mktemp)"
trap 'rm -f "$EXPECTED_FILE"; rm -rf "${TMP:-}"' EXIT
find "$PACKAGE_DIR" -name '*.asmdef' | sed "s|^$PACKAGE_DIR/||" | sort > "$EXPECTED_FILE"
if [[ ! -s "$EXPECTED_FILE" ]]; then
  echo "源包内未找到任何 .asmdef"
  exit 1
fi

TMP="$(mktemp -d)"
tar -tzf "$ARCHIVE" > "$TMP/listing.txt"

fail=0
asmdef_count=0
while IFS= read -r rel; do
  [[ -n "$rel" ]] || continue
  asmdef_count=$((asmdef_count + 1))
  entry="package/$rel"
  meta_entry="package/${rel}.meta"
  if ! grep -Fxq "$entry" "$TMP/listing.txt"; then
    echo "tgz 缺少：$entry"
    fail=1
  fi
  if ! grep -Fxq "$meta_entry" "$TMP/listing.txt"; then
    echo "tgz 缺少：$meta_entry"
    fail=1
  fi
done < "$EXPECTED_FILE"

if [[ "$fail" -ne 0 ]]; then
  exit 1
fi

echo "asmdef 数量：$asmdef_count"

echo "== 校验 tgz 含 CHANGELOG.md =="
if ! grep -Fxq "package/CHANGELOG.md" "$TMP/listing.txt"; then
  echo "tgz 缺少：package/CHANGELOG.md"
  exit 1
fi
echo "  OK package/CHANGELOG.md"

echo "tgz 校验通过：$ARCHIVE"
