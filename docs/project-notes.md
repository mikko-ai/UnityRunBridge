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

Unity package 只运行在 Editor 中，不进入 runtime build，不修改业务代码。它启动一个本地 HTTP Bridge，提供状态查询、Play Mode 控制、场景打开、脚本重编译触发、session 绑定和日志写入能力；在此基础上垂直扩展出 UGUI Hierarchy 查询、截图、UI 操作模拟、零侵入 gameplay 命令桥、动作录制、性能采样、批量资产健康检查等能力（见「垂直能力扩展」一节），以及独立 batchmode 进程执行的 Player 构建诊断。

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

## 垂直能力扩展（Phase 0-4）

在「运行控制 + 运行观测」的基础底座之上，按照"垂直能力架构方案"分五个 Phase 继续扩展，让 agent 能完成从"看懂画面结构"到"操作 UI / 调用游戏逻辑"到"固化成可复跑脚本"到"量化性能与项目健康度"的完整闭环。设计上延续既有的三个核心思路（握手发现、状态收敛、纯 JSON + Schema），并新增了两个基础设施层：

### Phase 0：路由注册 + 异步 job 模型

- **路由/能力注册**（`Editor/Routing/`）：把原来硬编码的 HTTP 路由表改成显式注册机制（`RouteTable.Register`），每个功能模块的 Controller 在加载时自行注册路由，并向 `CapabilityRegistry` 声明自己提供的能力名；`GET /capabilities` 汇总输出，CLI 侧用它判断 Bridge（UPM 包）版本是否支持某个命令，缺失时报 `bridge_capability_missing` 而不是笼统的 404。
- **异步 job 模型**（`Editor/Jobs/`）：截图、Prefab 扫描等耗时操作不能阻塞 HTTP 请求线程，也不能一次性做完（会卡住 Editor 主线程），统一抽象成「`POST .../start` 返回 `jobId` → 轮询 `GET /jobs/{id}` → 终态 `succeeded`/`failed`」的模式。`JobManager` 负责生命周期、并发数上限、超时熔断；domain reload 会清空内存态，`JobManager` 用 `SessionState` 记录"reload 前有正在跑的 job"，reload 后统一标成 `failed`（`interrupted_by_reload`），如实上报而不是让调用方永久卡在轮询。
- **手写 JSON 层**（`Editor/Json/`）：没有引入 `com.unity.nuget.newtonsoft-json` 依赖，而是自己写了一个 Newtonsoft 风格但更精简的 `JsonParser`/`JsonWriter`/`JsonValue`，Editor-only、无第三方依赖、行为可控（递归深度/输入体积上限、确定性 key 顺序，便于测试断言）。
- **session artifacts 目录约定**：新增能力的产物（截图、`actions.jsonl`、`metrics.jsonl`、`gameplay-invokes.jsonl`）统一落在当前 session 的 `artifacts/` 下，没有 session 时落 `.unity-agent/scratch/`；`ArtifactPathGuard` 校验落盘路径必须在这两类目录之内，防止任意路径写入。

### Phase 1：结构化理解（只读）

- **Hierarchy 查询**（`Editor/Hierarchy/`）：`roots`/`tree`/`find`/`ancestors`/`inspect` 五个只读命令，语义对齐 Unity Editor 的 Hierarchy 窗口和常用 C# 反射查询能力（按组件类型、公开属性条件过滤，支持分页），而不是让模型自己判断"这块 UI 看起来像什么"——结构化事实优先于视觉猜测。多场景 Additive 加载、同名兄弟节点等边界情况都有专门处理（`ambiguous_path`、`[index]` 后缀）。
- **截图**（`Editor/Capture/`）：作为结构化查询的补充，而不是主要事实来源；配置项区分"是否允许 agent 主动请求截图"和"截图是否可以被模型读取"，把权限和用途分离，管控口径可配置而不是硬编码。

### Phase 2：操作与执行

- **UI 操作**（`Editor/Interaction/`）：`click`/`input`/`set-value` 直接派发 Unity 事件系统的真实事件链（`IPointerDownHandler`、`onValueChanged` 等），而不是直接改内部状态——保证验证的是"用户操作会发生什么"而不是"我手动摆出了某个状态"。默认做射线遮挡验证（`occluded`/`no_click_handler`），`--force` 才跳过。
- **Gameplay 命令桥**（`Editor/Gameplay/`）：零侵入是核心约束——游戏代码不需要引用本包也能被发现调用（duck-typed attribute，游戏自己定义一个同名 attribute 类即可），另有白名单直调作为不需要游戏侧配合的备选通道。默认关闭，且是项目里最大的"任意代码执行"入口，所有调用都落审计日志。
- **动作录制**（`Editor/Recording/`）：录的是语义动作（按 `path` 记录的点击/输入），不是坐标或像素，这样录制产物既能给人复盘，也能机械转换成 scenario 草稿。实现上因为 Editor-only 程序集不能挂 `MonoBehaviour`，改成了静态类 + `EditorApplication.update` 驱动的轮询模型——这个模式后来在 Phase 4 的 `MetricsSampler`、`PrefabScanRunner` 上复用。

