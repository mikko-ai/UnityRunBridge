# UnityRunBridge Project Notes

## 我们要做什么

UnityRunBridge 的目标是为 Unity 项目提供一个低侵入的本地运行与验证桥接能力，让通用 coding agent 可以在写完代码后继续完成更关键的一步：启动 Unity、控制 Play Mode、收集日志、生成可审计结果，并把这些结果返回给 agent 或开发者。

当前阶段聚焦的是 Unity 游戏运行与验证基础设施，而不是通用 Unity AI 助手，也不是自动拼 UI Prefab。

核心目标：

- 让 agent 能启动并连接一个本地 Unity Editor。
- 让 agent 能查询 Editor 状态、进入/停止/暂停/恢复 Play Mode、打开场景。
- 让每次运行有独立 session，落盘 `session.json`、`unity-console.jsonl` 和 `summary.json`。
- 让 `unityctl` 成为全局命令，用户可以在 Unity project root 或子目录中直接使用。
- 让项目级配置和本机配置分离，支持多个 Unity 项目同时打开、不同端口和不同 Unity 安装路径。

## 为什么这样做

当前真实痛点不是让 agent 写代码，而是让 agent 写完代码后能够验证 Unity 项目。Unity 验证通常需要人工启动 Editor、进入 Play Mode、观察 Console、判断错误、整理结果。这个过程高频、重复，而且会打断 coding agent 的闭环。

因此第一阶段选择“运行控制 + 运行观测”作为基础能力：

- 运行控制让 agent 能推动 Unity Editor 进入目标状态。
- 运行观测让 agent 能读取本次运行产生的事实。
- session 文件让运行结果可复盘、可审计、可传给后续工具。

这比直接做画面理解、游戏 UI 自动点击或 Prefab 自动拼接更稳，也更适合作为后续能力的底座。

## 总体设计

项目由两部分组成：

- Unity Editor-only package：`packages/com.elex.unity-agent-bridge`
- Python CLI：`src/unityctl`

Unity package 只运行在 Editor 中，不进入 runtime build，不修改业务代码。它启动一个本地 HTTP Bridge，提供状态查询、Play Mode 控制、场景打开、session 绑定和日志写入能力。

Python CLI 负责：

- 启动 Unity Editor 进程。
- 发现 Unity project root。
- 读取项目配置。
- 调用 Unity Bridge HTTP API。
- 创建 session 目录。
- 汇总日志并生成 summary。
- 提供全局命令入口 `unityctl`。

高层流程：

```text
agent / user
  -> unityctl
  -> .unity-agent/config.jsonc + config.local.jsonc
  -> Unity Editor Bridge
  -> .unity-agent/sessions/<sessionId>/
```

## 配置设计

UnityRunBridge 使用项目本地 `.unity-agent/` 目录保存配置和运行产物。

配置拆成两类：

- `.unity-agent/config.jsonc`：项目级配置，建议提交到 Git。
- `.unity-agent/config.local.jsonc`：本机配置，不应提交。

`config.jsonc` 示例：

```jsonc
// 项目级配置：建议提交到 Git。
{
  // 配置结构版本，用于解析和未来迁移；不是 unityctl 版本，也不是 Unity 版本。
  "version": 1,

  // 可选：项目期望使用的 Unity 版本，仅用于提示和校验。
  "unityVersion": "2022.3.62f2",

  "bridge": {
    "host": "127.0.0.1",
    "port": 17890
  },

  "defaultScene": null,
  "sessionDirectory": ".unity-agent/sessions"
}
```

`config.local.jsonc` 示例：

```jsonc
// 本机配置：不要提交到 Git。
{
  // 必填：Unity 可执行文件路径。
  "unityExecutablePath": "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity"
}
```

`version` 是配置 schema version，不是 `unityctl` 包版本，也不是 Unity 版本。只有配置结构发生不兼容变化时，才需要升级它。未来如果需要迁移配置，可以增加 `unityctl config migrate`。

## init 设计

`unityctl init` 是项目入口。它可以无参数执行：

```bash
unityctl init
```

行为规则：

- 从当前目录向上查找 Unity project root。
- 展示将要初始化的项目路径，并要求用户确认。
- 脚本或 CI 中可以使用 `unityctl init --yes` 跳过确认。
- 只补缺失文件，不覆盖已有文件。
- 缺 `config.jsonc` 就创建 project template。
- 缺 `config.local.jsonc` 就创建 local template。
- 补 `.gitignore` 中缺失的 `.unity-agent/config.local.jsonc` 和 `.unity-agent/sessions/`。
- 初始化完成后提示用户编辑 local 配置并运行 `unityctl config validate`。

已初始化项目再次执行 `init` 时，不会重写用户手改过的配置。

## CLI 使用目标

安装后，用户希望在 Unity project root 或子目录中直接运行：

```bash
unityctl init
unityctl config validate
unityctl start
unityctl status
unityctl play --session login-flow
unityctl stop --latest
unityctl summary --latest
```

也可以通过 `--project` 从仓库外控制指定 Unity project：

