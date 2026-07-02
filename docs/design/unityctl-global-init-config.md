# unityctl 全局命令与项目级配置设计说明

## 背景

当前 `unityctl` 已经具备启动 Unity Editor、控制 Play Mode、创建 session、捕获 Unity Console 日志并生成 `summary.json` 的能力。但是它的使用体验仍偏开发者内部工具：

- 需要进入 `UnityRunBridge/src/unityctl` 后执行 `uv run unityctl <command>`。
- 多数命令需要显式传入 `--project`、`--unity` 或手动设置 `UNITY_PROJECT`、`UNITY_BIN`。
- Bridge 地址当前默认固定为 `http://127.0.0.1:17890`，不利于同时打开多个 Unity 项目。
- Unity project 的 `.unity-agent/` 已经承载 session 文件，但还没有统一的项目配置入口。

下一阶段目标是把 `unityctl` 从“仓库内开发命令”推进到“全局可用的项目工具”。

## 目标体验

使用者安装一次 CLI 后，可以在任意 Unity project root 或其子目录中运行：

```bash
unityctl init
unityctl start
unityctl status
unityctl play --session login-flow
unityctl stop
unityctl summary --latest
```

使用者不应该在日常命令中反复传入 Unity project 路径、Unity 安装路径和 Bridge URL。项目级信息由 `.unity-agent/` 下的配置文件提供。

## 设计原则

### 1. 全局命令，项目本地状态

`unityctl` 应该是全局命令，但它操作的状态属于当前 Unity project。

全局安装只解决“命令在哪运行”的问题。项目状态仍然放在 Unity project root 下：

```text
ProjectName/
  Assets/
  Packages/
  ProjectSettings/
  .unity-agent/
```

`unityctl` 从当前工作目录向上查找 Unity project root。识别规则是同一目录下同时存在：

```text
Assets/
Packages/
ProjectSettings/
```

找到 project root 后，所有 session、log rules、project config 都在这个 root 的 `.unity-agent/` 下。

### 2. 共享配置与本机配置分离

Unity project 有两类配置：

- 项目事实：团队共享、可以提交到 Git。
- 本机事实：只对当前机器成立，不应该提交。

因此配置拆成两个文件：

```text
ProjectName/.unity-agent/config.json
ProjectName/.unity-agent/config.local.json
```

`config.json` 是可提交配置，保存项目共享事实：

```json
{
  "version": 1,
  "unityVersion": "2022.3.62f2",
  "bridge": {
    "host": "127.0.0.1",
    "port": 17890
  },
  "defaultScene": null,
  "sessionDirectory": ".unity-agent/sessions"
}
```

`config.local.json` 是本机配置，保存机器相关事实：

```json
{
  "unityAppPath": "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app"
}
```

`config.local.json` 必须默认加入 Unity project 的 ignore 规则。它可以放入：

```text
ProjectName/.gitignore
```

新增内容：

```gitignore
.unity-agent/config.local.json
```

如果目标 Unity project 不使用 Git，`unityctl init` 仍然创建 `config.local.json`，但只提示无法自动更新 ignore。

### 3. Unity 版本属于项目，Unity 路径属于本机

不同项目可能使用不同 Unity 版本，因此 `unityVersion` 应写入 `config.json`。但是 Unity 安装路径是本机事实，应写入 `config.local.json`。

`unityctl start` 的解析顺序：

1. 命令行 `--unity`。
2. `.unity-agent/config.local.json` 的 `unityAppPath` 或 `unityExecutablePath`。
3. 如果只有 `unityVersion`，尝试按常见 Unity Hub 路径推断：

```text
/Applications/Unity/Hub/Editor/<unityVersion>/Unity.app
```

推断失败时，命令返回清晰错误，提示运行：

```bash
unityctl config set-local unityAppPath "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app"
```

第一版可以支持 `.app` 路径和 `Contents/MacOS/Unity` 可执行路径。CLI 内部统一规范化为可执行路径。

### 4. Bridge URL 属于项目配置

Bridge host/port 应放在 `config.json`，不是全局配置。原因：

- 可能同时打开两个不同 Unity project。
- 不同项目可以使用不同端口，避免 `HttpListener` 端口冲突。
- Agent 在项目目录中运行时，可以从项目配置得到正确的 Bridge URL。

这要求 CLI 和 Unity package 都读取同一个项目配置：

```text
CLI
  -> 读取 .unity-agent/config.json
  -> 请求 http://<host>:<port>

Unity package
  -> 通过 Application.dataPath 找到 project root
  -> 读取 .unity-agent/config.json
  -> 使用 bridge.host + bridge.port 启动 HttpListener
```

如果配置缺失，Unity package 使用当前默认值：

```text
host = 127.0.0.1
port = 17890
```

如果端口被占用，Bridge 应输出明确日志，并让 `unityctl status` 给出可诊断错误。

### 5. `unityctl init` 是项目入口

`unityctl init` 负责把当前 Unity project 接入 UnityRunBridge 的项目级约定。

第一版命令形态：

```bash
unityctl init \
  --unity "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app" \
  --port 17891
```

行为：

1. 从当前目录向上查找 Unity project root。
2. 创建 `.unity-agent/`。
3. 写入或更新 `.unity-agent/config.json`。
4. 写入或更新 `.unity-agent/config.local.json`。
5. 确保 `.unity-agent/config.local.json` 被 ignore。
6. 检查 `Packages/manifest.json` 是否已接入 `com.elex.unity-agent-bridge`。
7. 输出下一步命令。

初始输出示例：

