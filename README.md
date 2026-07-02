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

将包添加到 Unity 项目的 `Packages/manifest.json` 中。

### 正式引用（推荐）

通过 GitHub 远端地址引用已发布的 UPM 包：

```json
{
  "dependencies": {
    "com.mk.unity-agent-bridge": "https://github.com/mikko-ai/UnityRunBridge.git#upm/v0.1.0"
  }
}
```

将 `upm/v0.1.0` 替换为需要的版本 tag。该包仅在 Editor 下运行，并在 Unity Editor 加载时启动本地桥接服务。

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

默认会等待 Unity Editor 完成握手（写出 `bridge.json` 并可被连接）。需要只启动 Unity 进程时：

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

1. 更新 [packages/com.mk.unity-agent-bridge/package.json](packages/com.mk.unity-agent-bridge/package.json) 中的 `version`。
2. 合并到 `main` 分支。
3. 打 tag 并推送：

```bash
git tag v0.1.0
git push origin v0.1.0
```

4. GitHub Actions 会自动：
   - 校验 tag 版本与 `package.json` 一致
   - 将包切出到 `upm` 分支，并创建 `upm/vX.Y.Z` tag
   - 创建 GitHub Release，附带 `.tgz` 产物

发布后，Unity 项目可通过以下方式引用：

```json
"com.mk.unity-agent-bridge": "https://github.com/mikko-ai/UnityRunBridge.git#upm/v0.1.0"
```
