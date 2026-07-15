# P0 Agent 交互可靠性设计

日期：2026-07-14
状态：设计定稿（经独立审阅修订），待实现

## 一、背景与问题

基于 2026-07-14 多轮 Agent 实机探索记录（登录 → 清对白 → 跟随引导 → 自由点主界面），确认：

1. **核心能力可用。** 最后一轮逐条执行 `unityctl click` / `hierarchy find` 后，背包、英雄、邮件、建造、联盟均拿到回执与对应面板变化。问题不在点击实现本身。
2. **Agent 误判“点成功”。** `click` 只返回事件派发事实（`clicked` / `events`），不等待业务状态变化。Agent 常把“有回执”写成“界面已打开”。
3. **缺少持久化审计。** CLI stdout 中的 click JSON 若未被可靠记录，事后无法证明点过谁、是否被遮挡。`gameplay invoke` 已有 `gameplay-invokes.jsonl`；交互命令没有对应物。`record` 面向手工输入，不能替代 Agent 命令审计。
4. **Agent 自写脚本放大失误。** 探索脚本里 `local path=` 在 zsh 中破坏 `PATH`，导致 `unityctl` 根本未发出；又用 `|| true`、`grep` 字段存在性检查、空等补时长掩盖失败。文档虽已禁止截图像素推目标，但缺少完整的“逐步探索闭环”协议。

P0 只解决上述交互可靠性缺口；P1（顶层 `wait-for`、项目 UI 导航知识、截图可读性诊断）另开设计。

## 二、目标与非目标

### 目标

1. 每次**已进入** `InteractionController.Click` / `Input` / `SetValue`、并产生结构化结果（成功或失败信封）的调用，都在当前 session 的 `artifacts/interaction-actions.jsonl` 追加一行；无 session 时写入 `.unity-agent/scratch/`。
2. 官方 Skill 定义可验证的自适应探索闭环与三级证据模型，禁止未知流程用一次性 shell/Python 长脚本代跑。
3. 保持现有 Bridge HTTP 响应与 CLI JSON 信封字段兼容；审计写盘失败不得改变原操作结果。

### 审计覆盖边界（明确）

**在范围内：** Controller 内所有早退与成功返回（含 `invalid_argument`、`not_in_play_mode`、`node_not_found`、`ambiguous_path`、`occluded`、`no_click_handler`、后端失败码、成功）。

**不在范围内（P0 不审计）：**

- 未通过鉴权 / Host 在进入 Controller 前拒绝的请求
- 路由表未命中、capability 缺失（CLI 侧 `bridge_capability_missing`，请求未达 Controller）
- Controller 外未捕获的进程级异常导致 Host 返回的 `internal_error`（若未来要覆盖，需路由包装器，本 P0 不做）

### 非目标

- 不新增顶层 `unityctl wait-for` / `click --verify`。
- 不扩展 `unityctl-project-skill-creator` 的 UI 导航/引导知识。
- 不改 `.cursorignore` / `agentImageAccess` 诊断逻辑。
- 不改 `scenario` 步骤语义、断言模型或 `actions.jsonl`（手工录制）格式。
- 不把审计文件并入 `summary.json` 的通过/失败判定（本阶段仅落盘，供复盘）。
- 不要求 CLI 响应新增审计文件路径字段。

## 三、总体方案

采用 **Bridge 侧交互审计 + Skill 探索协议**：

```text
Agent / CLI / scenario
        │
        ▼
POST /interaction/{click|input|set-value}
        │
        ▼
InteractionController
        │
        ├── 业务逻辑（响应字段与现网兼容，不新增破坏性字段）
        └── 统一出口 AuditAndReturn(...)
                ├── InteractionAuditLog.Append(...)
                └── return 原响应对象
                        → artifacts/interaction-actions.jsonl
                          （无 session → .unity-agent/scratch/）

Skill 侧：
  SKILL.md           → 索引“自适应探索”入口
  interaction.md     → 单步闭环 + 三级证据 + 禁止项
```