### Phase 3：固化为可复跑脚本

`unityctl scenario` 把"操作 UI → 等待收敛 → 断言事实"的一次性验证固化成 JSON 文件，可重复执行、机器判定通过/失败，替代 agent 每次读日志主观判断。关键设计取舍：

- 断言判定逻辑全部放在 **CLI 侧（Python）**，Bridge 只负责提供 hierarchy/日志/gameplay/metric 的原始事实——保持 Bridge 侧简单，判定逻辑用 Python 写更容易维护和测试。
- v1 刻意做成线性步骤表：无变量、无条件分支、无循环。先把"能确定性复跑"这个最小可用版本做稳，复杂控制流留给后续版本按需再加。
- `scenario from-recording` 只做机械转换，不自动插入 `wait-for`/`assert`——录制脚本知道"发生了什么"，但不知道"应该断言什么"，这一步交给人补。

### Phase 4：量化与诊断

- **性能采样**（`Editor/Profiling/`）：用 `ProfilerRecorder` 采固定一组计数器，明确不追求"绝对性能数字"（Editor 内采样含 Editor 自身开销），只服务于"同机同项目改动前后的相对回归对比"这一个场景，避免误用。
- **Build 诊断**（`Editor/Build/` + `build.py`）：故意做成完全独立于 Bridge 的第二进程（`-executeMethod` batchmode 构建），因为 Unity 一次只能有一个进程持有项目的 `Library`/`Temp` 锁——构建必须是"另一个 Unity 实例"，不能复用正在跑的交互式 Editor。CLI 侧兜底解析 `build.log` 里的编译错误，覆盖"报告都没生成"的失败模式（脚本编译错误会导致 `-executeMethod` 从未真正执行）。
- **项目健康检查**（`Editor/Health/` + `health.py`）：`doctor` 回答"环境能不能跑"，`health` 回答"项目干不干净"，两者定位不同不合并。检查项设计成互相独立、可单独跑、Bridge 不可达时优雅降级为 `skipped` 而不是让整体检查失败——这样静态检查（`build_scenes`/`packages`）永远可用，不必先启动 Editor。

### 0.3.0：可选依赖与程序集边界

垂直能力落地后，把单体 Editor 程序集拆成可按项目依赖裁剪的模块，避免无 UGUI 的项目也被强行拉入 UI 包：

- **Core**：契约、实例级 Route/Capability runtime、JSON、Jobs、Hierarchy 核心扫描；禁止引用 UGUI/TMP/Input System。
- **Host**：唯一 `[InitializeOnLoad]` composition root；事务装配 Adapter → Module，失败回滚。
- **Features**：各 capability Module（含 Interaction/Recording 的 `IsAvailable` 门控）。
- **Build**：独立 batchmode 构建入口。
- **Adapters**：UGUI / TMP / LegacyInput / Input System 按 `versionDefines` + `defineConstraints` 条件编译。

Capability 裁剪规则（对外契约）：

| 场景 | routes | capabilities | 缺省能力 |
|------|--------|--------------|----------|
| 完整安装（含 UGUI） | 30 | 9 | — |
| Core-only / NoUGUI | 24 | 7 | 无 `interaction`、`recording` |

项目侧在 `Packages/manifest.json` 按需加入 `com.unity.ugui` / TMP / Input System；示例见 `examples/unity-project-manifest/`。CLI 对缺失 capability 统一报 `bridge_capability_missing`。

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
- 补 `.unity-agent/.gitignore` 中缺失的 `config.local.json`、`sessions/`、`bridge.json`、`scratch/`、`builds/`（不改动项目根 `.gitignore`）。
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

命令集：`init`、`config show|validate|set-local`、`start`、`status`、`play`、`stop`、`pause`、`resume`、`open-scene`、`logs`、`errors`、`summary`、`refresh`、`doctor`、`hierarchy`、`snapshot`、`click`、`input`、`set-value`、`gameplay`、`record`、`profile`、`scenario`、`build`、`health`、`skills`。旧版的 `start-editor` 已删除（`start` 已完全覆盖其能力）。

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

会话生命周期与 Play Mode 生命周期是解耦的（会话只由 `session/start`/`session/end` 控制），手动进/退 Play Mode 不结束会话——但每一轮 Play Mode 运行的边界会如实落进日志：

