#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "用法：.github/scripts/create-github-release.sh <upm-tgz> <wheel> <sdist>"
  exit 2
fi

ARCHIVE_PATH="$1"
WHEEL_PATH="$2"
SDIST_PATH="$3"

for asset in "$ARCHIVE_PATH" "$WHEEL_PATH" "$SDIST_PATH"; do
  if [[ ! -f "$asset" ]]; then
    echo "Release 资产不存在：$asset"
    exit 1
  fi
done

TAG_NAME="${GITHUB_REF_NAME:?缺少 GITHUB_REF_NAME}"
REPOSITORY="${GITHUB_REPOSITORY:?缺少 GITHUB_REPOSITORY}"
VERSION="${TAG_NAME#v}"
WHEEL_FILE="$(basename "$WHEEL_PATH")"

RELEASE_NOTES="$(cat <<EOF
## 安装

### Unity UPM 包

\`\`\`json
"com.mk.unity-agent-bridge": "https://github.com/${REPOSITORY}.git#upm/v${VERSION}"
\`\`\`

或下载 \`com.mk.unity-agent-bridge-${VERSION}.tgz\` 后通过 \`file:\` 引用。

### Python CLI (unityctl)

\`\`\`bash
uv tool install --force https://github.com/${REPOSITORY}/releases/download/${TAG_NAME}/${WHEEL_FILE}
\`\`\`

也可下载 wheel/sdist 后本地安装：

\`\`\`bash
uv tool install --force /path/to/${WHEEL_FILE}
\`\`\`
EOF
)"

ASSETS=("$ARCHIVE_PATH" "$WHEEL_PATH" "$SDIST_PATH")

if gh release view "$TAG_NAME" >/dev/null 2>&1; then
  gh release upload "$TAG_NAME" --clobber "${ASSETS[@]}"
else
  gh release create "$TAG_NAME" \
    --title "$TAG_NAME" \
    --notes "$RELEASE_NOTES" \
    "${ASSETS[@]}"
fi