选择 Bridge 而非 CLI 的原因：

- 与现有 `GameplayAuditLog` 模型一致，覆盖 CLI、scenario、直接 HTTP（只要进入 Controller）。
- 审计与操作同进程、同时刻，不依赖 Agent 是否 `tee` stdout。
- 失败路径（`occluded`、`not_in_play_mode`）也在 Controller 内统一落盘。

## 四、Bridge：InteractionAuditLog

### 4.1 位置与依赖

- 新文件：`packages/com.mk.unity-agent-bridge/Editor/Features/Interaction/InteractionAuditLog.cs`
- 命名空间：`Mk.UnityAgentBridge.Editor.Interaction`
- 默认复用：`ArtifactPathGuard.ResolveArtifactDirectory()`（session `artifacts/` 或 `scratch/`）
- 参考：`GameplayAuditLog` 的 append-only、写盘失败只 Warning、不阻塞主路径

为可测性，`InteractionAuditLog` **必须**提供可注入 seam（测试用，生产默认走 Guard + `File.AppendAllText`）：

- 目录解析：可替换的 `Func<string>` / 内部 static hook，默认 `ArtifactPathGuard.ResolveArtifactDirectory`
- 追加写入：可替换的 append action，默认写文件；测试可改为写入 `List<string>` 或抛异常

文件名固定：`interaction-actions.jsonl`。与手工录制的 `actions.jsonl` **刻意分离**：

| 文件 | 来源 | 用途 |
|------|------|------|
| `actions.jsonl` | `unityctl record` | 用户手工操作 → scenario 草稿 |
| `interaction-actions.jsonl` | Bridge 交互路由 | Agent/CLI/scenario 发出的命令审计 |
| `gameplay-invokes.jsonl` | gameplay invoke | 任意代码执行审计 |

### 4.2 写入时机与统一出口

三个入口方法的**每一个**结构化返回都必须经过统一出口，禁止散落的手工 `Append` + `return`（避免漏挂成功分支）。

推荐形状（示意，命名可微调）：

```csharp
private static object AuditAndReturn(
    string action, JsonValue requestSummary, object response, long durationMs)
{
    InteractionAuditLog.AppendFromResponse(action, requestSummary, response, durationMs);
    return response;
}
```

覆盖的结果码包括：

- `invalid_argument`（缺 path 等）
- `not_in_play_mode`
- `node_not_found` / `ambiguous_path`
- `occluded`（含 `blockedBy`）
- `no_click_handler` 及其他 `PointerSimulator` / `InputSimulator` 失败码
- 成功响应

实现约束：

1. `Append` / `AppendFromResponse` 内部 `try/catch`：任何 IO/序列化异常只 `Debug.LogWarning`，**不得**改写或吞掉原响应。
2. 方法入口记 `Stopwatch`；审计行写入 `durationMs`（毫秒，整数）。早退路径也记录。
3. `events` 数组必须原样复制后端返回的事件名字符串，**不得重命名**（现网为 lower camel：`pointerDown` / `pointerUp` / `pointerClick`）。

### 4.3 单行字段契约

每行一个 JSON 对象，UTF-8，末尾 `\n`。

**公共必填（每行都必须出现）：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `time` | string | UTC ISO-8601（`DateTime.UtcNow.ToString("O")`） |
| `action` | string | `"click"` \| `"input"` \| `"set-value"` |
| `ok` | boolean | 与响应 `ok` 一致 |
| `code` | string | 见下方合成规则 |
| `request` | object | 规范化安全请求摘要 |
| `durationMs` | integer | ≥ 0 |
| `playModeFrame` | integer | Playing 时为 `Time.frameCount`，否则 **固定写 `-1`** |
| `activeScenePath` | string | `EditorSceneManager.GetActiveScene().path`；空场景写 `""` |

**`code` 合成规则：**