- 每条日志带 `runIndex` 字段，标记它属于 session 内第几轮 Play Mode 运行（`0` 表示首轮运行开始前的编辑期日志）。`runIndex` 持久化到 `SessionState`，跨 domain reload 连续。
- 每轮的起止由 Bridge 写入的 `BridgeEvent` 边界行标出：`runStarted` 在进入 Play 流程开始时（`ExitingEditMode`，domain reload 之前）写入并递增 `runIndex`，让 reload 噪音与 `Awake` 日志归入新一轮；`runEnded` 在退出流程完全结束（`EnteredEditMode`）后写入，保证 `OnDestroy` 日志属于本轮。边界行与普通日志共用同一条 `sequence` 链，不参与问题分类。
- 一个 session 内 CLI 只触发一轮 play，出现第二轮即说明有人在 Editor 中手动重新进入过 Play Mode：summary 的 `runs` 数组按轮次分组统计（起止时间、sequence 区间、`problemCount`/`blockingProblemCount`），并给出 `manualInterventionDetected: true` 提示 agent 结果可能混入非受控运行。这是"如实记录 + 显式标注"的取舍：桥不阻止手动操作、不丢弃日志，判定交给读 summary 的一方。

`summary.json` 汇总本次运行结果。规则：

- session 处于 `failed`（进程级失败）时，summary 的 `status` 直接是 `failed`，并带上 `failedReason`。
- 否则按日志分类：`Exception` / `Assert` 默认视为 blocking problem，会让 `status` 变成 `failed`。
- 普通 `Error` 会记录为 problem（`status` 为 `problem_detected`），但不必然代表业务失败。
- `Warning` 默认不影响状态。
- `.unity-agent/log-rules.json` 可配置 ignore rules（降噪）与 watch rules（聚焦）；`unityctl errors` 复用与 `summary` 相同的分类逻辑（`classify_log` + `load_log_rules`），口径保持一致。
- watch rules 命中的日志会在生成 summary 时提取进 `watchedLogs` 字段（带 `line` 行号，最多保留最近 50 条，`watchedCount` 记录全量命中数），不影响问题分类。agent 可以在 `play` 前声明本次运行的关注点，`stop` 后直接从 summary 拿到命中日志。

Play Mode 期间日志量可能很大，而要验证的行为往往发生在运行后期，因此 `unityctl logs` 支持查询侧过滤：`--grep`（message 子串，不区分大小写）、`--type`（日志类型，逗号分隔）、`--after-sequence`（只看某个 sequence 游标之后的增量，利用 sequence 单调递增的特性跳过启动噪音）、`--run`（只看第 N 轮 Play Mode 运行的日志）；`BridgeEvent` 边界行默认过滤，`--include-events` 显示。过滤只影响查询结果，`unity-console.jsonl` 始终全量落盘。`logs` 与 `errors` 输出的每条日志都带 `line` 字段（在 `unity-console.jsonl` 中的 1-based 行号），便于回到完整日志中查看上下文；`logs` 输出还包含 `totalCount` / `matchedCount`。SKILL.md 中同步给出了推荐的读日志顺序（先 `errors`，再按关键字过滤，不做全量通读）。

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
- `unityctl init` 检测并可写入 Unity `Packages/manifest.json` 中的 bridge package 依赖。
- `unityctl config show` / `set-local` / `validate`。
- `unityctl --version` 从 Python package metadata 输出 CLI 版本。
- `unityctl refresh`、`unityctl doctor`（含 `project_lock` 项目占用检测）。
- `--latest` session 查询能力。
- JSON Schema 和 examples（含 `bridge.schema.json`、`config.schema.json`、`config.local.schema.json`）。
- Python 与 Unity EditMode 测试脚本。
- 专门的 Agent skill（SKILL.md），用自然语言封装常见 Unity 验证流程（含垂直能力扩展后的完整用法与错误码表），`unityctl skills init/update` 分发到项目内。
- Phase 0 基础设施：路由/能力注册机制（`RouteTable` + `CapabilityRegistry` + `GET /capabilities`）、异步 job 模型（`JobManager`，支持并发上限、超时熔断、domain reload 后如实标记 `interrupted_by_reload`）、手写 JSON 解析器/写入器（`Editor/Json/`，无第三方依赖）、session artifacts 目录约定与路径校验（`ArtifactPathGuard`）。
- Phase 1 结构化理解：只读 UGUI Hierarchy 查询命令组 `roots`/`tree`/`find`/`ancestors`/`inspect`（组件过滤、属性条件、分页、多场景消歧）；Play Mode 截图 job 与 `unityctl snapshot`（配额、权限配置分离）。
- Phase 2 操作与执行：射线遮挡验证的 `click`/`input`/`set-value`（真实派发 Unity 事件系统事件链）；零侵入 gameplay 命令桥（duck-typed attribute + 白名单双通道，默认关闭，带审计日志）；UGUI 语义动作录制（`unityctl record`，产出 `actions.jsonl`）。
- Phase 3 可复跑验证脚本：`unityctl scenario`（`validate`/`run`/`from-recording`），CLI 侧断言引擎覆盖 `ui`/`log`/`gameplay`/`metric` 四类条件源，结果并入 session `summary.json`。
- Phase 4 量化与诊断：`ProfilerRecorder` 逐帧性能采样（`unityctl profile`，60 帧批量落盘、`avg`/`max`/`p95` 汇总）；独立 batchmode 进程的 Player 构建诊断（`unityctl build`，`build-report.json` + 编译错误日志兜底解析）；项目健康检查（`unityctl health`：`compilation`/`missing_scripts`/`build_scenes`/`packages`，Bridge 不可达时优雅降级为 `skipped`）。
- **0.3.0 模块化拆分**：Editor 包拆为八个生产程序集（Core / Host / Features / Build + UGUI / TMP / LegacyInput / InputSystem Adapter）；`package.json` 不再强依赖 UGUI；完整安装 **30 路由 / 9 capability**，NoUGUI **24 / 7**（无 `interaction`/`recording`）。内部 asmdef 边界为破坏性变化；对外 HTTP 协议与 CLI 命令面保持兼容（见包内 `CHANGELOG.md`）。

