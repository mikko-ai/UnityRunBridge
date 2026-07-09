# Skill 体系与 Project Skill Creator 设计

日期：2026-07-09
状态：设计定稿，待实现

## 一、背景与问题

unityctl 当前随 CLI 包分发一份官方 agent skill（`skill_assets/SKILL.md`，约 340 行），由 `unityctl skills init/update` 安装到项目的 `.agents/skills/unityctl/`。随着垂直能力（Phase 0-4）全部并入，出现三个问题：

1. **官方 skill 单文件持续膨胀**。触发后整份进入 agent 上下文，且随 scenario v2、MCP 等后续能力还会继续增长。
2. **通用工具与项目知识之间存在鸿沟**。`unityctl hierarchy` 能回答"路径 X 下有什么"，但回答不了"这个游戏里什么算一个界面"。后者是项目知识：命名约定（界面以 `Panel` 结尾）、标记组件（都挂某个 UI 基类）、根结构、置顶机制。没有这份知识，agent 每次任务都要盲探（逐层 `tree` 展开），慢且可能归纳错；这份知识又不能写进官方 skill——一写就变成错误的通用知识。
3. **用户自定义 skill 的成本高**。用户要精准使用 hierarchy 能力，必须先学会它再手写项目 skill，这与"降低 agent 使用 Unity 的门槛"的产品目标相悖。

本设计包含三部分：官方 skill 目录化重构、项目 skill creator、用户扩展约定。

## 二、总体结构

```text
随 CLI 包分发（skills init/update 管理，update 整体覆盖）：
.agents/skills/
  unityctl/                          # 官方参考手册（主动调用）
    SKILL.md                         # 精简主文件：核心工作流 + 能力索引
    references/                      # 按需加载的深度参考
      hierarchy.md
      interaction.md                 # click/input/set-value/record
      scenario.md
      profiling-build-health.md
      error-codes.md
  unityctl-project-skill-creator/    # creator（被动调用）
    SKILL.md                         # 路由 + 共享原则
    flows/
      ui-location.md                 # v1 唯一流程：UI 定位方法论

用户自建（skills update 永不触碰）：
.agents/skills/
  <游戏名>-ui/SKILL.md               # creator 生成物（主动调用）
  <用户自定义>/SKILL.md              # 用户手写的项目流程 skill
```

## 三、官方 unityctl skill 目录化（渐进式披露）

**不拆成多个按能力划分的 skill**：所有能力共享同一个 CLI 和同一套心智模型（session、状态收敛、JSON 信封、错误码），拆分会导致触发描述互相重叠、共享内容重复、版本同步变成 N 份。

**也不维持单文件**：改为渐进式披露——

- `SKILL.md` 收缩到百行以内：frontmatter、「改完代码后验证」主链路（refresh → play → stop → summary 判读）、环境准备、能力索引表（每个能力 2-3 行 + 指向 `references/` 对应文件）。
- `references/` 承载深度内容：hierarchy 子命令详解与消歧规则、UI 操作与录制、scenario 文件结构与断言模型、profiling/build/health、完整错误码表。agent 需要时才读对应文件。
- 版本号仍写在主文件 frontmatter 的 `x-unityctl-version` 字段。

## 四、`skills.py` 分发改造

从"分发单文件"改为"分发目录"，语义保持不变：

- `skills init`：目标 skill 目录已存在则保持原样（`already_installed`），否则整目录写入。
- `skills update`：内容有差异则**整目录覆盖刷新**（先删后写，避免残留已删除的旧文件），无差异返回 `up_to_date`。
- 官方分发物为两个 skill 目录：`unityctl` 与 `unityctl-project-skill-creator`，一次 init/update 同时处理两者。
- 版本占位符 `__UNITYCTL_VERSION__` 机制保留，仅作用于各 skill 的主 `SKILL.md`。
- 用户自建的 skill 目录（不在分发清单内）永不触碰。

需同步更新 `tests/test_skills.py`：目录安装、整目录覆盖、用户目录不受影响、版本渲染。

## 五、Project Skill Creator 设计

### 5.1 定位

一句话：**它是"知识蒸馏"过程的引导者——把只存在于项目里的 UI 约定，蒸馏成一份 agent 可加载的项目 skill；它自己不承载任何项目知识。**

creator 不是程序，是一份给 agent 看的操作剧本：什么阶段探测什么、访谈问什么、怎么验证、产物长什么样，全部固定，保证不同用户跑出来的产物结构一致。

### 5.2 结构：封闭路由 + 流程文件