- 审计行根据结果合成，**不修改 HTTP/CLI 响应体**。
- 成功：一律写 `"ok"`。说明：当前 click / set-value 成功响应体本身往往不带 `code` 字段；input 成功经 `BridgeResponse.Success` 带 `code:"ok"`。审计不得为了“对齐响应”而给 click/set-value 成功响应新增 `code`。
- 失败：写 Bridge 错误码（与响应 `code` 一致）。

**条件字段：**

| 字段 | 何时出现 |
|------|----------|
| `scene` | 请求 body 含非空 `scene` 时写入；否则省略（不写 null） |
| `message` | `ok:false` 且有错误信息时写入 |
| `clicked` / `raycastHit` / `events` / `forced` | click 成功时按响应写入；`raycastHit` 可为 JSON null |
| `blockedBy` | `code=="occluded"` 时写入 |
| `component`（顶层） | set-value 成功时写入实际组件类型名 |

P0 **不写** `runIndex`。

**`request` 规范化（body 已是 JSON object 时）：**

| action | 始终写出 | 条件写出 | 禁止出现 |
|--------|----------|----------|----------|
| `click` | `force`（bool；缺省按 `false`） | `path`（字符串且非空时） | — |
| `input` | `submit`（bool；缺省按 `false`） | `path`；`text` 为 string 时写 `textLength`（C# `string.Length`，UTF-16 code units） | `text` 及任何原文 |
| `set-value` | — | `path`；`component`（若请求提供）；`valueKind` + 可选 `value`/`valueLength`（见脱敏） | 敏感原文 |

**`request.path` 完整性规则（覆盖所有 `ok` 取值）：**

- 默认：`request.path` 必须为非空字符串。
- **唯一例外**：`code=="invalid_argument"` 且失败原因正是“请求体缺少/非法 `path` 字段”时，允许省略 `request.path`。
- 因此 `occluded`、`no_click_handler`、`node_not_found`、`not_interactable` 等失败码——path 本身已被成功解析——**必须**带 `path`；只有“path 参数本身缺失/非法”这一种早退可以没有 `path`。

**set-value 脱敏：**

| 原始 value | `valueKind` | 是否写 `value` |
|------------|-------------|----------------|
| number | `number` | 是（数字） |
| boolean | `boolean` | 是 |
| 仅含 `x`/`y` 且均为 number 的 object | `object` | 是（仅这两个键） |
| string | `string` | **否**；可写 `valueLength`（`string.Length`） |
| 其他 object / array / null / 无法分类 | `unknown` 或 `invalid` | **否** |

`valueKind` 与 `value` 双向耦合（缺一不可）：

- `valueKind` ∈ {`number`,`boolean`,`object`} ⇔ **必须**同时出现 `value`，且 `value` 的 JSON 类型与 `valueKind` 一致。
- `valueKind` ∈ {`string`,`unknown`,`invalid`} ⇔ **必须不**出现 `value`（可选 `valueLength`）。

即：只声明 `valueKind:"number"` 却不带 `value`，或反过来带 `value` 却不声明匹配的 `valueKind`，均视为违反契约。

### 4.4 示例

成功 click：

```json
{
  "time": "2026-07-14T12:05:01.2345670Z",
  "action": "click",
  "ok": true,
  "code": "ok",
  "request": { "path": "UICanvas/Canvas/HudLayer/main_panel_new/right_bot/root_down/bag", "force": false },
  "scene": "DontDestroyOnLoad",
  "clicked": "UICanvas/Canvas/HudLayer/main_panel_new/right_bot/root_down/bag",
  "raycastHit": "UICanvas/Canvas/HudLayer/main_panel_new/right_bot/root_down/bag",
  "events": ["pointerEnter", "pointerDown", "pointerUp", "pointerClick", "pointerExit"],
  "forced": false,
  "durationMs": 12,
  "playModeFrame": 1842,
  "activeScenePath": "Assets/Scenes/City.unity"
}
```

遮挡失败：

