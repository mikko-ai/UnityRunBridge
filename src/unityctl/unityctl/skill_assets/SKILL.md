---
name: unityctl
description: 使用 unityctl CLI 控制本地 Unity Editor 并验证运行结果。当需要启动 Unity Editor、进入/退出 Play Mode、触发脚本重编译、检查编译错误、收集 Unity Console 日志或生成运行 summary 时使用。适用于改完 Unity 项目代码后验证编译与运行是否正常的场景。
x-unityctl-version: __UNITYCTL_VERSION__
---

# unityctl：Unity 运行与验证

`unityctl` 是控制本地 Unity Editor 的 CLI。所有命令在 Unity 项目根目录或其子目录中执行（也可用 `--project <path>` 指定项目），输出统一为 JSON：成功时 stdout 输出 `{"ok": true, ...}`，失败时 stderr 输出 `{"ok": false, "code": "...", "message": "..."}` 且退出码为 1。

## 核心工作流：改完代码后验证

改完 Unity 项目代码后，按以下顺序验证：

```bash
# 1. 触发脚本重编译并等待完成（阻塞直到编译结束）
unityctl refresh

# 2. 编译通过后，进入 Play Mode 并记录 session（--task 记录任务描述，便于复盘）
unityctl play --session <名称> [--scene Assets/Scenes/Xxx.unity] [--task "验证登录流程"]

# 3. 观察一段时间后退出 Play Mode；输出中直接包含 summary，无需再单独查询
unityctl stop --latest
```

`play` 成功后输出包含 `sessionId` 和 `sessionPath`，后续命令可用 `--latest` 或 `--session-path <路径>` 引用该 session。`stop --latest` 的输出已带 `summary` 字段；如需事后重新读取，再运行 `unityctl summary --latest`。

判读规则：

- `refresh` 返回的 `compilationSucceeded` 为 `false` 时，`compilationErrors` 数组包含文件、行号和错误信息，先修复编译错误再继续。
- `summary` 的 `status` 为 `passed` 表示本次运行没有问题；`problem_detected` 表示出现了普通 `Error` 日志（不必然是业务失败，需要结合日志判断）；`failed` 表示出现 `Exception`/`Assert` 等 blocking problem，或发生了进程级失败（`failedReason` 字段记录原因，如 `compilation_failed`、`timeout`、`editor_exited`）。

## 环境准备

```bash
unityctl doctor            # 诊断：项目配置、UPM 包、Editor 进程、Bridge 连通性
unityctl start             # 启动 Unity Editor 并等待 Bridge 就绪（已在运行则幂等返回 already_running）
unityctl status            # 查询 editorState、编译状态、当前场景
```

- 项目未初始化时（缺 `.unity-agent/config.json`），按以下顺序初始化：

```bash
unityctl init --yes
unityctl config set-local unityExecutablePath "/Applications/Unity/Hub/Editor/<版本>/Unity.app/Contents/MacOS/Unity"
unityctl config validate    # 确认配置无误后再 start
```

- `unityctl config show` 输出合并后的有效配置（项目配置 + 本机配置），排查配置问题时先看它。
- `start` 返回 `editor_already_running` 表示项目被另一个 Editor 实例占用但 Bridge 未就绪，此时不要重试 `start`，先运行 `unityctl doctor` 检查，必要时请用户处理已打开的 Unity 窗口。

## 日志与排错

日志可能非常多（尤其是 Play Mode 期间），不要直接用大 `--limit` 通读全量日志。推荐顺序：

```bash
# 1. 先看有没有错误/异常（已按 log-rules.json 过滤）
unityctl errors --latest

# 2. 再按关键字定位关注的日志（message 子串匹配，不区分大小写）
unityctl logs --latest --grep "关键字"

# 3. 需要看某条日志前后的上下文时，用输出中的 line 字段回到完整日志读取
#    （line 是该条日志在 unity-console.jsonl 中的 1-based 行号）
sed -n '120,140p' <sessionPath>/unity-console.jsonl
```

