# UnityRunBridge Project Notes

## 我们要做什么

UnityRunBridge 的目标是为 Unity 项目提供一个低侵入的本地运行与验证桥接能力，让通用 coding agent 可以在写完代码后继续完成更关键的一步：启动 Unity、控制 Play Mode、收集日志、生成可审计结果，并把这些结果返回给 agent 或开发者。

当前阶段聚焦的是 Unity 游戏运行与验证基础设施，而不是通用 Unity AI 助手，也不是自动拼 UI Prefab。

核心目标：

- 让 agent 能启动并连接一个本地 Unity Editor。
- 让 agent 能查询 Editor 状态、进入/停止/暂停/恢复 Play Mode、打开场景、触发脚本重编译。
- 让每次运行有独立 session，落盘 `session.json`、`unity-console.jsonl` 和 `summary.json`。
- 让 `unityctl` 成为全局命令，用户可以在 Unity project root 或子目录中直接使用。
- 让项目级配置和本机配置分离，支持多个 Unity 项目同时打开、不同端口和不同 Unity 安装路径。
- 让 CLI 命令在返回前尽量确认 Unity Editor 已经真正达到目标状态（而不是发完请求就假设成功）。

## 为什么这样做

当前真实痛点不是让 agent 写代码，而是让 agent 写完代码后能够验证 Unity 项目。Unity 验证通常需要人工启动 Editor、进入 Play Mode、观察 Console、判断错误、整理结果。这个过程高频、重复，而且会打断 coding agent 的闭环。

因此第一阶段选择"运行控制 + 运行观测"作为基础能力：

- 运行控制让 agent 能推动 Unity Editor 进入目标状态。
- 运行观测让 agent 能读取本次运行产生的事实。
- session 文件让运行结果可复盘、可审计、可传给后续工具。

这比直接做画面理解、游戏 UI 自动点击或 Prefab 自动拼接更稳，也更适合作为后续能力的底座。

## 总体设计

项目由两部分组成：

- Unity Editor-only package：`packages/com.mk.unity-agent-bridge`
- Python CLI：`src/unityctl`

Unity package 只运行在 Editor 中，不进入 runtime build，不修改业务代码。它启动一个本地 HTTP Bridge，提供状态查询、Play Mode 控制、场景打开、脚本重编译触发、session 绑定和日志写入能力。

Python CLI 负责：

- 启动 Unity Editor 进程。
- 发现 Unity project root。
- 读取项目配置。
- 通过握手文件发现 Bridge 实际监听的端口和鉴权 token。
- 调用 Unity Bridge HTTP API，并轮询状态直到目标状态收敛（或超时/失败）。
- 创建 session 目录。
- 汇总日志并生成 summary。
- 提供全局命令入口 `unityctl`。

高层流程：

```text
agent / user
  -> unityctl
  -> .unity-agent/config.json + config.local.json
  -> .unity-agent/bridge.json（握手发现端口与 token）
  -> Unity Editor Bridge（带 X-Bridge-Token）
  -> 轮询 GET /status 直到状态收敛
  -> .unity-agent/sessions/<sessionId>/
```

## 三个核心设计

这一版重构围绕三个核心设计展开，彻底替换了第一版的实现，不保留旧行为：

### 1. 握手发现（`bridge.json`）

Unity Bridge 启动（含每次 domain reload 后重启）时，把实际监听的端口、进程 PID、鉴权 token、Unity 版本等信息原子写入 `.unity-agent/bridge.json`。CLI 不再依赖配置文件里的固定端口，而是读取这个握手文件来定位 Bridge。

- 端口顺延：Bridge 从 `config.json` 的 `bridge.preferredPort`（默认 17890）开始尝试，被占用则递增，最多尝试 10 个端口；实际绑定端口以 `bridge.json` 为准。
- 生命周期：绑定成功后写入、每次 domain reload 后覆盖写、仅在 Editor 真正退出时删除（domain reload 期间绝不删除，否则 CLI 会在 reload 窗口里误判 Editor 已退出）。
- 鉴权：token 每个 Editor 进程生成一次，写入 `SessionState` 以跨 domain reload 保持不变；所有 HTTP 请求必须带 `X-Bridge-Token` 请求头，否则返回 401。

CLI 侧的握手校验（`unityctl.discovery`）分两步：读取 `bridge.json` → 确认里面记录的 pid 仍然存活（否则视为过期文件并自动清理）。第三步（带 token 请求 `GET /status`）由调用方自行发起。

### 2. 状态收敛（`unityctl.convergence`）

Unity 的 Play Mode 进入/退出、脚本重编译都是异步的。`play`、`stop`、`refresh` 等命令发出请求后，会持续轮询 `GET /status` 的 `editorState` 字段，直到目标状态达成、超时，或探测到编译失败/Editor 退出等终止性失败，才返回结果。

