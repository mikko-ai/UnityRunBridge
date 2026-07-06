# UnityRunBridge

UnityRunBridge 提供一个轻量级的 Editor-only Unity 包和一个 Python CLI，用于通过脚本或 Agent 控制本地 Unity Editor 实例。

当前功能范围：

- 启动 Unity Editor 进程。
- 通过本地 HTTP 桥接查询 Editor 状态（含编译状态、Play Mode 状态）。
- 进入、停止、暂停和恢复 Play Mode，命令会等待 Unity 真正收敛到目标状态才返回。
- 打开 Unity 项目中的场景。
- 触发脚本重编译并等待结果（`unityctl refresh`）。
- 诊断本机环境与 Bridge 连通性（`unityctl doctor`）。

Bridge 在 Unity Editor 内监听 `127.0.0.1` 上的某个端口（默认从 `17890` 开始，被占用会自动顺延），实际端口和鉴权 token 由 Unity 写入项目内的 `.unity-agent/bridge.json` 握手文件，CLI 会自动读取，不需要手动配置。

## 环境要求

- Unity Editor `2022.3` 或更高版本。
- Python `3.11` 或更高版本。
- `uv` 用于 Python 依赖管理和命令执行。

## 添加 Unity 包

将包添加到 Unity 项目的 `Packages/manifest.json` 中。推荐直接使用 `unityctl init`：它会检测 manifest 是否已包含 bridge 包依赖，缺失时询问是否写入（详见下文「初始化 Unity Project」）。也可以按以下方式手动添加。

### 正式引用（推荐）

通过 GitHub 远端地址引用已发布的 UPM 包：

```json
{
  "dependencies": {
    "com.mk.unity-agent-bridge": "https://github.com/mikko-ai/UnityRunBridge.git#upm/vX.Y.Z"
  }
}
```

将 `upm/vX.Y.Z` 替换为需要的版本 tag（例如 `upm/v0.1.0`）。该包仅在 Editor 下运行，并在 Unity Editor 加载时启动本地桥接服务。

### 本地开发

在本仓库内开发包时，可使用 `file:` 引用：

```json
{
  "dependencies": {
    "com.mk.unity-agent-bridge": "file:/absolute/path/to/UnityRunBridge/packages/com.mk.unity-agent-bridge"
  }
}
```

请使用本仓库在你机器上的绝对路径。

## 安装 CLI

### 从 GitHub Release 安装（正式）