其他过滤参数：

```bash
unityctl logs --latest --type Error,Exception   # 按日志类型过滤
unityctl logs --latest --after-sequence 500     # 只看 sequence > 500 的增量日志
unityctl logs --latest --limit 20               # 过滤后只取最近 N 条（默认 100）
```

`--after-sequence` 适合"要验证的行为发生在运行后期"的场景：先让游戏跑完初始化，用 `logs --latest --limit 1` 记下当前 sequence 作为游标，触发目标操作后只读游标之后的新日志，跳过全部启动噪音。输出中的 `totalCount`/`matchedCount` 分别是全量条数与命中条数。所有过滤只影响查询结果，`unity-console.jsonl` 始终保留完整日志。

```bash
unityctl open-scene <场景路径>         # 在 Editor 中打开场景
unityctl pause / unityctl resume      # 暂停/恢复 Play Mode
```

`.unity-agent/log-rules.json` 支持两类规则（规则可写 `type`、`messageContains`，同时给出时须同时满足）：

- `ignore`（降噪）：已知无害的 Error 日志（例如第三方插件的固定报错）不再计入问题，`errors` 与 `summary` 按同一套规则过滤，避免误判。
- `watch`（聚焦）：命中的日志会被提取进 `summary.json` 的 `watchedLogs` 字段（带 `line` 行号，最多保留最近 50 条，`watchedCount` 是全量命中数），不影响问题分类。

```json
{
  "ignore": [
    { "type": "Error", "messageContains": "已知无害的报错片段" }
  ],
  "watch": [
    { "messageContains": "本次要验证的关键日志片段" }
  ]
}
```

验证运行后期才发生的行为时，推荐在 `play` 之前把关注点写入 `watch` 规则：`stop --latest` 输出的 summary 会直接带出命中的日志，不需要再从全量日志里捞。

## 查询场景 Hierarchy（只读）

`unityctl hierarchy` 提供跟 Editor Hierarchy 窗口等价的结构化查询能力，Play Mode 内外都能用；只读、不修改场景，全部输出原样为 Bridge 的 JSON 信封。

```bash
unityctl hierarchy roots                                   # 列出所有已加载场景（含 DontDestroyOnLoad）的根节点
unityctl hierarchy tree MainCanvas --depth 2                # 从指定节点向下遍历子树
unityctl hierarchy find --component Button --active-only    # 全 AND 过滤，见 --help 看全部过滤器
unityctl hierarchy find --component Canvas --sort-by Canvas.sortingOrder --desc --page-size 1  # 取某属性最值
unityctl hierarchy ancestors MainCanvas/ShopWindow/BuyButton # 列出祖先（近到远）
unityctl hierarchy inspect MainCanvas/ShopWindow/BuyButton   # 查看完整组件与属性详情
```

- 节点用 `path`（`/` 分隔，同名兄弟带 `[index]` 后缀，如 `Item[0]`）或 `instanceId`（纯数字）定位；两者都可以直接作为 `tree`/`ancestors`/`inspect` 的位置参数传入。
- 多场景 Additive 加载导致同一 `path` 在多个场景命中时返回 `ambiguous_path`，用 `--scene <场景名>` 消歧（DontDestroyOnLoad 的场景名固定为 `DontDestroyOnLoad`）。
- `find` 分页统一用 `--page-size`（默认 50，上限 500）+ `--cursor`（取上次响应的 `nextCursor`）；响应里 `truncated: true` 说明还有更多结果。
- `find --where "Component.property<op>value"`（op 为 `= != > < >= <=`）用于按组件公开属性做单条件过滤；组件短名有歧义时报错并列出候选 FQN，改用完整类型名即可。

## 截图（需 Play Mode）

`unityctl snapshot` 截取当前 Game View 画面并落盘为 PNG，用于给多模态模型看画面或留存证据；底层是异步 job，命令会自动轮询直到完成。