## 还没有做

暂未进入或还需要继续完善的方向：

- 更完整的跨平台路径校验，尤其是 Windows 与 Unity Hub 非默认安装路径。
- 非 Python 用户的一键安装脚本、二进制分发或更顺滑的安装体验。
- MCP adapter，让其他 agent 可以通过 MCP tools 调用 UnityRunBridge。
- scenario v2：变量、条件分支、循环（v1 刻意保持线性步骤表，按需再加）。
- UI Prefab 自动拼接。

## 当前不做的方向

这些方向有价值，但不是当前 MVP 主路径：

- 完全无侵入式 Unity 控制。完全无侵入很难稳定控制 Play Mode 和场景。
- 依赖截图或多模态视觉作为主要事实来源。它适合作为辅助（`snapshot`/`scenario` 的 `screenshot`/`snapshot` 步骤都保留为可选观测手段），不适合作为断言判定的主要依据——断言逻辑始终建立在 hierarchy/日志/gameplay/metric 这些结构化事实上。
- UI Prefab 自动拼接。它依赖设计图理解、资源匹配、Prefab 规范和运行验证，应该在运行与观测底座稳定后再做。
- MCP 第一版。当前优先 CLI 和本地 HTTP 协议，MCP 可以作为后续适配层。
- 配置迁移工具。这一版是彻底重构，不保留旧结构，也不提供从旧结构自动迁移的能力。

## 文件与 Git 策略

建议提交到 Unity project：

```text
.unity-agent/config.json
.unity-agent/log-rules.json
```

建议忽略（由 `.unity-agent/.gitignore` 管理，相对该目录）：

```text
config.local.json
sessions/
bridge.json
scratch/
builds/
```

（`init` 会自动把这几条补进 `.unity-agent/.gitignore`，缺失才补，不会重复添加或删除用户自定义内容；不修改项目根 `.gitignore`。）

本仓库自身保留：

- `README.md`：用户入口说明。
- `docs/project-notes.md`：项目目标、设计、状态和后续路线。
- `schemas/`：落盘数据结构契约。
- `examples/`：示例配置和 session 文件。

## 后续建议

基础运行控制/观测链路与垂直能力扩展已在仓库 fixture 矩阵（NoUGUI / UGUI / UGUI+TMP × Legacy / Input System / Both）上验证。下一步比较自然的是：

1. 在真实 Unity project 中添加 UPM package（`com.mk.unity-agent-bridge`），按需声明可选依赖（见 `examples/unity-project-manifest/`），跑一遍基础链路：`init` → `config validate` → `start`/`status` → `play --session <name>` → `stop --latest` → `summary --latest` → 故意改一段编译报错代码验证 `refresh`。
2. 在同一个真实项目里试跑垂直能力：`hierarchy find` 看真实结构是否符合预期、有 UGUI 时 `click`/`input` 走一遍真实登录/交互流程、录一段 `record` 并用 `scenario from-recording` 生成草稿补上断言、跑一次 `unityctl health` 看真实项目会报出哪些 `missing_scripts`/`packages` 问题。
3. 用真实项目的反馈决定下一步优先级：是补安装体验、做 MCP adapter，还是继续加固 scenario 的表达能力（变量/条件分支）。
