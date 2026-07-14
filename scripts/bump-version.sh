#!/usr/bin/env bash
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
用法：scripts/bump-version.sh {patch|minor|major} [--no-push] [--skip-full-tests]

  patch   递增 patch 版本（0.1.0 -> 0.1.1）
  minor   递增 minor 版本（0.1.0 -> 0.2.0）
  major   递增 major 版本（0.1.0 -> 1.0.0）
  --no-push          仅本地 commit + tag，不 push
  --skip-full-tests  提前跳过发布前全量测试（Python + Unity 全量矩阵）。
                      需要额外输入 SKIP 二次确认，不会静默跳过。

打 tag 前会询问是否运行本地全量测试（scripts/run-full-tests.sh：Python 单测 +
Unity EditMode 全量矩阵，9 种 UGUI/TMP/InputSystem 组合），默认 Yes；选择运行且
测试失败则中止，不会创建 commit/tag。这一步替代了原先跑在 GitHub Actions
self-hosted runner 上的 Unity 矩阵门禁。

执行前会显示当前版本与目标版本，需输入 y 确认后才会继续。

示例：
  scripts/bump-version.sh patch
  scripts/bump-version.sh minor --no-push
  scripts/bump-version.sh patch --skip-full-tests
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

BUMP_KIND="$1"
NO_PUSH=false
SKIP_FULL_TESTS=false
shift

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-push)
      NO_PUSH=true
      shift
      ;;
    --skip-full-tests)
      SKIP_FULL_TESTS=true
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

echo ""
echo "版本升级：${CURRENT_VERSION} -> ${NEW_VERSION} (${BUMP_KIND})"
echo "将创建 tag：${TAG_NAME}"
if [[ "$NO_PUSH" == true ]]; then
  echo "模式：仅本地 commit + tag（不 push）"
else
  echo "模式：commit + tag + push 到 origin/main"
fi
echo ""
read -r -p "确认继续？[y/N] " CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
  echo "已取消。"
  exit 0
fi

if [[ "$SKIP_FULL_TESTS" == true ]]; then
  echo ""
  echo "⚠️  已选择 --skip-full-tests：将跳过 Python + Unity 全量矩阵测试直接发布。"
  echo "⚠️  这会跳过发布前唯一的自动化正确性校验，风险自负。"
  read -r -p "确认跳过测试？输入 SKIP 继续，其他任意输入将取消： " SKIP_CONFIRM
  if [[ "$SKIP_CONFIRM" != "SKIP" ]]; then
    echo "未输入 SKIP，已取消。"
    exit 0
  fi
  echo "已跳过全量测试。"
else
  echo ""
  read -r -p "是否运行发布前全量测试（Python + Unity 全量矩阵）？[Y/n] " RUN_TESTS_CONFIRM
  if [[ -z "$RUN_TESTS_CONFIRM" || "$RUN_TESTS_CONFIRM" =~ ^[Yy]$ ]]; then
    echo ""
    echo "==> 运行发布前全量测试（scripts/run-full-tests.sh）..."
    if ! bash "$SCRIPT_DIR/run-full-tests.sh"; then
      echo ""
      echo "全量测试失败，已中止发布（未创建 commit/tag）。"
      echo "修复后重新运行，或在下一次运行时选择跳过测试。"
      exit 1
    fi
    echo "全量测试通过。"
  else
    echo "已跳过全量测试。"
  fi
fi

# 文件同步委托给无副作用的 sync-version.sh（含 uv.lock 与一致性校验）
bash "$SCRIPT_DIR/sync-version.sh" "$NEW_VERSION"

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

echo "完成：${TAG_NAME} 已推送，GitHub Actions 将校验 tag、跑 Python 测试并发布 Release。"