```bash
unityctl snapshot                                    # 默认 reason=agent，落到当前 session 的 artifacts/ 或 .unity-agent/scratch/
unityctl snapshot --reason assert_failure            # 标注触发原因（不同 reason 独立计入配额）
unityctl snapshot --max-long-edge 800                # 单次覆盖输出长边像素上限
```

- 只在 Play Mode 且非 batchmode 下可用；受 `config.json` 里 `capture.screenshot` 配置项管控：`enabled`（总开关）、`allowAgentRequest`（是否允许 `reason=agent` 的主动请求）、`maxPerSession`（配额）、`maxLongEdge`（默认输出长边像素上限）、`agentImageAccess`（`allow`/`deny`，约定多模态模型是否可读取截图内容，Bridge 不做强制）。
- 输出的 `path` 字段是 PNG 的绝对路径；是否把这张图喂给自己（多模态读取）应遵循 `agentImageAccess` 的约定。

## UI 操作（点击/输入/设值，需 Play Mode）

`click`/`input`/`set-value` 是模拟真实用户操作 UGUI 的顶层命令（跟 `play`/`stop` 同级，不是 `interaction` 子命令组），底层直接派发 Unity 事件系统的事件链（`IPointerDownHandler`/`onValueChanged` 等），不是修改内部状态。目标节点用 `hierarchy` 的 `path` 或 `instanceId` 定位。

```bash
unityctl click MainCanvas/ShopWindow/BuyButton              # 默认对目标 screenRect 中心做射线验证
unityctl click MainCanvas/ShopWindow/BuyButton --force      # 跳过射线检测，明知可能被遮挡也强制派发（调试用）
unityctl input MainCanvas/Login/NameField --text "Alice" --submit   # 写入文本并触发 onEndEdit/onSubmit
unityctl set-value MainCanvas/Settings/VolumeSlider --value 0.5              # Slider/Scrollbar 用数字
unityctl set-value MainCanvas/Settings/MusicToggle --value true              # Toggle 用布尔
unityctl set-value MainCanvas/Settings/Scroll --value '{"x": 0.5, "y": 0.2}' --component ScrollRect
```

- `click` 默认走射线验证：命中另一个元素则返回 `occluded` 并带 `blockedBy`（遮挡者的 path），命中链上没有点击处理器返回 `no_click_handler`；成功时返回 `clicked`（实际响应者 path）、`raycastHit`、`events`（实际派发的事件名列表）。只返回派发事实，不等待游戏反应——后续状态验证请配合 `hierarchy inspect` 或 `snapshot`。
- `set-value` 只支持固定组件列表（`Slider`/`Toggle`/`Scrollbar`/`Dropdown`/`TMP_Dropdown`/`ScrollRect`），`--value` 按 JSON 解析（数字/布尔/对象）；节点上有多个可设值组件时必须显式传 `--component`，否则返回 `ambiguous_component`。
- 三个命令都要求 `editorState == "playing"`（暂停中也拒绝），否则返回 `not_in_play_mode`；场景里没有 `EventSystem` 时返回 `no_event_system`。

## Gameplay 命令（零侵入调用游戏代码，需 Play Mode，默认关闭）

`unityctl gameplay` 调用游戏侧暴露的命令，绕开 UI 直接触达 gameplay 逻辑（发货、加钱、切关卡等）。**默认关闭**（安全默认，需在 `config.json` 显式开启，见下）。两条发现通道完全独立：

1. **Duck-typed attribute**：游戏代码给公开静态方法标注一个短名为 `AgentCommandAttribute` 的 attribute（游戏自己定义这个类，不需要引用本包），即可被发现；attribute 若有 `Name` 属性则用作命令名，否则命令名默认为 `类名.方法名`。
2. **白名单直调**：`config.json` 的 `gameplay.whitelist` 里列出完全限定方法名（`Namespace.Class.Method`），无需游戏代码配合。

```json
{
  "gameplay": {
    "enabled": true,
    "whitelist": ["MyGame.CheatManager.AddGold"]
  }
}
```