在 [GitHub Releases](https://github.com/mikko-ai/UnityRunBridge/releases) 页面找到对应版本，使用 wheel 安装：

```bash
uv tool install --force https://github.com/mikko-ai/UnityRunBridge/releases/download/vX.Y.Z/unity_run_bridge-X.Y.Z-py3-none-any.whl
```

将 `vX.Y.Z` 和 wheel 文件名替换为实际版本。安装后验证：

```bash
unityctl --version
```

### 本地开发安装

本地开发安装：

```bash
cd /absolute/path/to/UnityRunBridge
uv tool install --editable ./src/unityctl
```

安装后可以在任意目录运行：

```bash
unityctl --help
```

开发调试 CLI 时，也可以继续在 `src/unityctl` 下使用低层开发命令：

```bash
cd src/unityctl
uv run unityctl --help
```

## 命令参考

所有命令以 JSON 输出。全局选项 `--project PATH` 可指定 Unity 项目根目录（默认从当前目录向上查找）。

| 命令 | 说明 |
| --- | --- |
| `init` | 初始化 `.unity-agent` 配置目录 |
| `config show` | 输出合并后的有效配置 |
| `config validate` | 校验 `config.json` 与 `config.local.json` |
| `config set-local KEY VALUE` | 更新本机配置字段 |
| `start` | 启动 Unity Editor（默认等待 Bridge 握手） |
| `status` | 查询 Editor 状态（编译、Play Mode、当前场景等） |
| `play` | 进入 Play Mode（可选 `--session` 记录运行日志） |
| `stop` | 退出 Play Mode（可选 `--latest` 生成 summary） |
| `pause` / `resume` | 暂停 / 恢复 Play Mode |
| `open-scene PATH` | 在 Editor 中打开场景 |
| `refresh` | 触发脚本重编译并等待完成 |
| `logs` / `errors` / `summary` | 读取 session 日志、错误与 summary |
| `doctor` | 诊断项目配置与 Bridge 连通性 |
| `skills init` / `skills update` | 安装 / 更新 agent skill（SKILL.md） |

查看完整参数说明：

```bash
unityctl --help
unityctl play --help
unityctl config --help
```

## 初始化 Unity Project

在 Unity 项目根目录执行。Unity 项目根目录指包含 `Assets`、`Packages` 和 `ProjectSettings` 的目录：

```bash
cd /absolute/path/to/UnityProject
unityctl init
```

`init` 会展示检测到的 Unity project root，并要求确认后才写入文件。脚本或 CI 中可以使用 `unityctl init --yes`。

`unityctl init` 会创建：

```text
.unity-agent/config.json
.unity-agent/config.local.json
.unity-agent/schemas/*.json
```

如果已经初始化，`init` 只补缺失文件，不会覆盖已有的 `config.json` / `config.local.json`（内置 schema 文件除外，它们总是被刷新）。`config.json` 保存可提交的项目配置，例如 Unity 版本、Bridge 期望端口和超时时间。`config.local.json` 保存本机配置，例如 Unity 可执行文件路径，应被 `.gitignore` 忽略。

`init` 还会检测 `Packages/manifest.json` 是否已包含 `com.mk.unity-agent-bridge` 依赖：

- 已存在：保持不动，输出 `"packageAction": "already_installed"`。
- 缺失且在交互终端中：询问是否写入，同意后写入依赖（默认引用与 CLI 版本一致的 `upm/vX.Y.Z` tag）。
- 缺失且非交互（含 `--yes`）：默认不修改 manifest，仅在 `nextSteps` 中提示。

相关参数：

```bash
unityctl init --install-package                 # 缺失时直接写入，不询问（适合脚本/CI，可与 --yes 组合）
unityctl init --no-install-package              # 跳过 manifest 检测与写入
unityctl init --install-package --package-ref "file:/absolute/path/to/pkg.tgz"  # 自定义依赖引用
```

配置文件是纯 JSON，不支持注释；字段说明见 `.unity-agent/schemas/config.schema.json` 和 `config.local.schema.json`。

校验配置：

```bash
unityctl config validate
```

查看有效配置：

```bash
unityctl config show
```

更新本机 Unity 路径：

```bash
unityctl config set-local unityExecutablePath "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity"
```

## 启动 Unity

```bash
unityctl start
```

默认会等待 Unity Editor 完成握手（写出 `bridge.json` 并可被连接）。若项目已在运行且 Bridge 可达，重复执行会直接返回 `already_running`，不会重复启动 Unity 进程。需要只启动 Unity 进程时：

```bash
unityctl start --no-wait
```

启动成功后，Unity 日志中会出现类似：

```text
Unity Agent Bridge listening on http://127.0.0.1:17890/
```

## 控制 Editor

在 Unity 项目根目录或其子目录执行：

```bash
unityctl status
unityctl play
unityctl pause
unityctl resume
unityctl stop
unityctl open-scene "Assets/Scenes/Login.unity"
unityctl refresh
unityctl doctor
```

所有命令均输出 JSON。成功响应中包含 `"ok": true`。`play`/`stop`/`refresh` 会轮询 Unity 状态直到收敛（进入/退出 Play Mode、编译完成），可以用 `--timeout` 覆盖配置中的默认超时，用 `--no-wait`（`refresh` 除外）跳过等待。

## Session-based 运行观测

运行带 session 的 Play Mode：

```bash
unityctl play \
  --session login-flow \
  --scene Assets/Scenes/Login.unity \
  --task "verify login flow"
```

CLI 会在 Unity 项目下创建：

```text
<ProjectRoot>/.unity-agent/sessions/<sessionId>/
  session.json
  unity-console.jsonl
```

停止并生成 `summary.json`：

```bash
unityctl stop --latest
```

如果收敛过程中出现编译失败、超时或 Unity Editor 意外退出，`session.json` 的 `status` 会被标记为 `failed` 并记录 `failedReason`，同时仍然会生成对应的 `summary.json`。

查看日志和 summary：

```bash
unityctl logs --latest --limit 100
unityctl errors --latest
unityctl summary --latest
```

也可以显式指定 session 目录：

```bash
unityctl summary --session-path "/absolute/path/to/UnityProject/.unity-agent/sessions/2026-07-02_100000_login-flow"
```

可选 ignore rules：

```json
{
  "ignore": [
    {
      "type": "Error",
      "messageContains": "Expected test error"
    }
  ]
}
```

将 ignore rules 保存到 Unity 项目的 `.unity-agent/log-rules.json`。`errors` 命令与 `summary` 命令共用同一套分类逻辑，口径保持一致，只支持 `ignore`，匹配字段为 `type` 和 `messageContains`。

## Agent Skill

CLI 内置了一份 `unityctl` 的 agent skill（SKILL.md），用自然语言描述"改代码 → refresh → play → summary"的标准 Unity 验证流程，供 Cursor、Claude Code 等 coding agent 学习使用。

在 Unity 项目根目录（或其子目录）安装：

```bash
unityctl skills init
```

默认安装到 Unity 项目的 `.agents/skills/unityctl/SKILL.md`。可以用 `--target` 指定其他 skills 根目录，相对路径基于项目根目录解析，也支持绝对路径：

```bash
unityctl skills init --target .cursor/skills          # 安装到项目的 .cursor/skills/
unityctl skills init --target ~/.claude/skills        # 安装到全局目录（绝对路径不要求在 Unity 项目内执行）
```

行为语义与 `init` / schema 一致：

- `skills init`：已存在时不覆盖，返回 `already_installed`。
- `skills update`：总是刷新为当前 CLI 版本内置内容（未安装则直接安装）；升级 CLI 后运行一次即可同步 skill。

skill 的 frontmatter 中带有 `x-unityctl-version` 字段，记录生成它的 CLI 版本。

## 数据契约与示例

`schemas/` 固定了落盘文件和运行时文件的数据契约：

```text
schemas/config.schema.json
schemas/config.local.schema.json
schemas/bridge.schema.json
schemas/session.schema.json
schemas/unity-console-log.schema.json
schemas/summary.schema.json
schemas/log-rules.schema.json
```

`examples/` 提供最小可读样例：

```text
examples/unity-project-manifest/manifest.json
examples/log-rules.json
examples/sessions/session.json
examples/sessions/unity-console.jsonl
examples/sessions/summary.json
examples/unity-agent-config/config.json
examples/unity-agent-config/config.local.json
examples/unity-agent-config/bridge.json
```

## 运行测试

Python 测试：

```bash
cd src/unityctl
uv run pytest tests -v
```

也可以从仓库根目录运行脚本：

```bash
scripts/run-python-tests.sh
```

Unity EditMode 测试，在仓库根目录下执行：

```bash
cd "$REPO_ROOT"
mkdir -p "$REPO_ROOT/.tmp/logs" "$REPO_ROOT/.tmp/test-results"

"$UNITY_BIN" \
  -batchmode \
  -projectPath "$REPO_ROOT/.tmp/unity-test-project" \
  -runTests \
  -testPlatform EditMode \
  -testResults "$REPO_ROOT/.tmp/test-results/editmode.xml" \
  -logFile "$REPO_ROOT/.tmp/logs/editmode.log"
```

Unity 测试命令**故意不传** `-quit` 参数；Unity 在测试运行写入结果 XML 后会自动退出。

也可以使用脚本运行。未设置 `UNITY_PROJECT` 时，脚本会使用仓库内
`.tmp/unity-test-project` 作为临时 Unity project：

```bash
export UNITY_BIN="/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity"
scripts/run-unity-editmode-tests.sh
```

## 本地模拟正式安装

在发布前验证 Release 产物安装路径：

```bash
scripts/install-local.sh
```

可选传入 Unity 项目路径，脚本会把 manifest 依赖改为 `file:<tgz绝对路径>`：

```bash
scripts/install-local.sh /absolute/path/to/UnityProject
```

脚本会：

1. 打包 UPM `.tgz` 到 `.tmp/packages/`
2. 构建 Python wheel
3. 用 `uv tool install --force <wheel>` 安装 CLI
4. 打印 `unityctl --version` 验证结果

## 打包 UPM

从仓库根目录运行：

```bash
scripts/package-upm.sh
```

产物默认写入 `.tmp/packages/`，也可以通过 `DIST_DIR` 指定输出目录：

```bash
DIST_DIR="$REPO_ROOT/.tmp/release" scripts/package-upm.sh
```

### 发布流程

1. 在 `main` 分支执行版本升级脚本（会同步更新 Unity 包与 Python 工具版本、commit 并打 tag）：

```bash
scripts/bump-version.sh patch
# 或 minor / major
# 仅本地完成、不 push：scripts/bump-version.sh patch --no-push
```

2. 脚本默认 push `main` 与 `vX.Y.Z` tag；GitHub Actions 会自动：
   - 校验 tag 位于 `main` 历史上
   - 校验 tag 与 `package.json` / `pyproject.toml` / `__init__.py` 版本一致
   - 运行 Python 测试
   - 将包切出到 `upm` 分支，并创建 `upm/vX.Y.Z` tag
   - 创建 GitHub Release，附带 UPM `.tgz`、Python wheel 与 sdist

发布后，Unity 项目可通过以下方式引用：

```json
"com.mk.unity-agent-bridge": "https://github.com/mikko-ai/UnityRunBridge.git#upm/vX.Y.Z"
```

Python CLI 可从同一 Release 的 wheel 安装（见上文「从 GitHub Release 安装」）。