`editorState` 由 Unity Bridge按固定优先级从原始标志位派生（`compiling` > `updating` > `paused` > `exitingPlay` > `playing` > `enteringPlay` > `idle`），是收敛循环判断的唯一依据。

轮询过程中如果连接失败（例如 domain reload 造成的短暂中断），CLI 会重新读一次 `bridge.json`：pid 还活着就当作正常的 reload 窗口继续等待；pid 已经不存在则立即判定 Editor 退出，不用等到超时。

`play`/`stop` 都支持 `--timeout` 覆盖配置里的默认超时时间，以及 `--no-wait` 跳过收敛；`refresh` 也支持 `--timeout`，但没有 `--no-wait`，因为收敛是它的核心价值。

### 3. 纯 JSON 配置 + Schema

配置文件从 `.jsonc` 改为纯 `.json`，不再支持注释和尾随逗号，也不再需要自定义 JSONC 解析器。`init` 时会把 CLI 内置的 schema 文件复制到 `.unity-agent/schemas/`，配置文件里的 `$schema` 字段指向它们，供编辑器提供自动补全和字段说明（中文 `description`），替代过去的行内注释。

## 配置设计

UnityRunBridge 使用项目本地 `.unity-agent/` 目录保存配置和运行产物。

配置拆成两类：

- `.unity-agent/config.json`：项目级配置，建议提交到 Git。
- `.unity-agent/config.local.json`：本机配置，不应提交。

`config.json` 示例：

```json
{
  "$schema": "schemas/config.schema.json",
  "version": 1,
  "unityVersion": "2022.3.62f2",
  "bridge": {
    "preferredPort": 17890
  },
  "defaultScene": null,
  "timeouts": {
    "playSeconds": 180,
    "stopSeconds": 60,
    "startEditorSeconds": 300
  }
}
```

`config.local.json` 示例：

```json
{
  "$schema": "schemas/config.local.schema.json",
  "unityExecutablePath": "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity"
}
```

`version` 是配置 schema 自身的版本，不是 `unityctl` 包版本，也不是 Unity 版本。这次是彻底重构，没有从旧 `.jsonc` 结构迁移的概念：`bridge.host`（监听地址硬编码 `127.0.0.1`）和 `sessionDirectory`（路径硬编码为 `.unity-agent/sessions`）这两个字段已经被删除。

握手文件 `.unity-agent/bridge.json` 是运行时产物，不应提交到 Git，也不能人工编辑；结构见 `schemas/bridge.schema.json`。

## init 设计

`unityctl init` 是项目入口。它可以无参数执行：

```bash
unityctl init
```

行为规则：

- 从当前目录向上查找 Unity project root。
- 展示将要初始化的项目路径，并要求用户确认。
- 脚本或 CI 中可以使用 `unityctl init --yes` 跳过确认。
- 只补缺失的 `config.json` / `config.local.json`，不覆盖已有文件。
- 把内置 schema 复制/刷新到 `.unity-agent/schemas/`（schema 是机器生成物，总是覆盖）。
- 补 `.gitignore` 中缺失的 `.unity-agent/config.local.json`、`.unity-agent/sessions/`、`.unity-agent/bridge.json`。
- 初始化完成后提示用户编辑 local 配置并运行 `unityctl config validate`。

已初始化项目再次执行 `init` 时，不会重写用户手改过的 `config.json` / `config.local.json`。

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
unityctl refresh
unityctl doctor
```

也可以通过 `--project` 从仓库外控制指定 Unity project：

```bash
unityctl --project /path/to/UnityProject status
```

Python package / uv tool package 名称使用 `unity-run-bridge`，全局命令保持短命令 `unityctl`，内部 Python import package 仍是 `unityctl`。

命令集：`init`、`config show|validate|set-local`、`start`、`status`、`play`、`stop`、`pause`、`resume`、`open-scene`、`logs`、`errors`、`summary`、`refresh`、`doctor`。旧版的 `start-editor` 已删除（`start` 已完全覆盖其能力）。

`refresh` 会触发 `AssetDatabase.Refresh()` 并轮询直到编译完成，是 agent 改完代码后验证编译是否通过的主入口。`doctor` 会依次检查 project root、`config.json` 是否可解析、`unityExecutablePath` 是否存在、UPM package 是否已安装、`bridge.json` 是否存在、Editor 进程是否存活、Bridge 是否可达、项目是否被 Unity 占用（`project_lock`），输出统一的诊断报告。

## Session 与运行观测

一次带 session 的运行会在 Unity project 下创建：

```text
.unity-agent/sessions/<sessionId>/
  session.json
  unity-console.jsonl
  summary.json