```bash
unityctl gameplay list                                              # 查看当前可调用命令菜单（含参数/返回类型/是否可调用）
unityctl gameplay invoke CheatManager.AddGold --args '{"amount": 100}'
```

- 参数仅支持 `bool`/`int`/`long`/`float`/`double`/`string`/枚举（枚举可传名字字符串或整数）；`list` 输出里 `invocable: false` 的命令签名不受支持，`invoke` 会拒绝并说明原因。
- 每次 `invoke` 都会追加一行到当前 session 的 `artifacts/gameplay-invokes.jsonl`（无 session 时落 `.unity-agent/scratch/`），记录命令、参数、结果摘要、耗时，供事后审计。
- `invoke` 是任意代码执行入口：只在明确需要绕过 UI 直接验证/构造游戏状态时使用，且应在测试/开发环境启用，不建议对生产分支常开。

## 录制 UGUI 语义动作（需 Play Mode）

`unityctl record` 把手工操作（点击、输入框失焦）录成结构化的 `actions.jsonl`，用来事后复盘、或作为 Phase 3 `scenario from-recording` 生成回放草稿的原料。只录 UGUI 语义动作（按 `path` 记录，不是坐标/像素），不录非 UI 的 gameplay 输入（WASD/摇杆等）。

```bash
unityctl record start                              # 不指定目录时落到当前 session 的 artifacts/，无 session 落 .unity-agent/scratch/
unityctl record start --latest                     # 显式落到最近 session 的 artifacts/
unityctl record start --session-path <path>        # 显式落到指定 session 的 artifacts/
# 手工点击/输入若干次……
unityctl record status                             # 查看是否在录制、已录制多少条
unityctl record stop                                # 停止录制，返回 actionsPath / actionCount / interrupted
```

- 产物两份：`recording-meta.json`（开始时间、activeScene、loadedScenes、屏幕分辨率、sessionId）与 `actions.jsonl`（每行一条动作，`click` 带 `screenPos` 附注、`input` 带失焦时的最终文本；两者都带 `scene` + `path`，多场景场景下用于消歧）。
- domain reload 或退出 Play Mode 会打断录制（监听状态无法跨越这两者存活）；`status`/`stop` 会如实返回 `interrupted: true`，已落盘的动作不会丢失，只是不会再有新动作被追加。
- 回放不在本命令的范围内：`actions.jsonl` → scenario 草稿的转换由 `unityctl scenario from-recording` 承接（见下文）。

## 性能采样（ProfilerRecorder，需 Play Mode）

`unityctl profile` 用 `ProfilerRecorder` 逐帧采样一组固定计数器（v1 不支持自定义配置），写出 `metrics.jsonl`，用来在改动前后做相对回归比较。

```bash
unityctl profile start                              # 不指定目录时落到当前 session 的 artifacts/，无 session 落 .unity-agent/scratch/
unityctl profile start --latest                     # 显式落到最近 session 的 artifacts/
# 让游戏运行一段时间……
unityctl profile status                             # 查看是否在采样、已采样多少帧
unityctl profile stop                                # 停止采样，返回 metricsPath / frameCount / interrupted / aggregates（avg/max/p95）
```

- 固定计数器集（`metrics.jsonl` 字段名 → `ProfilerRecorder` 计数器）：`frameTimeMs`（Internal/"CPU Main Thread Frame Time"，纳秒转毫秒）、`gcAllocBytes`（Memory/"GC Allocated In Frame"）、`drawCalls`（Render/"Draw Calls Count"）、`setPassCalls`（Render/"SetPass Calls Count"）、`triangles`（Render/"Triangles Count"）、`totalMemoryBytes`（Memory/"Total Used Memory"）、`gcMemoryBytes`（Memory/"GC Used Memory"）。
- 计数器在当前 Unity 版本/渲染管线下缺失时不采样该项，记入 `profile start` 响应的 `unavailableMetrics` 列表（不静默返回 0）；scenario 的 `metric` 断言引用不可用指标会判 `metric_not_available`。
- 每 60 帧批量落盘一次（避免逐帧 IO）；domain reload / 退出 Play Mode 会打断采样，已落盘的批次保留，未落盘的一批（< 60 帧）按设计丢弃，`status`/`stop` 会如实返回 `interrupted: true`。
- **重要限制**：Editor 内采样含 Editor 自身开销，绝对值不代表真机性能；正确用途是同机同项目改动前后的相对回归比较，阈值应基于本机基线自行设定。
- session 存在 `artifacts/metrics.jsonl` 时，`unityctl summary` 会自动附加 `metrics` 段（各指标 `avg`/`max`/`p95` + `frameCount`）。

