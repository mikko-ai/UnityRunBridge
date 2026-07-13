#!/usr/bin/env bash
# 从 Unity 日志中提取首个 C# 编译错误（CS####），供 CI 快速定位根因。
# 用法：bash .github/scripts/extract-unity-first-error.sh [log-dir...]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

LOG_DIRS=("$@")
if [[ ${#LOG_DIRS[@]} -eq 0 ]]; then
  LOG_DIRS=(
    "$REPO_ROOT/.tmp/logs/matrix"
    "$REPO_ROOT/.tmp/logs"
  )
fi

found=0
for dir in "${LOG_DIRS[@]}"; do
  if [[ ! -d "$dir" ]]; then
    continue
  fi
  while IFS= read -r -d '' log; do
    match="$(
      /usr/bin/python3 - "$log" <<'PY'
import re, sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
# 形如 Assets/Foo.cs(12,34): error CS0103: ...
pat = re.compile(r"^.*\.cs\(\d+,\d+\):\s*error\s+CS\d+:.*$", re.MULTILINE)
m = pat.search(text)
if m:
    print(m.group(0).strip())
PY
    )" || true
    if [[ -n "${match:-}" ]]; then
      echo "=== 首个 C# 编译错误（来自 $(basename "$log")）==="
      echo "$match"
      found=1
      exit 0
    fi
  done < <(find "$dir" -type f -name '*.log' -print0 2>/dev/null | sort -z)
done

if [[ "$found" -eq 0 ]]; then
  echo "未在日志中找到 CS 编译错误行（可能为测试失败而非编译失败）"
fi
exit 0