```json
{
  "time": "2026-07-14T12:05:08.0000000Z",
  "action": "click",
  "ok": false,
  "code": "occluded",
  "message": "click target is occluded by another UI element",
  "request": { "path": "UICanvas/Canvas/HudLayer/main_panel_new/middle_bot/heroBtn/herobtn", "force": false },
  "blockedBy": "UICanvas/Canvas/FunctionLayer/f_bag_panel/btn_back",
  "durationMs": 3,
  "playModeFrame": 1901,
  "activeScenePath": "Assets/Scenes/City.unity"
}
```

缺 path：

```json
{
  "time": "2026-07-14T12:05:09.0000000Z",
  "action": "click",
  "ok": false,
  "code": "invalid_argument",
  "message": "body 必须包含字符串字段 path",
  "request": { "force": false },
  "durationMs": 0,
  "playModeFrame": -1,
  "activeScenePath": ""
}
```

脱敏 input：

```json
{
  "time": "2026-07-14T12:06:00.0000000Z",
  "action": "input",
  "ok": true,
  "code": "ok",
  "request": { "path": "MainCanvas/Login/NameField", "textLength": 5, "submit": true },
  "durationMs": 8,
  "playModeFrame": 200,
  "activeScenePath": "Assets/Scenes/Login.unity"
}
```

## 五、Schema 与分发

### 5.1 新增 schema

文件名：`interaction-actions.schema.json`

同步维护两份：

- `schemas/interaction-actions.schema.json`
- `src/unityctl/unityctl/schemas/interaction-actions.schema.json`

单行对象（draft 2020-12），约束如下：

1. 顶层必填：`time`、`action`、`ok`、`code`、`request`、`durationMs`、`playModeFrame`、`activeScenePath`。
2. 顶层 `additionalProperties: false`；允许的属性仅限本设计列出的字段。
3. `action` 枚举：`click` | `input` | `set-value`。
4. `request`：
   - `type: object`，**`additionalProperties: false`**。
   - 按 `action` 用 `allOf` + `if/then` 封闭允许键：
     - `click` → 仅 `path`、`force`
     - `input` → 仅 `path`、`textLength`、`submit`（**禁止** `text`）
     - `set-value` → 仅 `path`、`component`、`valueKind`、`value`、`valueLength`
5. 路径完整性（对齐 4.3 节规则，覆盖所有 `ok` 取值）：
   - 默认 `request` required 含 `path`（非空 string）。
   - 仅当 `code=="invalid_argument"` 时，`if/then` 放宽为不要求 `path`（放宽即可，仍允许该场景补 `path`）。
   - `occluded` / `no_click_handler` / `node_not_found` / `not_interactable` 等其余失败码与 `ok:true` 一样要求 `path`。
6. set-value 值耦合（双向）：
   - `valueKind` ∈ {`number`,`boolean`,`object`} ⇔ 必须有 `value`，且类型与 kind 匹配。
   - `valueKind` ∈ {`string`,`unknown`,`invalid`} ⇔ 禁止 `value`。

说明：与 `scenario.schema.json` 一样，schema 文件首先是结构文档与编辑器提示；机器校验可采用手写断言（零 `jsonschema` 依赖，与现有 scenario 惯例一致）或等价检查。无论用哪种方式，第 7.3 节反例必须自动化失败。

### 5.2 init 分发

在 `src/unityctl/unityctl/config.py` 的 `SCHEMA_FILENAMES` 追加 `"interaction-actions.schema.json"`，使 `unityctl init` 复制到 `.unity-agent/schemas/`。

两份 schemas 内容必须一致。

## 六、Skill：自适应探索协议

### 6.1 改动文件

| 文件 | 改动 |
|------|------|
| `skill_assets/unityctl/SKILL.md` | 能力索引或注意事项中增加“自适应 UI 探索”入口，指向 `references/interaction.md`；保持主文件精简。 |
| `skill_assets/unityctl/references/interaction.md` | 新增「自适应探索闭环」「三级证据」「禁止项」「interaction-actions.jsonl 审计说明」；强化 path 引号；保留禁止像素推目标。 |