- `SKILL.md`（入口）：共享原则（见 5.3）+ 知识域路由表。路由表是**封闭枚举**：明确列出支持的知识域及其判断特征；用户诉求不属于任何已知域时，明确回答"该类知识 creator 尚不支持，建议手写进项目 skill"，禁止 agent 即兴发明新流程。
- `flows/<知识域>.md`：单个知识域的探测步骤、访谈剧本、产物模板。只写该域特有内容，不重复共享原则。
- v1 只有一个 flow：`ui-location.md`。目录结构按扩展设计，但不预建空流程——未来的知识域（gameplay 命令、scenario 编写等）等真正要做时再写。

扩展方式：新增知识域 = 新增一个 flow 文件 + 路由表加一行，已有流程零改动。

### 5.3 共享原则（写在入口 SKILL.md，所有 flow 遵守）

1. **约定优先于路径**。产出以规则层（架构级约定）为主体，规则腐烂慢、压缩率高、能直接翻译成查询；不生成大而全的路径快照。
2. **验证优先于生成**。每条候选规则写入前必须机械验证：翻译成 `unityctl hierarchy find` 查询当场跑一遍，结果与预期比对，通过才写入，且验证过的查询本身作为示例写进生成物。
3. **诚实原则**。例外如实记录；覆盖率不足的规则标注"部分适用"及范围；完全无规律时诚实输出"该项目无统一约定"并降级为探测指引——这是合法产物，不算失败。禁止写入未经验证的规则。用户口述、无法机械验证的信息可以写入，但必须标注来源（`用户口述，未验证`）。
4. **生成物克制**。只写项目知识，不复述任何 unityctl 用法（用法在官方 skill 里，两处写必然两处过时）；物理形态为单份 markdown，不做独立知识库系统。
5. **内置自愈**。生成物末尾固定一节自愈指引：查询失效（`node_not_found` 等）时先用规则层重新探测，定位成功后提示用户更新本文件。知识过时的代价是"多一轮查询"，不是"任务失败"。

### 5.4 v1 flow：ui-location（UI 定位方法论）

覆盖三个问题，**不做具体界面的知识**（不列界面清单、不记"某界面怎么打开"）：

1. 界面存在于哪几个树形根节点下（含 `DontDestroyOnLoad` 常驻层）。
2. 想枚举当前有哪些界面，从哪儿查、怎么判断什么算一个界面（识别规则 → 一条 `find` 查询）。
3. 怎么判断哪个界面在最上方（本项目的置顶机制）。

执行流程五阶段：

```text
A 环境检查   doctor → start → status；Editor 不可用则整体降级为纯问答模式
B 探测       play → hierarchy roots → 有限深度 tree → 常见 UI 组件/命名采样
             → 少量 inspect 抽查组件构成（采样深度与节点数写死上限，避免大项目扫穿）
C 归纳       候选规则限四类：命名后缀规律 / 公共标记组件 / UI 根结构 / 置顶机制
D 验证补全   每条候选规则 → find 查询验证；置顶机制的验证：请用户依次打开两个界面，
             跑置顶查询比对实际情况；访谈 ≤ 5 个问题（典型 2-3 个）
E 生成       按固定模板写入 .agents/skills/<游戏名>-ui/SKILL.md
```

置顶机制的常见形态（flow 中给 agent 的判别提示）：同一 Canvas 下以 sibling 顺序决定；每界面独立 Canvas 以 `sortingOrder` 决定（查询：`hierarchy find --component Canvas --sort-by Canvas.sortingOrder --desc --page-size 1`）；UIManager 内部栈管理（hierarchy 看不出来，诚实写明"以 sibling 顺序近似"或"需 gameplay 命令查询"）。

生成物固定模板（六节）：

1. **frontmatter**：`name`、`description`（触发条件："在 <游戏名> 中定位/枚举/操作 UI 时使用"），主动调用。
2. **UI 根节点**：界面存在于哪几棵子树。
3. **界面识别与枚举**：识别规则 + 验证过的枚举查询。
4. **最上方判断**：本项目置顶机制 + 对应查询。
5. **例外清单**：不符合规则的部分。
6. **自愈指引**：规则失效时的标准重探测动作。

再次触发 creator 且生成物已存在时，先询问"全量重建还是只更新部分内容"，做增量访谈。

### 5.5 调用模式

- **creator：被动调用**（frontmatter 设 `disable-model-invocation: true`）。生成项目 skill 是一次性、有副作用、需用户配合的流程，必须用户显式触发（如 `/unityctl-project-skill-creator`），agent 不得在普通任务中顺手执行。
- **生成物：主动调用**。agent 操作该项目 UI 时应自动加载。
- 两者调用模式相反，这个差异本身是设计的一部分。