```

`session.json` 记录运行元数据，例如 session id、项目路径、场景、任务说明、状态、时间、`editorPid`、`unityVersion`。状态机是 `created → running → stopped`（正常）或 `created/running → failed`（编译失败、超时、Editor 退出等进程级失败），失败时 `failedReason` 记录原因。

`unity-console.jsonl` 记录 Unity Console 日志，每行一个 JSON 对象；日志的 `sequence` 会持久化到 `SessionState`，跨 domain reload 仍然单调递增。

`summary.json` 汇总本次运行结果。规则：

- session 处于 `failed`（进程级失败）时，summary 的 `status` 直接是 `failed`，并带上 `failedReason`。
- 否则按日志分类：`Exception` / `Assert` 默认视为 blocking problem，会让 `status` 变成 `failed`。
- 普通 `Error` 会记录为 problem（`status` 为 `problem_detected`），但不必然代表业务失败。
- `Warning` 默认不影响状态。
- `.unity-agent/log-rules.json` 可配置 ignore rules；`unityctl errors` 复用与 `summary` 相同的分类逻辑（`classify_log` + `load_log_rules`），口径保持一致。

## 已完成

已完成的主要能力：

- Python CLI package 与 `unityctl` 命令入口。
- Unity Editor 进程启动，`unityctl start` 启动后轮询握手直到 Bridge 就绪；重复 `start` 时若 Bridge 已可达则幂等返回 `already_running`，若项目被占用但 Bridge 未就绪则快速失败（`editor_already_running`）。
- Unity Editor-only Bridge package `com.mk.unity-agent-bridge`。
- 握手发现：`bridge.json` 原子写入/删除、端口顺延、token 鉴权。
- 统一 HTTP 响应信封（`ok`/`code`/`message`）与状态码映射（200/401/404/409/422/500）。
- HTTP routes：`status`、`play`、`stop`、`pause`、`resume`、`open-scene`、`refresh`、`session/start`、`session/end`、`session/status`。
- `editorState` 派生（含编译中/更新中/进入播放/退出播放等中间态）与编译结果跟踪（`CompilationTracker`）。
- 状态收敛：`play`/`stop`/`refresh` 轮询到目标状态或超时/失败才返回。
- Session 创建、状态更新（含 `failed` 状态与 `failedReason`）和落盘。
- Unity Console 日志捕获到 session，`sequence` 跨 domain reload 持久化。
- Summary 生成、log rules ignore、`errors` 与 `summary` 分类口径统一。
- 全局命令设计：package 名 `unity-run-bridge`，命令名 `unityctl`。
- Unity project root 自动发现。
- 纯 JSON 配置 `.unity-agent/config.json` 和 `.unity-agent/config.local.json`，`init` 时同步内置 schema 到项目内。
- `unityctl config show` / `set-local` / `validate`。
- `unityctl refresh`、`unityctl doctor`（含 `project_lock` 项目占用检测）。
- `--latest` session 查询能力。
- JSON Schema 和 examples（含 `bridge.schema.json`、`config.schema.json`、`config.local.schema.json`）。
- Python 与 Unity EditMode 测试脚本。

## 还没有做

暂未进入或还需要继续完善的方向：

- 自动修改 Unity `Packages/manifest.json` 安装 package。
- `unityctl --version`，从 Python package metadata 输出 CLI 版本。
- 更完整的跨平台路径校验，尤其是 Windows 与 Unity Hub 非默认安装路径。
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
- 配置迁移工具。这一版是彻底重构，不保留旧结构，也不提供从旧结构自动迁移的能力。

## 文件与 Git 策略

建议提交到 Unity project：

```text
.unity-agent/config.json
.unity-agent/log-rules.json
```

建议忽略：

```text
.unity-agent/config.local.json
.unity-agent/sessions/
.unity-agent/bridge.json
```

本仓库自身保留：

- `README.md`：用户入口说明。
- `docs/project-notes.md`：项目目标、设计、状态和后续路线。
- `schemas/`：落盘数据结构契约。
- `examples/`：示例配置和 session 文件。

## 后续建议

下一步比较自然的是做一次实际项目试用：

1. 在真实 Unity project 中添加 UPM package（`com.mk.unity-agent-bridge`）。
2. 运行 `unityctl init`。
3. 配置 `config.local.json` 的 `unityExecutablePath`。
4. 运行 `unityctl config validate`。
5. 运行 `unityctl start` 和 `unityctl status`。
6. 跑一次 `unityctl play --session <name>`，再用 `stop --latest` 和 `summary --latest` 检查结果。
7. 改一段会编译报错的代码，运行 `unityctl refresh` 确认能正确报出编译错误。

真实项目试用后，再决定优先补安装体验、MCP adapter，还是更强的验证能力。