### 6.2 单步闭环（必须遵守）

对未知或需动态决策的探索，每一步严格：

1. **唯一定位**：`hierarchy find` / `tree` / `inspect` 消歧为唯一 `path` 或 `instanceId`；不得像素最近距离猜测。
2. **单条命令**：直接执行一条 `unityctl ...`，不把多步未知流程打包进自定义 shell/Python 脚本。
3. **保留回执**：完整保留命令 JSON；事后可对照 `artifacts/interaction-actions.jsonl`。
4. **状态验证**：用 hierarchy / gameplay / log 确认预期业务变化。
5. **必要时截图**：仅理解画面与复核，不得从截图像素推导点击目标。
6. **再决策**：`occluded` 时读 `blockedBy`，先处理遮挡。

已知可复跑流程使用官方 `unityctl scenario`。

### 6.3 三级证据

| 级别 | 来源 | 含义 | 能否宣称“操作成功” |
|------|------|------|-------------------|
| L1 | 响应被接受 / `ok` 语义 | 命令到达且未被参数/能力门拒绝 | 否 |
| L2 | `clicked` / `events`（click）或 `component`（input/set-value）等成功字段 | 控件级交互已被对应 adapter（UGUI/TMP 等）接受并应用 | 否 |
| L3 | hierarchy / gameplay / log / snapshot 业务变化 | 游戏状态符合意图 | **是** |

仅有 L1/L2 时只能说“已派发”，不能说“已打开某某界面”。

### 6.4 禁止项

- 禁止未知探索用一次性长 shell/Python 包装代跑多步决策。
- 禁止 `|| true`（或等价）吞掉交互失败。
- 禁止用 `grep` 检查 `"clicked"` 字符串代替解析 JSON 语义。
- 禁止无观测的空等补时长。
- 禁止从截图像素或手指 `screenRect` 欧氏距离选“最近按钮”。
- path 含 `[index]` 时示例统一加引号：`unityctl click 'Root/Item[1]'`。
- 打开面板后先验证并关闭（或处理遮挡），再点下一入口。

### 6.5 zsh / path 陷阱

简短提示：不要在 zsh 函数里使用局部变量名 `path`（绑定 `PATH`）。

## 七、测试与验收

### 7.1 Editor（NUnit）

全部自动化；**禁止**以“PR 人工确认每个 return 已挂钩”作为成功路径的唯一验收。

1. **统一出口 + 脱敏（单元）**
   - builder / `Append`：input 行整行 JSON **不含**秘密原文子串，且无 `text` 键；set-value 对 string/`unknown` 不落 `value`。
   - `textLength` 使用 C# `string.Length`。
   - 成功/失败行均含第 4.3 节公共必填字段。

2. **Controller 失败路径落盘（EditMode）**
   - click / input / set-value 的 `invalid_argument` 与 `not_in_play_mode` 各至少一条。
   - 断言：目标目录（或注入的 sink）**行数恰好 +1**；`ok:false`、`code` 匹配、`action` 正确、`request` 符合规范化；Controller 返回码不变。

3. **Controller 成功路径落盘（必须自动化）**
   - 三个方法各至少一条成功路径测试，证明走统一出口后审计行 `ok:true`、`code:"ok"`、含非空 `request.path`。
   - 实现方式二选一（Spec 允许，PR 须采用其一并写进测试名）：
     - **A. EditMode seam**：注入 fake play-state / fake resolve / fake backend，使 Controller 在非真实 Play Mode 下走到成功分支；或
     - **B. 既有 Play Mode / EditorIntegration 基建**（如 UGUI `PointerSimulatorTests` 同类）上对 Controller 包一层调用并断言审计 sink。
   - 不得只测“手工构造的成功 Append 行”而不经过 Controller 成功返回。

4. **落盘目录**
   - 通过注入目录解析或临时 project 根：无 session → scratch；有 session → 该 session `artifacts/`。
   - 断言 `Append` **实际写入**该目录下的 `interaction-actions.jsonl`（不仅断言 Guard 返回值）。