### 5.6 合格产物标准

- 规则层坚持硬门槛：条条经 `find` 验证，验证不过不进规则层。
- 用户口述且无法机械验证的信息不丢弃，写入时标注来源。
- 无统一约定时的诚实降级产物（探测指引 + "无统一约定"声明）是合法结果。

## 六、v1 范围

### 做

| 项 | 内容 |
|---|---|
| 官方 skill 目录化 | `unityctl` skill 拆成主文件 + `references/` |
| 分发改造 | `skills.py` 单文件 → 目录分发，含两个官方 skill；更新对应测试 |
| creator skill | 入口 `SKILL.md`（路由 + 共享原则）+ `flows/ui-location.md` |
| 生成物模板 | 固定六节（见 5.4） |
| 扩展文档 | 官方 skill 或 README 中补一节「如何为你的项目编写自定义 skill」 |

### 不做（v1 明确砍掉）

| 不做 | 原因 |
|---|---|
| 具体界面清单 / 锚点路径表 / Prefab 资产扫描 | 腐烂快；v1 只做定位方法论 |
| 新 CLI 子命令、Bridge 改动 | creator 全部实现就是 skill 文本 |
| gameplay / scenario / 日志规则知识域 | 另行知识域；v1 路由表仅含 ui-location，未来按需新增 flow |
| 自动更新、定时重扫、文件监听 | 过重；更新 = 重跑 creator 或自愈时手改 |
| 独立知识库系统（DB / 向量化 / 结构化存储） | 知识量级撑不满一份 markdown |
| 跨项目知识复用、UI 框架预设自动套用 | 易产生假规律 |
| 在生成物里复述 unityctl 用法 | 双源过时 |
| `skills init --template project` 模板命令 | 被 creator 覆盖大部分场景，暂不做 |

## 七、成功标准与量化约束

成功标准（满足即算做成）：

1. 用户显式触发 creator 后，在典型项目上能得到可用的 `.agents/skills/<游戏名>-ui/SKILL.md`。
2. 写入的每条识别规则都附带当场跑过的 `find` 示例（或明确标注"用户口述，未验证"）。
3. 后续 UI 任务中，agent 能用规则层把"枚举界面 / 找最上方界面"从盲探变成 1-2 次精准查询。
4. 无统一约定时诚实降级，不算失败。

量化约束（写进 flow 剧本）：

- 人工访谈 ≤ 5 个问题（典型 2-3 个：确认根节点、抽查识别规则、验证置顶机制）。
- 探测有写死的深度与采样上限，单次 creator 目标时长 10-20 分钟以内。
- 规则层能验证几条写几条；0 条规则 + 诚实声明 = 合法产物。

## 八、风险与对策

| 风险 | 对策 |
|---|---|
| 归纳出的规则太弱（覆盖率低） | 诚实标注"部分适用"+ 范围；产物价值随项目约定清晰度缩放，如实呈现 |
| 大项目探测慢、噪声大（对象池、隐藏节点） | 探测深度/采样上限写死在 flow 里；`--active-only` 优先 |
| 生成物长期无人维护 | 规则层为主体（腐烂慢）+ 自愈指引兜底；接受口述类信息逐步过时 |
| creator 或生成物开始复述 CLI 用法 | 模板中机械禁止；review 时检查 |
| 路由被 agent 即兴扩展 | 路由表封闭枚举，不认识的知识域明确拒绝 |

## 九、测试与验收

- Python 单测：`skills.py` 目录分发（init 不覆盖、update 整目录刷新、用户目录不触碰、版本渲染、两个官方 skill 同时分发）。
- 人工验收：在真实 Unity 项目上完整跑一次 creator（Editor 可用 + 纯问答降级两条路径），检查生成物六节齐全、规则均带验证示例、访谈次数在约束内。
- 官方 skill 目录化后，抽查 agent 在典型任务（写 scenario、查错误码）中能否按索引找到对应 reference 文件。

## 十、落地顺序

1. `skills.py` 目录分发改造 + 测试（其余一切的前置）。
2. 官方 `unityctl` skill 拆分为主文件 + `references/`。
3. creator：入口 `SKILL.md` + `flows/ui-location.md` + 生成物模板。
4. 扩展文档（如何手写自定义项目 skill）。
5. 真实项目人工验收，按反馈迭代 flow 剧本。