## Scenario：可复跑的自动化验证脚本

`unityctl scenario` 把「打开场景 → 操作 UI → 等待收敛 → 断言事实」的一次验证固化成 JSON 文件，可重复执行、机器判定通过/失败，取代 agent 每次读日志主观判断。断言判定全部在 CLI 侧完成（Bridge 只提供 hierarchy/日志/gameplay 事实），v1 是线性步骤表：**无变量、无条件分支、无循环**。

```bash
unityctl scenario validate login-flow.json           # 只做字段/结构校验，不连接 Bridge
unityctl scenario run login-flow.json                # 执行并生成 session + summary
unityctl scenario run login-flow.json --session my-run --timeout-scale 2   # 自定义 session 名；CI 偏慢时放大所有等待超时
unityctl scenario from-recording .unity-agent/sessions/<id>/artifacts/actions.jsonl -o draft.json  # 从录制生成草稿
```

scenario 文件结构（`schemas/scenario.schema.json`）：

```json
{
  "name": "login-flow",
  "description": "验证登录流程",
  "defaults": { "waitTimeoutSeconds": 10 },
  "steps": [
    { "action": "open-scene", "scene": "Assets/Scenes/Login.unity" },
    { "action": "play" },
    { "action": "wait-for", "ui": { "path": "MainCanvas/LoginWindow", "activeInHierarchy": true } },
    { "action": "input", "path": "MainCanvas/LoginWindow/NameField", "text": "player1" },
    { "action": "click", "path": "MainCanvas/LoginWindow/LoginButton" },
    { "action": "wait-for", "ui": { "path": "MainCanvas/HUD", "activeInHierarchy": true }, "timeoutSeconds": 15 },
    { "action": "assert", "id": "login-window-closed", "ui": { "path": "MainCanvas/LoginWindow", "activeInHierarchy": false } },
    { "action": "assert", "id": "login-log", "log": { "messageContains": "Login success", "sinceStep": 5 } },
    { "action": "assert", "id": "no-exception", "log": { "type": "Exception", "absent": true } },
    { "action": "assert", "id": "user-name", "gameplay": { "command": "GameState.GetCurrentUser", "equals": "player1" } },
    { "action": "stop" }
  ]
}
```

步骤分四类：

- 控制类（复用现有能力）：`open-scene` / `play` / `stop` / `pause` / `resume`。
- 操作类：`click`（含 `force`）/ `input`（含 `submit`）/ `set-value` / `invoke`（gameplay 命令，纯执行不判定）。
- 观测类：`screenshot` / `snapshot`（受 `config.json` 里 `capture.screenshot.onScenarioStep` 开关控制；关闭时该步骤直接跳过，不算失败）。
- 性能采样类：`profile-start` / `profile-stop`（对应 `unityctl profile start/stop`，产出 `artifacts/metrics.jsonl`，供后续 `metric` 断言使用）。
- 收敛/断言类：`wait-for`（轮询直到条件成立或超时，超时算步骤失败，`failureType: "timeout"`）/ `assert`（即时判定一次，不通过算 `failureType: "assertion_failed"`）。两者共用同一套条件模型，四选一 `source`：
  - `ui`：`path`（+可选 `scene`）或 `find`（同 `hierarchy find` 的过滤器子集）定位节点/节点集合后判定 `exists` / `activeInHierarchy` / `interactable` / `textEquals` / `textContains`（path 模式），或 `countEquals` / `countAtLeast` / `countAtMost`（find 模式）。
  - `log`：`{ "type", "messageContains", "absent", "sinceStep" }`；`absent: true` 断言「不应出现」；`sinceStep` 限定日志范围为第 N 步（steps 数组下标）开始之后，缺省为整个 session。
  - `gameplay`：`{ "command", "args", <比较符> }`，比较符六选一：`equals` / `notEquals` / `greaterThan` / `lessThan` / `atLeast` / `atMost`。
  - `metric`：`{ "name", "aggregate", <比较符> }`，依赖前面已执行过的 `profile-start`/`profile-stop`；`aggregate` 三选一 `avg`（默认）/ `max`/ `p95`，比较符同 `gameplay`。metrics.jsonl 不存在，或该指标没有任何样本（可能在本机/渲染管线下不可用）都判 `metric_not_available`。

