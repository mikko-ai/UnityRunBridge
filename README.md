# UnityRunBridge

UnityRunBridge 提供一个轻量级的 Editor-only Unity 包和一个 Python CLI，用于通过脚本或 Agent 控制本地 Unity Editor 实例。

当前功能范围：

- 启动 Unity Editor 进程。
- 通过本地 HTTP 桥接查询 Editor 状态。
- 进入、停止、暂停和恢复 Play Mode。
- 打开 Unity 项目中的场景。

桥接服务在 Unity Editor 内监听 `http://127.0.0.1:17890`。

## 环境要求

- Unity Editor `2022.3` 或更高版本。
- Python `3.11` 或更高版本。
- `uv` 用于 Python 依赖管理和命令执行。

## 添加 Unity 包

将包添加到 Unity 项目的 `Packages/manifest.json` 中：

```json
{
  "dependencies": {
    "com.elex.unity-agent-bridge": "file:/absolute/path/to/UnityRunBridge/packages/com.elex.unity-agent-bridge"
  }
}
```

请使用本仓库在你机器上的绝对路径。该包仅在 Editor 下运行，并在 Unity Editor 加载时启动本地桥接服务。

## 安装 CLI

在本仓库中执行：

```bash
cd src/unityctl
uv sync
```

使用 `uv run unityctl ...` 运行命令。

## 配置本地路径

`UNITY_BIN` 和 `UNITY_PROJECT` 并非硬编码的项目设置，它们是以下示例中用到的普通 shell 变量，以便每台机器可以指定自己的 Unity 安装路径和 Unity 项目路径。

`UNITY_BIN` 应指向 Unity 命令行可执行文件：

```bash
export UNITY_BIN="/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity"
```

如果你从 `.app` 路径（如 `/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app`）开始，请在末尾追加 `/Contents/MacOS/Unity`。

`UNITY_PROJECT` 应指向 Unity 项目根目录，即包含 `Assets`、`Packages` 和 `ProjectSettings` 的目录：

```bash
export UNITY_PROJECT="/absolute/path/to/your/unity-project"
```

为便于重复本地运行，请将日志保存在本仓库下：

```bash
cd /absolute/path/to/UnityRunBridge
export REPO_ROOT="$(pwd)"
mkdir -p "$REPO_ROOT/.tmp/logs"
```

## 启动 Unity

在 `src/unityctl` 目录下执行：

```bash
cd "$REPO_ROOT/src/unityctl"
uv run unityctl start-editor \
  --unity "$UNITY_BIN" \
  --project "$UNITY_PROJECT" \
  --log-file "$REPO_ROOT/.tmp/logs/unity-editor.log"
```

等待 Unity 日志中出现：

```text
Unity Agent Bridge listening on http://127.0.0.1:17890/
```

## 控制 Editor

在 `src/unityctl` 目录下执行：

```bash
uv run unityctl status
uv run unityctl play
uv run unityctl pause
uv run unityctl resume
uv run unityctl stop
uv run unityctl open-scene "Assets/Scenes/Login.unity"
```

所有命令均输出 JSON。成功响应中包含 `"ok": true`。

## Session-based 运行观测

运行带 session 的 Play Mode：

```bash
cd "$REPO_ROOT/src/unityctl"
uv run unityctl play \
  --project "$UNITY_PROJECT" \
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
uv run unityctl stop \
  --project "$UNITY_PROJECT" \
  --session-path "<ProjectRoot>/.unity-agent/sessions/<sessionId>"
```

查看日志和 summary：

```bash
uv run unityctl logs --session-path "<ProjectRoot>/.unity-agent/sessions/<sessionId>" --limit 100
uv run unityctl errors --session-path "<ProjectRoot>/.unity-agent/sessions/<sessionId>"
uv run unityctl summary --session-path "<ProjectRoot>/.unity-agent/sessions/<sessionId>"
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

将 ignore rules 保存到 Unity 项目的 `.unity-agent/log-rules.json`。第一版只支持
`ignore`，匹配字段为 `type` 和 `messageContains`。

## 运行测试

Python 测试：

```bash
cd src/unityctl
uv run pytest tests -v
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