```json
{
  "ok": true,
  "projectPath": "/Users/example/Game",
  "configPath": "/Users/example/Game/.unity-agent/config.json",
  "localConfigPath": "/Users/example/Game/.unity-agent/config.local.json",
  "bridgeUrl": "http://127.0.0.1:17891",
  "packageInstalled": false,
  "nextSteps": [
    "Add com.elex.unity-agent-bridge to Packages/manifest.json",
    "Run unityctl start",
    "Run unityctl status"
  ]
}
```

第一版不自动修改 `Packages/manifest.json`，除非显式传入：

```bash
unityctl init --install-package
```

原因是 Unity project 的 manifest 可能有团队管理规则，默认自动改动风险偏高。

## 配置查找优先级

CLI 参数优先级从高到低：

1. 显式命令行参数，例如 `--project`、`--unity`、`--base-url`。
2. 当前目录向上发现的 Unity project root。
3. 当前 project 的 `.unity-agent/config.local.json`。
4. 当前 project 的 `.unity-agent/config.json`。
5. 内置默认值。

日常命令不再要求 `--project`：

```bash
cd /Users/elex-mb0203/ELEX/Flame/u3dclient
unityctl play --session login-flow
```

仍然保留 `--project`，用于 agent 在非 project 目录中显式控制目标项目：

```bash
unityctl --project /Users/elex-mb0203/ELEX/Flame/u3dclient status
```

## 命令设计

### 初始化

```bash
unityctl init --unity "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app" --port 17891
```

### 配置查看

```bash
unityctl config show
```

输出合并后的有效配置，并标明来源：

```json
{
  "projectPath": "/Users/example/Game",
  "bridgeUrl": "http://127.0.0.1:17891",
  "unityVersion": "2022.3.62f2",
  "unityExecutablePath": "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity",
  "sources": {
    "projectConfig": "/Users/example/Game/.unity-agent/config.json",
    "localConfig": "/Users/example/Game/.unity-agent/config.local.json"
  }
}
```

### 本机配置更新

```bash
unityctl config set-local unityAppPath "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app"
```

### 启动

```bash
unityctl start
```

等价于当前：

```bash
unityctl start-editor --unity <resolved-unity> --project <resolved-project>
```

后续可以保留 `start-editor` 作为低层命令，但用户文档优先使用 `start`。

### 运行观测

```bash
unityctl play --session login-flow --scene Assets/Scenes/Login.unity
unityctl stop
unityctl summary --latest
unityctl logs --latest --limit 100
unityctl errors --latest
```

`--latest` 表示读取当前 project 下最近一次 session。第一版可通过 session 目录名排序实现。

## 全局安装策略

第一版推荐使用 `uv tool install`。本地开发安装：

```bash
uv tool install --editable ./src/unityctl
```

远程 Git 安装也使用 `uv tool install`，具体 URL 由仓库发布地址决定：

```bash
UNITY_RUN_BRIDGE_GIT_URL="https://github.com/example/UnityRunBridge.git"
uv tool install "git+$UNITY_RUN_BRIDGE_GIT_URL#subdirectory=src/unityctl"
```

原因：

- 项目当前已经使用 `uv` 管理 Python CLI。
- `uv tool install` 会为 CLI 创建隔离环境，避免污染 Unity project 或本仓库虚拟环境。
- 相比自制 install script，第一版维护成本更低。

后续如果需要给非 Python 用户更顺滑的安装体验，再考虑安装脚本或单文件打包。

## 文件与 Git 策略

建议提交：

```text
.unity-agent/config.json
.unity-agent/log-rules.json
```

建议 ignore：

```text
.unity-agent/config.local.json
.unity-agent/sessions/
```

原因：

- `config.json` 记录项目级协议和 Bridge port，是团队共享事实。
- `log-rules.json` 记录项目认可的预期日志过滤规则，应该团队共享。
- `config.local.json` 包含本机路径，不应该提交。
- `sessions/` 是运行产物，不应该提交。

`unityctl init` 不应强行覆盖已有 ignore 内容，只追加缺失行。

## 错误处理

常见错误应给出直接可执行的下一步：

- 找不到 Unity project root：提示在 Unity project 下运行，或传 `--project`。
- 找不到 `config.json`：提示运行 `unityctl init`。
- 找不到 Unity 安装路径：提示运行 `unityctl config set-local unityAppPath "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app"`。
- Bridge 连接失败：展示目标 Bridge URL，提示确认 Unity Editor 是否启动、port 是否匹配。
- Port 被占用：提示换一个 `bridge.port` 后重启 Unity Editor。

错误输出仍保持 JSON，方便 agent 读取：

```json
{
  "ok": false,
  "error": "Unity bridge is not reachable",
  "bridgeUrl": "http://127.0.0.1:17891",
  "hint": "Run unityctl start or check .unity-agent/config.json bridge.port"
}
```

## 非目标

第一版不做：

- 多 Unity Editor 自动发现。
- 自动扫描 Unity Hub 所有安装版本。
- 自动修改 `Packages/manifest.json`，除非显式传 `--install-package`。
- MCP adapter。
- GUI 配置工具。
- 跨机器同步本机 Unity path。

## 待定问题

以下问题需要在 implementation plan 前确认：

1. `unityctl init` 是否默认生成 `bridge.port = 17890`，还是发现占用时自动挑选空闲端口。
2. `unityctl start` 是否应该等待 Bridge ready 后才返回。
3. `config.json` 是否需要 schema，并放入当前仓库 `schemas/`。
4. `summary --latest` 的 latest 是否只按 session id 时间戳排序，还是读取 `session.json.createdAt`。

建议第一版选择：

- 默认 port 为 `17890`，如冲突由用户显式传 `--port`。
- `unityctl start` 默认等待 Bridge ready，提供 `--no-wait`。
- 增加 `schemas/unity-agent-config.schema.json`。
- `--latest` 按 session 目录名排序。