其他字段：`id`（结果引用名，assert 缺省为 `step-<index>`）、`continueOnFailure`（默认 `false`：失败即中止后续步骤，跳到收尾；`true` 则继续执行下一步）、`timeoutSeconds`（覆盖 `defaults.waitTimeoutSeconds`）。

执行细节：

- `run` 会创建独立 session（名字缺省用 scenario 的 `name`），执行完（无论成败）都会：若曾进入 Play Mode 且仍在播放则自动 `stop`、结束 session、把结果写入 `artifacts/scenario-result.json`，并把断言摘要并入该 session 的 `summary.json`（新增 `scenario` 段：`name`/`stepsTotal`/`stepsPassed`/`stepsFailed`/`assertions`）。断言失败与 `Exception` 日志同级，视为 blocking：`summary.status` 会是 `"failed"`。
  ```bash
  unityctl summary --session-path <run 输出的 sessionPath>   # 事后重新读取
  ```
- `assert` 失败时，若 `config.json` 的 `capture.screenshot.onAssertFailure`（默认 `true`）为真，会自动截图并把路径写进该步骤的 `evidence.screenshotPath`，作为失败证据。
- 退出码：全部步骤通过为 `0`；任何步骤失败（含 `continueOnFailure: true` 的步骤）为 `1`，CI 友好。
- `scenario from-recording` 只做机械转换（`recording-meta.json` 的 `activeScene` → 头部 `open-scene` + `play`；`actions.jsonl` 逐条转成 `click`/`input` 步骤，保留 `scene`/`path`，附纯注释字段 `recordedGap`，不自动插 `wait-for`），产出的草稿**不含任何断言**，尾部补一个 `stop`；回放的价值由你在关键节点手工补 `wait-for` 与 `assert`。缺少 `recording-meta.json` 时报错，不做假设。

## 构建（独立进程，不经过 Bridge）

`unityctl build` spawn 一个新的 batchmode Unity 进程执行 Player 构建，与正在运行、供交互调试的 Editor 实例完全独立——两者不能同时持有同一个项目（Unity 一次只能有一个进程占用 `Library`/`Temp`），所以构建前会检测 `Temp/UnityLockfile` 是否被占用，占用时直接报错，**不会自动关闭已打开的 Editor**。

```bash
unityctl build                                    # 用项目当前 active build target（省略 -buildTarget）
unityctl build --target StandaloneOSX             # 显式指定 Unity 原生 BuildTarget 名
unityctl build --target Android --output /tmp/out.apk --timeout 1800
```