```bash
unityctl --project /path/to/UnityProject status
```

Python package / uv tool package 名称使用 `unity-run-bridge`，全局命令保持短命令 `unityctl`，内部 Python import package 仍是 `unityctl`。

## Session 与运行观测

一次带 session 的运行会在 Unity project 下创建：

```text
.unity-agent/sessions/<sessionId>/
  session.json
  unity-console.jsonl
  summary.json
```

`session.json` 记录运行元数据，例如 session id、项目路径、场景、任务说明、状态和时间。

`unity-console.jsonl` 记录 Unity Console 日志，每行一个 JSON 对象。

`summary.json` 汇总本次运行结果。当前规则是：

- `Exception` / `Assert` 默认视为 blocking problem。
- 普通 `Error` 会记录为 problem，但不必然代表业务失败。
- `Warning` 默认不影响状态。
- `.unity-agent/log-rules.json` 可配置 ignore rules。

## 已完成

已完成的主要能力：

- Python CLI package 与 `unityctl` 命令入口。
- Unity Editor 进程启动。
- Unity Editor-only Bridge package。
- HTTP routes：`status`、`play`、`stop`、`pause`、`resume`、`open-scene`、`session/start`、`session/end`、`session/status`。
- Play Mode 和 Scene 控制。
- Session 创建、状态更新和落盘。
- Unity Console 日志捕获到 session。
- Summary 生成和 log rules ignore。
- 全局命令设计：package 名 `unity-run-bridge`，命令名 `unityctl`。
- Unity project root 自动发现。
- `.unity-agent/config.jsonc` 和 `.unity-agent/config.local.jsonc`。
- 中文注释 JSONC 配置模板。
- `unityctl init` 无参数初始化、确认机制、只补缺失文件。
- `unityctl config show`。
- `unityctl config set-local`。
- `unityctl config validate`。
- `unityctl start` 使用项目 local 配置启动 Unity。
- `--latest` session 查询能力。
- Unity Bridge 从 `config.jsonc` 读取 `bridge.host` 和 `bridge.port`。
- JSON Schema 和 examples。
- Python 与 Unity EditMode 测试脚本。

当前验证状态：

- Python 测试：44 个测试通过。
- Unity EditMode：9 个测试通过。
- 真实 Unity smoke：Bridge 可从 `config.jsonc` 读取配置端口并返回 `/status`。

## 还没有做

暂未进入或还需要继续完善的方向：

- 自动修改 Unity `Packages/manifest.json` 安装 package。
- `unityctl config migrate`，用于未来配置 schema 升级。
- `unityctl --version`，从 Python package metadata 输出 CLI 版本。
- 更完整的跨平台路径校验，尤其是 Windows 与 Unity Hub 非默认安装路径。
- Bridge 端口冲突自动诊断或自动建议可用端口。
- 非 Python 用户的一键安装脚本、二进制分发或更顺滑的安装体验。
- MCP adapter，让其他 agent 可以通过 MCP tools 调用 UnityRunBridge。
- 专门的 Agent skill，用自然语言封装常见 Unity 验证流程。
- 游戏画面结构化理解。
- 游戏 UI 自动点击、录制/回放和 gameplay command bridge。
- 自动生成验证断言。
- 性能 profiling、build 诊断、项目健康检查等更垂直的后续 agent service。
- UI Prefab 自动拼接。

## 当前不做的方向

这些方向有价值，但不是当前 MVP 主路径：

- 完全无侵入式 Unity 控制。完全无侵入很难稳定控制 Play Mode 和场景。
- 依赖截图或多模态视觉作为主要事实来源。它适合作为辅助，不适合作为第一版自动验证核心。
- 自动操作游戏 UI。需要游戏侧暴露结构化状态或命令接口，暂不进入基础设施阶段。
- UI Prefab 自动拼接。它依赖设计图理解、资源匹配、Prefab 规范和运行验证，应该在运行与观测底座稳定后再做。
- MCP 第一版。当前优先 CLI 和本地 HTTP 协议，MCP 可以作为后续适配层。

## 文件与 Git 策略

建议提交到 Unity project：

```text
.unity-agent/config.jsonc
.unity-agent/log-rules.json
```

建议忽略：

```text
.unity-agent/config.local.jsonc
.unity-agent/sessions/
```

本仓库自身保留：

- `README.md`：用户入口说明。
- `docs/README.md`：项目目标、设计、状态和后续路线。
- `schemas/`：落盘数据结构契约。
- `examples/`：示例配置和 session 文件。

## 后续建议

下一步比较自然的是做一次实际项目试用：

1. 在真实 Unity project 中添加 UPM package。
2. 运行 `unityctl init`。
3. 配置 `config.local.jsonc` 的 `unityExecutablePath`。
4. 运行 `unityctl config validate`。
5. 运行 `unityctl start` 和 `unityctl status`。
6. 跑一次 `unityctl play --session <name>`，再用 `stop --latest` 和 `summary --latest` 检查结果。

真实项目试用后，再决定优先补安装体验、MCP adapter，还是更强的验证能力。