5. **写盘失败不改结果**
   - 注入 appender 抛异常（优先于只读目录）；Controller 仍返回原错误码/成功体。
   - 使用 `LogAssert.Expect`（或项目等价手段）接收预期 Warning。
   - 测试前后清理 sink / 临时文件，避免历史行干扰“+1”断言。

6. **解析失败类（尽量覆盖）**
   - 至少一条 `node_not_found`（或 EditMode 可构造的等价 Resolve 失败）证明后半段 return 也审计。
   - `occluded`：若 EditMode 成本过高，可用对 `AppendFromResponse` / builder 传入 occluded 形状的单元测 + Controller 成功/失败测共同约束；但 **不得**因此豁免第 3 条成功路径要求。

### 7.2 Python

- init / `SCHEMA_FILENAMES`：新 schema 被复制到 `.unity-agent/schemas/`。
- `test_skills.test_real_assets_install`（或等价）断言安装后文案含：
  - 三级证据或“不能仅凭 clicked 宣称界面已打开”
  - 自适应探索闭环关键词
  - 禁止一次性包装脚本 / 禁止像素最近按钮
  - `interaction-actions.jsonl`

### 7.3 Schema / 行形状（自动化反例）

正例通过：成功 click（含完整 `path`）、occluded（含 `path` 与 `blockedBy`）、缺 path 的 invalid_argument（省略 `request.path`）、脱敏 input、合法 set-value number（`valueKind:"number"` 且带匹配 `value`）。

反例必须失败：

- 缺公共必填字段
- 非法 `action`
- `ok:true` 但缺少 `request.path`
- **`code=="occluded"`（或 `no_click_handler`/`node_not_found`/`not_interactable`）但缺少 `request.path`**——验证“仅 `invalid_argument` 可省略 path”这条规则不会被其他失败码滥用
- `request` 含额外键（如 input 的 `text`，或未知敏感字段）
- set-value：`value` 为 string 且无/错 `valueKind`；或 `valueKind` 为 `string` 却带 `value`
- **`valueKind:"number"`（或 `boolean`/`object`）但缺少 `value`**——验证双向耦合，不只是“有 value 才需要 valueKind”的单向约束
- 嵌套未知 object / array 作为 `value` 却声称可落盘

实现可用手写断言（与 scenario 零依赖惯例一致）；不强制引入 `jsonschema` 包。

### 7.4 回归

- 现有 CLI interaction 转发、scenario click、相关 Editor 测保持通过。
- **冻结契约**：click / set-value 成功 HTTP/CLI 响应**不因本 P0 新增**顶层 `code` 字段；审计落盘与响应体解耦。
- `scripts/run-full-tests.sh` 覆盖范围内不引入新失败。

## 八、文档

- `references/interaction.md`：闭环、证据、审计文件说明、禁止项（必做）。
- `docs/project-notes.md`：artifacts 列表追加 `interaction-actions.jsonl`（必做）。
- `README.md`：仅当正文已逐条列举 artifacts 文件名时同步补一句；否则不改。

## 九、实现顺序建议

1. Schema 双份 + `SCHEMA_FILENAMES` + 行形状正/反例测试
2. `InteractionAuditLog`（含注入 seam）+ 统一 `AuditAndReturn` + Controller 挂钩
3. Editor：失败路径、成功路径、目录、写盘失败、脱敏
4. Skill + `test_skills` 契约断言
5. `docs/project-notes.md`
6. 跑相关测试子集确认

## 十、明确不做（复述）

- 顶层 `wait-for`、`click --verify`
- 项目 UI creator / 引导目标查询能力
- Cursor ignore / 截图 Permission denied 诊断
- 修改 `actions.jsonl` 或 `scenario from-recording`
- 将交互审计计入 `summary.status`
- 要求 Agent 必须 `cat` 审计文件才能继续
- 审计轮转 / 配额、`runIndex` 公开 API、路由级 `internal_error` 包装审计