- 目标平台直接透传 Unity 原生 `-buildTarget <target>`（不是自定义参数），保证脚本编译符号（`UNITY_ANDROID` 等）与目标平台一致；缺省时省略该参数，使用项目当前 active build target。
- 产物落在 `.unity-agent/builds/<buildId>/`（`buildId` = 时间戳 + target），含 `build-report.json`（结构见 `schemas/build-report.schema.json`：`result`/`durationMs`/`outputPath`/`sizeBytes`/`errors`/`warnings`/`steps`）与完整的 `build.log`。
- v1 只做 Player 构建（不含 AssetBundle/Addressables）。
- 报告缺失时（多半是脚本编译错误导致 Unity 在真正开始构建前就中止，`-executeMethod` 从未跑起来）会从 `build.log` 里兜底解析 `Foo.cs(12,34): error CSxxxx: ...` 形式的编译错误行，此时 `reportSource` 为 `log_fallback`（正常情况下是 `build_report`）。
- 退出码：`result: "Succeeded"` 为 `0`，其余（`Failed`/`Cancelled`）为 `1`，CI 友好；超时（默认 3600s，`config.json` 的 `timeouts.buildSeconds` 可配，或 `--timeout` 单次覆盖）会杀掉构建进程并报 `build_timeout`。

## 项目健康检查（unityctl health）

`unityctl doctor` 回答「环境能不能跑」（Bridge 连通性、UPM 包、进程占用）；`unityctl health` 回答「项目干不干净」（编译、缺失脚本引用、构建场景列表、包一致性）。四个检查项彼此独立，默认全跑，可用 `--check` 只跑指定项：

```bash
unityctl health                                          # 跑全部四项
unityctl health --check compilation,missing_scripts      # 只跑指定项（逗号分隔）
```

- 四个检查项：
  - `compilation`：触发 `refresh` 并等编译完成，编译失败判 `fail`。
  - `missing_scripts`：分两部分——已加载场景（复用 `hierarchy find --missing-script`）+ 项目内**全部** Prefab 资产（异步 job，按 50 个/tick 批处理避免卡主线程，资产数量大也不会卡住 Editor）；命中任一判 `fail`。
  - `build_scenes`：`EditorBuildSettings.scenes` 里指向不存在文件的条目判 `fail`；项目里存在但未加入该列表的 `.unity` 文件判 `warn`（仅提示，不算错误）。
  - `packages`：`Packages/manifest.json` 与 `packages-lock.json` 依赖不一致，或 `ProjectSettings/ProjectVersion.txt` 记录的 Unity 版本与 `config.json` 的 `unityVersion` 不一致，判 `warn`。
- 每项检查独立输出 `{ "name", "status": "pass|warn|fail|skipped", "details": [...] }`；`compilation`/`missing_scripts` 需要 Bridge，Bridge 不可达时该项标记 `skipped` 并在 `details` 里说明原因，**不计入整体失败**（`build_scenes`/`packages` 是纯静态检查，任何时候都能跑，不需要先 `unityctl start`）。
- 整体 `status` 取所有检查项里最差的一个（`fail` > `warn` > `pass`，`skipped` 不参与比较）；退出码：`pass`/`warn` 为 `0`，`fail` 为 `1`，CI 门禁友好。

## 常见错误码

| code | 含义与处理 |
|------|-----------|
| `compilation_failed` | 编译错误，读取 `compilationErrors` 修复代码后重跑 `unityctl refresh` |
| `timeout` | 等待状态收敛超时，可用 `--timeout <秒>` 放宽后重试 |
| `editor_exited` | Unity Editor 进程退出，运行 `unityctl start` 重新启动 |
| `editor_already_running` | 项目被占用但 Bridge 未就绪，运行 `unityctl doctor` 检查 |
| `bridge_unreachable` | Bridge 不可达，通常 Editor 未启动，运行 `unityctl start` |
| `bridge_capability_missing` | Bridge（UPM 包）版本过旧，缺少所需能力，升级 UPM 包后重试 |
| `node_not_found` / `ambiguous_path` | hierarchy 查询的 path/instanceId 找不到或有歧义，见上文 |
| `unknown_component` / `ambiguous_component` | hierarchy 查询里的组件/接口名无法解析，改用完整类型名 |
| `capture_disabled` / `agent_capture_denied` | 截图被 `config.json` 中 `capture.screenshot` 配置关闭，检查 `enabled`/`allowAgentRequest` |
| `capture_requires_play_mode` / `capture_unavailable` | 截图需要 Play Mode 且非 batchmode，先 `unityctl play` |
| `capture_quota_exceeded` | 超出 `capture.screenshot.maxPerSession` 配额，调大配置或结束当前 session |
| `not_in_play_mode` | UI 操作命令需要 Play Mode（暂停中也算不满足），先 `unityctl play` / `unityctl resume` |
| `no_event_system` | 场景中没有 `EventSystem`，UI 操作无法派发 |
| `occluded` | `click` 命中了另一个元素（见响应 `blockedBy`），确认是否符合预期遮挡，或用 `--force` 调试 |
| `no_click_handler` / `not_interactable` | 目标节点链上没有点击处理器，或 `interactable=false`/祖先 `CanvasGroup` 禁用 |
| `not_input_field` | `input` 目标节点没有 `InputField`/`TMP_InputField` 组件 |
| `unsupported_set_value` / `ambiguous_component` | `set-value` 组件不在支持列表内，或节点上有多个可设值组件需显式传 `--component` |
| `gameplay_disabled` | gameplay 命令桥关闭，需在 `config.json` 的 `gameplay.enabled` 中显式开启 |
| `command_not_found` | 命令名既不在 attribute 发现结果中，也不在 `gameplay.whitelist` 里，先 `unityctl gameplay list` 核对命令名 |
| `unsupported_signature` | 命令参数/返回值类型不受支持（仅支持 bool/int/long/float/double/string/枚举），或白名单方法名有多个重载 |
| `invoke_failed` | 命令方法执行时抛出异常，见响应 `message` 里的异常类型与信息 |
| `already_recording` | 已经在录制中，先 `unityctl record stop` 再重新 `start` |
| `no_input_backend` | 项目未启用任何受支持的输入后端（Input Manager / Input System），检查 Player Settings |
| `invalid_scenario` | scenario 文件字段/结构非法，见响应 `errors`（每条带步骤索引） |
| `scenario_failed` | scenario 执行完成但有步骤失败（含超时/断言失败），见 `scenario.steps` 里 `status: "failed"` 的步骤 |
| `already_profiling` | 已经在采样中，先 `unityctl profile stop` 再重新 `start` |
| `metric_not_available` | assert/wait-for 用了 `metric` source，但还没有 `profile-start`/`profile-stop` 产出的 `metrics.jsonl`，或该指标在本机/渲染管线下不可用 |
| `editor_running` | `unityctl build` 检测到项目被另一个 Unity 实例占用（`Temp/UnityLockfile`），先关闭已打开的 Editor 窗口再重试，不会自动关闭 |
| `build_timeout` | 构建超过 `timeouts.buildSeconds`（默认 3600s）仍未结束，已被强制终止，可用 `--timeout` 放宽后重试 |
| `build_failed` | 构建进程正常结束但结果不是 `Succeeded`，见响应里的 `errors`/`reportSource`（`log_fallback` 时多半是编译错误） |
| `health_check_failed` | `unityctl health` 有检查项判定为 `fail`，见响应里 `checks` 数组中 `status: "fail"` 的项及其 `details` |
| `already_scanning` | 上一次 `missing_scripts` 检查触发的 Prefab 扫描还没结束，等它完成后再重试（不会并发扫描） |

## 注意事项

- `play`/`stop`/`refresh` 默认阻塞直到目标状态达成，不需要自行轮询 `status`。超时秒数默认读取 `config.json`，可用 `--timeout <秒>` 覆盖；`play`/`stop` 支持 `--no-wait` 立即返回（跳过状态收敛，一般不建议 agent 使用）。
- Unity 编译（domain reload）期间 Bridge 会短暂中断，CLI 已内部处理重连，无需干预。
- session 产物位于 `.unity-agent/sessions/<sessionId>/`（`session.json`、`unity-console.jsonl`、`summary.json`），可直接读取文件做进一步分析。
- 本文只覆盖常用流程；完整参数运行 `unityctl <命令> --help` 查看。
