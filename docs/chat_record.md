# 梳理 agent 技术选型

> 我们现在要进行关于垂直领域的agent开发，也就是我想要做一个自己的agent,我需要进行技术选型，我需要的这个agent,可以支持人机交互，也就是类似codex,同时也支持agent与agent 之间的交互。来聊聊技术选型吧，我们最好循序渐进，一点一点展开，不要上来就长篇大论

<details><summary>3 previous messages</summary>

> 我会先按已安装的 Superpowers 规范加载相关技能；这次主要是对齐“怎么逐步讨论技术选型”，不会一上来铺满架构图。
>
> 我正在用 `superpowers:using-superpowers` 和 `superpowers:brainstorming`：前者确保流程不乱，后者适合这种从想法逐步收敛到设计/技术选型的讨论。先轻量看一下当前项目上下文，再从一个关键问题开始。
>
> 这个 workspace 看起来还很空，`main` 分支也还没有提交记录；所以我们现在更像是在做“产品/架构前置选型”，不是改现有代码。接下来我会先帮你把问题拆小，从最影响技术路线的入口问起。
</details>

好，我们慢慢来。

我先把这个 agent 的技术选型拆成几层：

1. **交互层**：用户怎么和 agent 聊，类似 Codex 的 chat / terminal / task progress / approval flow。
2. **Agent runtime**：单个 agent 怎么规划、调用工具、记忆上下文、执行任务。
3. **多 agent 协作层**：agent 与 agent 之间怎么分工、通信、交接结果。
4. **工具与环境层**：代码执行、文件系统、浏览器、MCP、数据库、外部 API。
5. **部署与权限层**：本地优先、云端服务、沙箱、安全审计、用户授权。

我们先从最关键的分岔开始，不急着选框架。

第一个问题：你更想做的是哪一种形态？

A. **本地开发者 agent**：像 Codex / Claude Code，主要在本地项目里读写文件、跑命令、改代码、和用户协作。
B. **云端业务 agent 平台**：用户通过网页/IM/API 使用，agent 在服务端运行，支持多用户、多租户、任务队列。
C. **混合型**：本地有执行器，云端有调度/记忆/多 agent 协作中心，类似“本地 worker + 云端 control plane”。

我初步感觉你说“类似 Codex，同时支持 agent-agent 交互”，很可能是 **C 混合型**，但你先选一个最接近的方向。

> 也不能说完全是像codex 这样的agent,这样的通用智能体太多了，其实我想要的是，我的agent 更想是一个服务，是一种特定的服务，但是这种特殊的服务支持agent 现有的功能，例如mcp  skill  , 同时也支持定时任务，以及agent loop. 但是此agent 做的是垂直领域的。同时这个agent 也能对通用agent提供一些接口，或者查询的接口，无论这些接口是cli 还 agent 返回，这样做的原因是能够通过通用的编码智能体来进行一些验证操作，毕竟此agent是通过通用编程agent生成的，至于人机交互，也就是人可以通过自然语言或者ui等方式进行交互

明白，这个定位更清楚了。

你要做的不是“另一个 Codex”，而是一个 **垂直领域 Agent Service**：

它本身提供某种特定服务，比如分析、审计、生成、监控、验证、研究、运营自动化等；同时它具备 agent 能力：

- 可以通过自然语言或 UI 和人交互
- 可以跑 agent loop，自己规划、调用工具、产出结果
- 支持 MCP / skills / tools 等扩展机制
- 支持定时任务、后台任务、持续监控
- 对外暴露接口，让通用编程 agent 可以调用它、验证它、查询它
- 既可以返回自然语言，也可以返回结构化结果、CLI 输出、API 响应、报告、文件等

所以技术选型的核心不是“选一个聊天框架”，而是选一个 **垂直 agent 服务运行时 + 对外协议层 + 人机交互层**。

我建议我们下一步先不要急着选 LangGraph、CrewAI、MCP、FastAPI、Temporal 这些具体东西，而是先确定它的“服务边界”。

第一个关键问题：

你的这个垂直 agent，主要服务的领域是什么？

比如：

A. **代码/软件工程类**：测试、审计、重构、CI 分析、架构评审
B. **数据/分析类**：指标诊断、报表、BI、数据质量、市场研究
C. **内容/创意类**：文档、营销、视频、设计、品牌资产
D. **业务运营类**：客服、销售、CRM、工单、自动化流程
E. **安全/合规类**：策略检查、审计、权限、风险评估
F. 其他，你可以直接描述

这个答案会决定：它更像“工具调用型 agent”，还是“工作流型 agent”，还是“知识服务型 agent”。

> 关于服务的领域，这也是我们现在比较重要的讨论，首先我是一名unity 游戏开发者，我也是一名一人超级公司的创始人，现在我们要讨论的是需求，现在的问题是，关于unity 游戏开发者，有哪些agent service 的需求，我们可以做一个市场调研

<details><summary>2 previous messages</summary>

> 我会把这一步当成“垂直 Agent Service 机会调研”，先用公开资料做需求面和竞品面的粗筛，不直接跳到产品结论。因为市场和 Unity 生态变化很快，我会查最新资料，再把结论压缩成几类可讨论的机会。
>
> <details><summary>Searched the web</summary>
>
> <details><summary>Searched the web</summary>
>
> - Searched the web for `Unity Muse AI assistant game development features 2026`
> - Searched the web for `Unity game development pain points debugging build time shader compilation performance profiling survey`
> - Searched the web for `Unity official MCP Server docs`
> - Searched the web for `https://unity.com/resources/gaming-report`
> - Searched the web for `Unity 2026 Gaming Report AI developers Unity Muse`
>
> </details>
>
> </details>
</details>

可以。我们先做一轮很轻的市场调研，不急着下结论。

**初步判断**
截至 2026-06-30，Unity 生态里“通用 AI 助手”这条路已经很拥挤：Unity 官方已经在推 Unity AI、Unity Assistant、Unity MCP，Asset Store 也有 AI hub。也就是说，如果我们做“能在 Unity 里聊天、生成代码、改场景”的泛用助手，会正面撞官方和开源 MCP 工具。

更有机会的方向，反而是 **垂直 Agent Service**：不是替代 Unity Editor 里的助手，而是围绕某个高频、高痛、可验证的 Unity 工作流，提供自动化服务。

**我看到的需求簇**
1. **Build / CI / 发布诊断 Agent**
   帮 Unity 开发者分析构建失败、Addressables、Cloud Build、iOS/Android 打包、shader variant、包体大小、依赖冲突。这个痛点很工程化，也适合 agent 自动读日志、改配置、跑验证。

2. **性能优化 / Profiling Agent**
   面向移动端、XR、WebGL、小游戏。自动分析 Profiler 数据、内存、GC、Draw Call、资源加载、帧率波动，然后给出可执行修复建议。

3. **项目健康检查 Agent**
   像“Unity 项目体检服务”：检查 asmdef、Packages、资源目录、Prefab 引用、Addressables 配置、代码规范、Editor 脚本风险、升级 Unity 版本风险。

4. **资源与 Asset Store 决策 Agent**
   现在 AI 内容、Asset Store 质量、插件兼容性都很混乱。可以做“插件/资产采购前审计”：查兼容版本、维护状态、依赖风险、替代方案、是否适合当前项目。

5. **玩法原型验证 Agent**
   不是“帮你做完整游戏”，而是把设计想法转成最小 Unity prototype，并自动跑 smoke test / play mode test / editor validation。这个适合 solo dev，但和官方 Unity AI 更接近，竞争会更强。

6. **垂直发行/运营 Agent**
   比如 Steam 页面检查、移动端商店素材规范、埋点完整性、A/B 配置、版本发布 checklist、崩溃日志归因。这更偏“一人公司”的商业闭环，不只是开发工具。

**我目前更看好的切入点**
我会优先看 **Build / CI / 发布诊断 Agent** 或 **项目健康检查 Agent**。

原因是它们有三个好处：

- 痛点明确：失败日志、配置、包依赖、构建耗时都是真问题。
- 容易验证：agent 可以给出 patch、命令、报告，通用 coding agent 也能复查。
- 不直接撞 Unity 官方的“创作型 AI 助手”：更像专业服务，而不是聊天机器人。

**公开信号**
Unity 官方正在强化 AI 和 MCP，说明“AI + Unity Editor”方向成立，但泛用入口会被官方占住：[Unity AI](https://unity.com/features/ai)、[Unity MCP docs](https://docs.unity3d.com/Packages/com.unity.ai.assistant%402.0/manual/unity-mcp-overview.html)、[Unity MCP blog](https://unity.com/blog/mcp-servers-game-development)。Unity 2026 报告也显示开发者已经大量使用 AI 辅助编码：[Unity Gaming Report](https://unity.com/resources/gaming-report)。同时，社区里长期存在 build、Addressables、Cloud Build、Asset Store 质量和 AI 内容筛选等具体痛点：[Addressables Cloud Build discussion](https://discussions.unity.com/t/content-update-builds-fail-on-unity-cloud-build-what-is-the-right-workflow/909459)、[Asset Store AI discussion](https://discussions.unity.com/t/lets-talk-about-the-asset-store-defining-made-with-ai/1713385)。

下一步我们先收敛目标用户。你更想优先服务哪一类 Unity 开发者？

A. **像你一样的一人公司 / solo dev**
B. **2-10 人 indie 团队**
C. **中大型商业项目里的 Unity 工程团队**
D. **Asset Store 插件/工具作者**

> 首先说明一点，unity游戏开发是我的工作，一人超级公司是我的副业，我们可以从两个方面来开始这个讨论，要么是能够提高我的工作效率，这样我就有更多时间开始副业，要么就是告诉我副业如何开始。

<details><summary>1 previous message</summary>

> 收到，这个边界很关键：Unity 不是抽象市场，而是你当前时间杠杆的主场；副业也不是随便创业，而是要从你的能力和可复用资产里长出来。我们先把讨论拆成两条线，但只问一个问题来决定先看哪条。
</details>

明白。那我们现在其实有两个可选起点：

**路线 1：先提高你 Unity 正职效率**
目标是做一个“给你自己用”的垂直 Agent Service。它帮你省时间，比如构建诊断、项目体检、日志分析、性能优化、自动生成验证脚本、整理技术方案。
优点是需求真实、你自己就是第一个用户，容易验证价值。缺点是早期可能更像内部工具，商业化要再提炼。

**路线 2：先设计一人超级公司的副业入口**
目标是找一个可以产品化的 Unity/游戏开发者 Agent Service。它可能从你的工作流痛点出发，但一开始就按可售卖服务来设计。
优点是更接近商业目标。缺点是容易陷入市场假设，需要更快做用户验证。

我建议先走 **路线 1 → 路线 2**：先找你自己每周最浪费时间、最重复、最能被 agent 化的 Unity 工作流，做成自用服务；一旦它真的每周帮你省下时间，再判断哪些能力可以卖给别人。

第一个问题：

在你的 Unity 工作里，最近一两个月最消耗你时间的是哪类事情？

A. 构建、打包、平台适配、CI、发布问题
B. Debug、日志分析、线上 crash、复现问题
C. 性能优化、Profiler、内存、卡顿、包体
D. 需求开发、写 gameplay / UI / 工具代码
E. 项目维护、资源管理、Prefab、Addressables、Package 升级
F. 技术方案沟通、文档、评审、排期、带人协作
G. 其他，你直接说具体场景

> 尤其是需求的开发，业务逻辑等任务，目前我已经在cursor或者codex 有了一小部分的agent的配置，这部分主要还是借助于通用编程智能体来完成，首先我构建了工程大体知识库，其次编写以一些技能（主要服务于如何获取任务需求，如何提交代码，任务展开流程,查询游戏配表的skill），但是现在卡在了验证这一步，目前的验证，还是需要人为去运行，点击等等操作。验证这一步目前比较耗时，另一部分耗时的是UI prefab 的拼接，也就是我们要通过效果图来拼UI prefab,这是目前工作中的瓶颈。

这下非常具体了，而且我觉得你已经离一个真正有价值的垂直 Agent Service 很近了。

你现在的瓶颈其实不是“让 agent 写代码”，而是：

1. **Agent 产出的代码/配置/Prefab 变更如何被自动验证**
2. **视觉稿到 Unity UI Prefab 的拼装如何半自动或自动化**

这两个方向都很有价值，但我会优先推荐先做 **验证 Agent Service**。

原因很简单：你已经在 Cursor / Codex 里有任务拆解、知识库、配表查询、提交流程等能力了，缺的是最后的闭环。如果验证可以自动化，通用编程 agent 才能从“帮你写”变成“帮你写完并证明它大概率可用”。

这个服务可以长这样：

**Unity Verification Agent Service**

它不负责泛泛写代码，而是给通用 agent 提供验证接口：

- 输入：任务描述、改动 diff、目标场景、目标功能、配表信息、验证类型
- 执行：启动 Unity batchmode、运行 EditMode / PlayMode tests、打开指定 scene、执行自定义 Editor validation、跑 UI smoke flow、收集 log
- 输出：结构化结果，比如 `pass/fail`、错误日志、截图、关键断言、可复现步骤、建议修复点
- 对人：提供 UI 或自然语言报告
- 对 agent：提供 CLI / MCP / HTTP API，让 Codex/Cursor 能调用它

而 **UI Prefab 拼接 Agent** 更像第二阶段。它也很诱人，但更难：需要设计图理解、Unity UI 约束、Prefab 层级规范、资源匹配、字体/九宫格/组件绑定、动态布局验证。它最好也依赖验证能力，比如拼完后自动截图，和效果图做视觉对比。

所以我建议路线是：

**第一阶段：Verification Agent**
把“人肉运行、点击、看日志、截图确认”变成服务。

**第二阶段：UI Prefab Assembly Agent**
把“看效果图拼 UI Prefab”变成半自动工作流，并用第一阶段的验证服务兜底。

第一个问题我们聚焦一点：

你现在最想自动化的“验证”是哪一类？

A. **代码逻辑验证**：运行 Unity Test Framework、检查业务逻辑、配表逻辑、状态流转
B. **场景/玩法验证**：打开 scene，模拟点击/移动/战斗/流程，确认功能跑通
C. **UI 验证**：打开界面、点击按钮、检查文本/红点/列表/弹窗/截图
D. **构建验证**：跑打包、检查编译错误、资源缺失、平台问题
E. **提交流程验证**：改动后自动跑 lint/test/build/checklist，决定能不能提交

我猜你的核心可能是 **B + C**，也就是“需要人为运行和点击”的那部分。

> 我们抛开我做了什么，现在探讨的是需求，也就是在我的使用场景中，一个关于unity 游戏运行的这个service 算是个需求，目前我能能够想到的是如何，如何指定游戏的运行，如何停止，这个是最初级，之后，需要的是如何将游戏画面结构化，这样LLM 就能够理解游戏展示的内容了（这是非常难的），另一个思路是截图给多模态的模型来分析，我觉得这个不太靠谱，这样会非常拖慢节奏。之后就是如何让agent去操作游戏，这就更难了。这些是我大概能想到的需求，我们现在要做的就是来丰富需求，并对需求进行评估，评估需求实现的难度，是否能够精准解决这个需求，其次就是这个需求能够给我们带来什么？创造怎样的价值，如果价值低实现难，我们就先不做

对，这里我们可以把需求拆成一条“从低级控制到高可信验证”的能力阶梯。

我先给一个初版需求地图，按 **价值 / 难度 / 精准度** 粗评。

| 需求 | 说明 | 难度 | 精准度 | 价值 | 初步建议 |
|---|---|---:|---:|---:|---|
| 启动/停止游戏 | 指定 Unity project、scene、platform、参数，启动 Editor PlayMode 或 standalone build | 低 | 高 | 中 | 必做，基础设施 |
| 收集运行日志 | 捕获 Unity log、exception、warning、自定义埋点 | 低 | 高 | 高 | 必做 |
| 指定验证入口 | 运行某个 scene、打开某个 UI、跳到某个关卡/状态 | 中 | 高 | 高 | 必做 |
| 游戏状态结构化 | 读取当前场景对象、UI 树、玩家状态、任务状态、配表 key、网络状态 | 中到高 | 高 | 极高 | 核心能力 |
| Agent 操作游戏 | 点击按钮、输入文本、触发事件、调用 gameplay command | 中到高 | 中到高 | 高 | 核心能力，但要分层做 |
| 自动断言 | 验证 UI 文案、按钮可用、状态变化、奖励到账、红点出现等 | 中 | 高 | 极高 | 优先级很高 |
| 截图分析 | 截图给多模态模型判断画面 | 低到中 | 中到低 | 中 | 只做兜底，不做主路径 |
| 视觉 Diff | 对比基准图和当前截图 | 中 | 中 | 中 | UI 场景有用，但别一开始依赖 |
| 回放脚本 | 记录人工操作，转成可重复执行验证脚本 | 中 | 高 | 高 | 很值得做 |
| 失败诊断 | 失败后自动定位 log、状态、最近 diff、可能原因 | 高 | 中 | 高 | 第二阶段 |
| 自然语言生成测试 | “验证新手引导第一步”自动生成操作和断言 | 高 | 中 | 高 | 后做，依赖前面能力 |

我的判断：真正的 MVP 不应该从“让 LLM 看懂游戏画面”开始。那条路听起来智能，但慢、不稳定、成本高，而且很难精准验证。

更靠谱的主路径是：

**让游戏自己暴露结构化状态和可操作接口。**

也就是做一个 Unity Runtime Verification Bridge：

- LLM 不直接“看画面”
- Agent 通过 service 查询：当前有哪些 UI、按钮、文本、panel、scene、player state、quest state
- Agent 通过 service 操作：click button、open panel、set test account、jump scene、advance tutorial step
- Service 返回结构化结果、日志、截图作为辅助证据

这样价值很清楚：它把“人肉运行和点击”变成可重复、可审计、可让 coding agent 调用的验证过程。

我会把需求优先级排成这样：

**P0：运行控制 + 日志 + 状态查询**
没有这个，后面都谈不上。

**P1：结构化 UI 树 + 操作接口 + 自动断言**
这是从“能运行”到“能验证”的关键跃迁。

**P2：录制/回放人工验证流程**
这个对你很有价值，因为你可以先手动跑一次，然后以后交给 agent 跑。

**P3：失败诊断和修复建议**
这会让它从 verification service 变成真正的 agent service。

**P4：多模态截图理解**
作为兜底，不作为主干。比如结构化信息缺失、视觉错位、特效异常时再用。

这里有一个关键分叉，会影响所有需求评估：

你的 Unity 项目 UI 主要是用哪一套？

A. **UGUI / Canvas / GameObject + RectTransform**
B. **UI Toolkit**
C. **自研 UI 框架，基于 UGUI 或别的封装**
D. **混合使用**

> 首先，我想做的是无侵入性的service,或者少量侵入性的service。其次，你又开始长篇大论了，我们需要循序渐进，先把需求分为几个大的方向，然后慢慢展开

对，是我铺太开了。我们先收回来。

加上你说的 **无侵入 / 少量侵入**，需求可以先分成这几个大方向：

1. **运行控制**
   启动 Unity、指定场景/账号/参数、进入 PlayMode 或运行包、停止、重启、清理状态。

2. **运行观测**
   收集日志、异常、截图、性能数据、窗口状态、当前进程状态。这个方向最适合无侵入起步。

3. **游戏内容结构化**
   让 service 理解“当前游戏里有什么”：UI、文本、按钮、弹窗、玩家状态、任务状态、资源状态。
   这是核心难点，也最决定价值。

4. **游戏操作**
   让 agent 能操作游戏：点击、输入、等待、选择、拖拽、触发某个流程。
   无侵入可以做，但会脆；少量侵入可以稳定很多。

5. **验证与报告**
   判断这次运行是否通过：有没有异常、UI 是否出现、状态是否正确、流程是否完成，并输出给人或通用 coding agent。

6. **对外接口**
   给 Codex / Cursor / CLI / MCP / HTTP 调用，比如：
   `run_game`、`get_state`、`click_ui`、`assert_text`、`stop_game`、`get_report`。

我建议我们先只展开一个方向：**运行控制**。
因为它最基础、最容易无侵入、也能最快产生一个可用 service 雏形。

如果你同意，我们下一步就只讨论：
**“无侵入/少侵入的 Unity 游戏运行控制 service，到底需要支持哪些动作？”**

> 好的

好，那我们只看 **运行控制** 这一块。

我先给它一个很窄的定义：

**运行控制 service = 让外部 agent 能稳定地启动、停止、重启 Unity 游戏，并指定这次运行的上下文。**

先不管看懂画面，也不管点击操作。

这一层可以拆成 5 个小需求：

1. **启动 Unity Editor**
   指定 Unity project path、Unity version、scene、启动参数。

2. **进入 PlayMode**
   打开指定 scene 后自动进入 PlayMode。

3. **启动 standalone build**
   不走 Editor，直接运行 Windows/Mac/Android/iOS 包。

4. **停止/重启**
   停止 PlayMode、关闭 Editor、杀掉游戏进程、重新开始一次运行。

5. **运行会话管理**
   给每次运行一个 `session_id`，记录启动时间、目标场景、日志路径、进程状态、退出码。

这一层的价值是：以后 Codex/Cursor 不需要你手动点 Unity，可以直接说：

```bash
unity-agent run --project /path/game --scene LoginScene
unity-agent status <session_id>
unity-agent stop <session_id>
```

初步评估：

| 需求 | 难度 | 价值 | 优先级 |
|---|---:|---:|---:|
| 启动 Editor | 低 | 高 | P0 |
| 进入 PlayMode | 中 | 高 | P0 |
| 启动 standalone build | 低 | 中 | P1 |
| 停止/重启 | 低 | 高 | P0 |
| session 管理 | 中 | 高 | P0 |

这里最值得先确认的是一个问题：

你最常需要验证的是 **Editor PlayMode**，还是 **打出来的 standalone 包**？

> 我们先讨论一下这个需求的核心技术难点，如何启动Editor 如何 启动/停止/暂停

<details><summary>2 previous messages</summary>

> 我们这一步只拆“运行控制”的技术难点，不扩到验证和 UI。Unity 的命令行、Editor API 细节会随版本变，我先快速查一下官方资料，避免凭记忆说错。
>
> <details><summary>Searched the web</summary>
>
> <details><summary>Searched the web</summary>
>
> - Searched the web for `Unity Manual command line arguments batchmode executeMethod official`
> - Searched the web for `Unity 6000 EditorApplication EnterPlaymode isPlaying official docs`
>
> </details>
>
> </details>
</details>

可以。这里的核心难点其实分两层：

**1. 启动 Editor 不难，稳定启动难**

外部 service 可以直接用 Unity 可执行文件启动：

```bash
Unity -projectPath /path/to/project -logFile /path/to/log
```

Unity 官方命令行参数支持 `-projectPath`、`-logFile`、`-batchmode`、`-executeMethod` 等，所以“打开某个项目”本身不是难点。难点在于：

- 怎么找到正确 Unity 版本
- 项目是否已经被另一个 Editor 打开
- 第一次打开是否在 import / compile / package restore
- 启动成功和“可操作”不是一回事
- macOS / Windows 路径差异
- batchmode 适合自动任务，但不适合需要真实画面/点击的验证

所以启动 Editor 的 MVP 应该不是“能打开进程”，而是能判断：

```text
Editor process exists
Project loaded
Scripts compiled
Target scene opened
Editor ready
```

**2. 启动/停止/暂停 PlayMode，纯无侵入会很别扭**

如果只是外部 service，不往 Unity 项目里放东西，它最多能：

- 启动 Editor 进程
- 关闭/杀掉 Editor 进程
- 通过系统级 UI 自动化去点 Play/Pause 按钮

但这不稳定，也不优雅。

更靠谱的是 **少量侵入**：放一个很薄的 Editor Bridge 包。它只负责接收外部命令，然后调用 Unity Editor API：

- 启动 PlayMode：`EditorApplication.EnterPlaymode()` 或 `EditorApplication.isPlaying = true`
- 停止 PlayMode：`EditorApplication.ExitPlaymode()` 或 `EditorApplication.isPlaying = false`
- 暂停/恢复：`EditorApplication.isPaused = true/false`

这些 API 在 Unity 官方文档里都有：
[Editor command line arguments](https://docs.unity3d.com/6000.1/Documentation/Manual/EditorCommandLineArguments.html)、[EnterPlaymode](https://docs.unity3d.com/6000.0/Documentation/ScriptReference/EditorApplication.EnterPlaymode.html)、[ExitPlaymode](https://docs.unity3d.com/6000.1/Documentation/ScriptReference/EditorApplication.ExitPlaymode.html)、[isPaused](https://docs.unity3d.com/6000.4/Documentation/ScriptReference/EditorApplication-isPaused.html)。

所以我会这样判断：

**无侵入方案**
适合：启动 Editor、停止进程、收集日志。
不适合：稳定进入/退出/暂停 PlayMode。

**少量侵入方案**
适合：稳定控制 PlayMode，并返回明确状态。
代价：项目里要接入一个 Editor-only package。

我认为这里第一个技术结论是：

> 运行控制 service 想要可靠，至少需要一个 Editor-only Bridge。它不碰业务代码，不进 runtime 包，只在 Unity Editor 内提供控制通道。

下一步可以继续只展开这个 Bridge：
它到底应该用 **HTTP、本地 WebSocket、stdin/file command、还是 MCP/CLI 间接调用** 来接收外部命令。

> 有道理，如果说是少量侵入行为的话，就是是我们需要有一个bridge,用于转发，这是个好想法，对比一下这几种方式的优缺点，找出适合我们的，其实这个是否可以做成相对通用的工具？适合其他通用agent 来使用

对，可以做成相对通用的工具，而且这个点很有潜力：**给通用 agent 一个稳定控制 Unity Editor 的接口**。

Bridge 通信方式可以先分成几类：

| 方式 | 优点 | 缺点 | 适合度 |
|---|---|---|---|
| **HTTP 本地服务** | 通用、好调试、Codex/Cursor/脚本都能调、跨语言简单 | Unity 内要起本地 server；要处理端口、生命周期 | **很适合主方案** |
| **WebSocket** | 适合实时状态、日志流、事件推送 | 比 HTTP 复杂；早期可能用不上 | 适合第二阶段 |
| **文件命令队列** | 最稳定、最少依赖，Unity 轮询文件即可 | 慢一点；状态同步麻烦；并发差 | 适合 fallback |
| **stdin/stdout** | CLI 风格干净 | Unity Editor 进程不太适合作为长期 stdin worker | 不太适合 Editor 控制 |
| **MCP Server** | 天然适合给 agent 使用，工具描述清晰 | MCP 不一定适合直接嵌进 Unity；更适合做外层适配 | 适合作为 agent 接口层 |
| **CLI** | 最容易被通用 agent 调用和验证 | CLI 本身不适合长期持有状态，需要后端 bridge | 很适合作为外壳 |

我会推荐这个结构：

```text
通用 Agent / 人
    ↓
CLI 或 MCP Server
    ↓
本地 Unity Control Service
    ↓
Unity Editor Bridge package
    ↓
EditorApplication API
```

也就是说，不要让 Unity Bridge 直接承担所有协议。

**Unity Editor Bridge** 只做一件事：在 Editor 内接收命令并执行，比如：

```text
enter_playmode
exit_playmode
pause
resume
open_scene
get_editor_state
get_logs
```

外面再包一层 **CLI / MCP / HTTP API**，这样它就能给不同 agent 用。

我的初步推荐是：

**第一版：HTTP + CLI**

原因：

- HTTP 适合作为本地 service 协议
- CLI 适合 Codex / Cursor / Claude Code 这类通用编程 agent 调用
- 先不用 WebSocket，日志可以先通过 `get_logs` 拉取
- MCP 可以作为第二层适配，不要一开始把核心绑死在 MCP 上

例如：

```bash
unityctl editor start --project /path/game
unityctl play --project /path/game
unityctl pause
unityctl status
unityctl stop
```

同时暴露 HTTP：

```http
POST /sessions
POST /sessions/{id}/play
POST /sessions/{id}/pause
POST /sessions/{id}/stop
GET  /sessions/{id}/status
```

后面再加 MCP：

```text
tools:
- unity_start_editor
- unity_enter_playmode
- unity_pause
- unity_get_status
- unity_get_logs
```

这样它就比较通用了。

关键判断是：**核心能力不要设计成“某个项目的专用脚本”，而要设计成“Unity Editor 控制协议”。**
项目相关的东西，比如打开哪个 scene、加载哪个账号、进入哪个玩法，可以作为参数或后续扩展。

下一步我们可以只讨论一件事：
这个 `Unity Editor Bridge package` 应该如何被接入项目，才能做到“少量侵入但足够稳定”。

> 好

那我们聚焦：**Bridge package 怎么接入 Unity 项目**。

我觉得可以分三种接入方式：

| 接入方式 | 侵入性 | 稳定性 | 适合场景 |
|---|---:|---:|---|
| **UPM Git package** | 低 | 高 | 最推荐，通用工具化 |
| **复制 Editor 文件夹** | 中 | 高 | 快速试验、公司内项目 |
| **UnityPackage 导入** | 中 | 中 | 给非技术用户分发 |

我推荐 **UPM Git package**。

也就是项目里只加一个依赖：

```json
{
  "dependencies": {
    "com.yourname.unity-agent-bridge": "https://github.com/you/unity-agent-bridge.git"
  }
}
```

这个 package 只包含 Editor 代码：

```text
Packages/com.yourname.unity-agent-bridge/
  package.json
  Editor/
    BridgeServer.cs
    CommandRouter.cs
    EditorState.cs
    PlayModeController.cs
    SceneController.cs
```

它不进 runtime build，不改业务代码，不污染游戏逻辑。

第一版 Bridge 只做 4 件事：

1. **启动本地 HTTP server**
   Unity Editor 打开项目后自动启动，比如监听 `127.0.0.1:xxxxx`。

2. **暴露 Editor 状态**
   返回是否在编译、是否在 PlayMode、当前 scene、是否 paused、Unity version。

3. **执行 PlayMode 控制**
   enter / exit / pause / resume。

4. **打开指定 scene**
   后续运行验证基本都需要这个。

这里有一个很重要的设计点：

**端口不要写死。**

因为你可能同时开多个 Unity 项目。Bridge 可以启动时写一个 discovery 文件，例如：

```text
~/.unity-agent/sessions/{project_hash}.json
```

里面记录：

```json
{
  "projectPath": "/path/to/project",
  "unityVersion": "6000.0.XX",
  "port": 18231,
  "pid": 12345,
  "startedAt": "...",
  "status": "ready"
}
```

外部 CLI/MCP 先读 discovery 文件，再知道该连哪个 Unity Editor。

这样通用 agent 就可以：

```bash
unityctl list
unityctl status --project /path/to/project
unityctl play --project /path/to/project
```

我的判断：

> Bridge package 最小侵入方式 = UPM Editor-only package + 本地 HTTP server + discovery 文件。

下一个小问题：
你更倾向于这个工具一开始服务 **单个打开的 Unity 项目**，还是从第一版就支持 **多个 Unity 项目/多个 Editor 实例**？

> 同意这个方向，第一版本先支持单unity 项目

好，第一版先支持 **单 Unity 项目**，这会让 MVP 清爽很多。

那第一版可以暂时不做复杂 discovery，只做：

```text
固定本地地址：127.0.0.1
默认端口：比如 17890
单 Editor 实例
单 active project
```

Bridge 启动后，外部工具默认连：

```text
http://127.0.0.1:17890
```

第一版运行控制需求可以定成这样：

**Unity Bridge Package**

- Editor 打开项目后自动启动 HTTP server
- 提供 `/status`
- 提供 `/play`
- 提供 `/stop`
- 提供 `/pause`
- 提供 `/resume`
- 提供 `/open-scene`

**unityctl CLI**

- `unityctl status`
- `unityctl play`
- `unityctl stop`
- `unityctl pause`
- `unityctl resume`
- `unityctl open-scene <scene-path>`

先不做：

- 多项目管理
- 端口发现
- MCP
- WebSocket
- 自动点击
- 游戏内容结构化
- 验证断言

这样第一版的价值是：

> 通用编程 agent 可以不碰 Unity UI，直接通过 CLI 控制当前项目的 Editor PlayMode。

这已经能解决一部分“需要我手动点运行/停止”的问题，也给后面的验证服务打基础。

下一步我们可以继续讨论第二块：**运行观测**。
也就是外部 agent 控制游戏跑起来以后，它怎么知道 Unity 当前发生了什么。

> 先不着急讨论第二块，生成第一部分的开发文档 [$superpowers:writing-plans](~/.agents/source_skills/superpowers/skills/writing-plans/SKILL.md)

<details><summary>15 previous messages</summary>

> 我正在使用 `superpowers:writing-plans` 来创建第一部分的实现计划。先只覆盖“单 Unity 项目的 Editor 启动/Play/Pause/Stop 控制”，不把运行观测、结构化画面和操作游戏混进来。
>
> 我会把文档写成可执行的 implementation plan，而不是概念说明：文件结构、任务拆分、测试方式、每步 commit 都会写清楚。范围会克制在第一版：`UPM Editor-only Bridge + 本地 HTTP + Python CLI`。
>
> 我现在锁定一个重要实现细节：Unity API 必须在 Editor 主线程调用，所以 Bridge 的 HTTP request 不能直接在监听线程里操作 `EditorApplication`。计划里会明确用“后台监听 + 主线程队列”的方式，避免第一版就踩稳定性坑。
>
> <details><summary>Created a file</summary>
>
> - Wrote `./docs/superpowers/plans/2026-06-30-unity-editor-control.md` (+1518 -0)
>
> </details>
>
> 计划文件已经生成，我在做一次自检；刚注意到 README 示例里有嵌套 Markdown 代码块，需要把外层 fence 调整一下，避免文档渲染断掉。
>
> 占位符扫描没有发现问题。现在只修正 Markdown 嵌套代码块的格式，然后我会做最后的文件状态检查。
>
> 刚才那条检查命令里反引号被 shell 展开了，我会用单引号重跑。这个只是检查命令的小插曲，不影响文件内容。
>
> <details><summary>Edited a file</summary>
>
> - Wrote `./docs/superpowers/plans/2026-06-30-unity-editor-control.md` (+2 -2)
>
> </details>
>
> 这次 patch 命中了 README 内部第一个代码块的结束 fence，我继续把外层/内层 fence 对齐。Markdown 这种套娃格式就是得手稳一点。
>
> <details><summary>Edited a file</summary>
>
> - Wrote `./docs/superpowers/plans/2026-06-30-unity-editor-control.md` (+2 -2)
> - Wrote `./docs/superpowers/plans/2026-06-30-unity-editor-control.md` (+2 -2)
>
> </details>
>
> 嵌套代码块已经修正到外层四反引号、内层三反引号的形式。接下来我再做一次关键字扫描和 git 状态检查。
>
> 又发现一个 fence 位置还偏了一段：Success 示例提前关闭了 README 外层块。再修一次，这次用 Success/Failure 上下文定点改。
>
> <details><summary>Edited a file</summary>
>
> - Wrote `./docs/superpowers/plans/2026-06-30-unity-editor-control.md` (+2 -2)
>
> </details>
>
> 现在只剩最后一处：Failure 示例需要先用三反引号关内部 JSON，再用四反引号关 README 外层块。我来把这个顺序补正。
>
> <details><summary>Edited a file</summary>
>
> - Wrote `./docs/superpowers/plans/2026-06-30-unity-editor-control.md` (+1 -1)
>
> </details>
</details>

已生成第一部分开发计划，文件在这里：

[2026-06-30-unity-editor-control.md](./docs/superpowers/plans/2026-06-30-unity-editor-control.md)

内容范围只覆盖我们刚定下来的第一阶段：**单 Unity 项目、少量侵入的 Editor-only Bridge、固定 localhost HTTP、Python `unityctl` CLI、支持 start/status/play/stop/pause/resume/open-scene**。我也做了占位符扫描和 Markdown 嵌套代码块检查；这次没有实际实现代码，所以没有跑实现测试，也没有提交 git commit。

Plan complete and saved to `docs/superpowers/plans/2026-06-30-unity-editor-control.md`. 两种执行方式：

1. **Subagent-Driven（推荐）**：每个 task 派一个 fresh subagent，我在任务之间 review，迭代快。
2. **Inline Execution**：就在当前会话里按计划执行，用 checkpoints 分批 review。

你选哪种？

> 我希望文档使用中文进行描述

<details><summary>3 previous messages</summary>

> 我来把计划文档的叙述、任务说明、预期结果都改成中文；代码、命令、文件名、API 名称保持英文，这样既符合你的交互偏好，也不影响后续 agent/工程师照着执行。
>
> <details><summary>Created a file</summary>
>
> - Wrote `./docs/superpowers/plans/2026-06-30-unity-editor-control.md` (+1527 -0)
>
> </details>
>
> 中文版本已经覆盖写入。我现在做一次快速检查：确认没有英文占位提示残留、文件存在且 git 状态正常。
</details>

已把开发计划文档改成中文描述，代码、命令、文件路径和 API 名保持英文。

文件仍在这里：

[2026-06-30-unity-editor-control.md](./docs/superpowers/plans/2026-06-30-unity-editor-control.md)

我也重新扫了一遍占位符，没发现 `TBD/TODO/implement later` 这类残留。当前只是文档变更，尚未提交。

> 下一步我们可以继续讨论第二块：运行观测。

<details><summary>1 previous message</summary>

> 好，我们继续第二块：运行观测。我会先保持颗粒度小，只把它分成几个大方向，然后我们挑一个展开，避免又一下子滑进“大而全架构”。
</details>

运行观测这一块，可以先理解成：

> 游戏/Editor 跑起来之后，外部 agent 怎么知道“现在发生了什么”。

先分 5 个大方向：

1. **进程与 Editor 状态观测**
   Editor 是否还活着、是否在 PlayMode、是否 paused、是否 compiling、当前 scene 是什么。

2. **日志观测**
   Unity Console log、exception、warning、自定义业务 log、最近 N 条日志、按时间/session 过滤。

3. **运行错误观测**
   是否出现红色 error、未处理异常、断言失败、资源加载失败、网络错误。

4. **基础画面观测**
   截图、窗口大小、当前帧时间、是否黑屏/卡死。这里先不做“理解画面内容”。

5. **游戏内状态观测**
   玩家状态、当前 UI、任务状态、战斗状态、配表 key、网络状态。这个价值最高，但也最容易变成侵入式。

如果保持“无侵入 / 少量侵入”的原则，我建议第二块的优先顺序是：

**日志观测 → 运行错误观测 → 基础画面观测 → 游戏内状态观测**

因为日志和错误最容易低侵入接入，也最能立刻帮助 agent 判断“刚才运行有没有炸”。

我们先只展开一个问题：

你更希望第二块的 MVP 先解决哪件事？

A. **让 agent 能读取 Unity Console / Editor log**
B. **让 agent 能判断这次运行有没有 error / exception**
C. **让 agent 能拿到一张当前游戏截图**
D. **让 agent 能知道当前打开了哪个 UI / 处于哪个业务状态**

> A

好，第二块 MVP 先定成：

**让 agent 能读取 Unity Console / Editor log。**

这里也有两个层级：

1. **无侵入读取 Editor log 文件**
   - macOS 一般读 `~/Library/Logs/Unity/Editor.log`
   - 或者读取 `unityctl start-editor --log-file` 指定的日志文件
   - 优点：完全无侵入
   - 缺点：不一定能精确区分本次 session；Unity Console 里清屏/过滤不一定同步

2. **少量侵入：Bridge 捕获 Unity log callback**
   - 在 Editor Bridge 里注册 `Application.logMessageReceived`
   - 缓存最近 N 条 log
   - 提供 HTTP 接口：`GET /logs?limit=100`
   - 优点：结构化、实时、能区分 `Log/Warning/Error/Exception`
   - 缺点：需要 Bridge package，但我们第一部分已经接受这个前提

我建议 MVP 用 **第二种：Bridge 捕获日志**。

原因是它更适合 agent：

```json
{
  "ok": true,
  "logs": [
    {
      "time": "2026-06-30T18:30:00.123Z",
      "type": "Error",
      "message": "NullReferenceException...",
      "stackTrace": "..."
    }
  ]
}
```

然后 CLI 可以支持：

```bash
unityctl logs --limit 100
unityctl logs --type Error
unityctl errors
```

这里先不要做太复杂：

**P0 日志观测需求**

- 捕获 Unity log
- 缓存最近 500 条
- 支持查询最近 N 条
- 支持按类型过滤：`Log` / `Warning` / `Error` / `Exception` / `Assert`
- 提供 `hasErrors` 字段
- CLI 输出 JSON

第一版接口可以是：

```http
GET /logs?limit=100
GET /logs?limit=100&type=Error
GET /errors
```

我觉得这块价值很高，因为通用 agent 最需要的是：
**“我刚才点了 play / 跑了流程，有没有报错？报了什么？”**

下一步我们可以继续只讨论一个技术难点：

日志是应该 **只缓存 Bridge 启动后的 logs**，还是需要同时能读取 **Editor.log 历史文件**？

> 为什么我们不能将本次运行的所有log 写入到日志呢？也就是本次运行的时候的,有没有更好的方式，只有落盘到文件，我们才能真正的去观察，而不是基于编辑器

可以，而且你这个判断是对的：**运行观测最终应该以“本次运行的落盘日志”为准**，而不是只依赖 Editor 内存状态。

Bridge 缓存最近 N 条 log 适合“快速查询”，但它有明显问题：

- Editor 重启后丢失
- agent 事后无法复盘
- 长任务日志可能超过缓存
- 不方便和截图、报告、验证结果归档到同一个 session
- 通用 agent 更喜欢读文件，因为文件可审计、可 diff、可附加到报告

所以更好的设计应该是：

**每次运行创建一个 session log 文件。**

比如：

```text
.unity-agent/
  sessions/
    2026-06-30_183012_playmode/
      session.json
      editor.log
      unity-console.jsonl
      summary.json
```

其中：

- `editor.log`：Unity 原始 log 文件，可以来自 `-logFile` 或复制/截取 Editor.log
- `unity-console.jsonl`：Bridge 通过 `Application.logMessageReceived` 捕获的结构化日志，一行一条
- `session.json`：这次运行的 project、scene、startTime、endTime、status
- `summary.json`：错误数量、warning 数量、是否通过、最后错误等

这样 agent 可以：

```bash
unityctl play --session-name login-test
unityctl logs --session latest
unityctl errors --session latest
unityctl session-path latest
```

核心变化是：
**Bridge 不只是提供 `/logs`，还要把 log append 到当前 session 的 jsonl 文件里。**

我会把日志观测分成两层：

**P0：本次 PlayMode session 日志落盘**

- `unityctl play` 创建 session
- Bridge 开始记录 console log 到 `unity-console.jsonl`
- `unityctl stop` 结束 session
- `summary.json` 记录 error/warning/exception 数量
- agent 可以直接读取 session 目录

**P1：实时查询**

- `GET /logs`
- `unityctl logs`
- 方便快速看最近日志，但不是唯一事实来源

这比单纯读 Unity `Editor.log` 更好。因为 Editor.log 是全局日志，噪音大，不天然按“本次运行”切分；而 session log 是我们定义的验证边界。

所以我会修正刚才的建议：

> 日志观测的主路径应该是“session-based 落盘日志”，Bridge 内存缓存只是辅助。

下一步我们可以只讨论一个小点：
**session 的生命周期应该由 `unityctl play/stop` 管，还是由 Bridge 内部根据 PlayMode 变化自动创建/结束？**

> 这个讨论你的建议是什么？我听听你的想法

我的建议：**由外部 `unityctl` 显式创建 session，Bridge 根据 PlayMode 状态做兜底同步。**

也就是主控权在外部：

```bash
unityctl play --session login-flow
unityctl stop
```

执行时大概是：

1. `unityctl play --session login-flow`
2. CLI 创建本次 session 目录
3. CLI 调 Bridge：`POST /session/start`
4. CLI 调 Bridge：`POST /play`
5. Bridge 开始把 Unity console log 写入这个 session 的 `unity-console.jsonl`
6. `unityctl stop`
7. CLI 调 Bridge：`POST /stop`
8. CLI 调 Bridge：`POST /session/end`
9. CLI 写/更新 `summary.json`

我不建议完全由 Bridge 自动根据 PlayMode 创建 session。原因是：

- 用户手动点 Play 也会触发 session，容易产生很多无意义日志
- agent 不知道这次 session 叫什么，也不好关联任务
- 后续截图、验证报告、运行参数、目标 scene 都更适合由外部统一管理
- Bridge 不应该承担太多“产品语义”，它只应该是 Editor 内的薄控制层

但也不建议完全相信 CLI，因为用户可能手动 Stop，或者 Unity 崩了。所以 Bridge 要做兜底：

- 如果 PlayMode 退出，Bridge 自动 flush 当前 session log
- 如果 Editor 关闭，已写入的 jsonl 仍然存在
- `/status` 返回当前 session id/path
- `/session/end` 可以重复调用，保证幂等

所以最终是这个模式：

```text
CLI / Agent：定义一次运行的意图和 session
Bridge：执行 Editor 内控制，并持续落盘日志
文件系统：作为最终事实来源
```

我觉得这是最稳的，因为它同时满足：

- agent 可控
- 日志可审计
- 低侵入
- 后续容易扩展截图、报告、断言
- 不被 Unity Editor 当前内存状态绑死

一句话：

> session 的“开始/结束意图”由 `unityctl` 管，session 的“运行中事实记录”由 Bridge 持续落盘。

> 采纳你的建议

好，那第二块“运行观测”的核心方向我们先定下来：

**Session-based 落盘日志观测**

主设计：

- `unityctl` 显式创建和结束 session
- Bridge 接收当前 session 信息
- Bridge 捕获 Unity Console log
- Bridge 将日志持续 append 到 session 目录里的 `unity-console.jsonl`
- 文件系统是最终事实来源
- Bridge 的 `/logs` 或 CLI 的 `unityctl logs` 只是便捷查询

第一版最小能力可以是：

```bash
unityctl play --session login-flow
unityctl logs --session latest
unityctl errors --session latest
unityctl stop
```

对应 session 目录：

```text
.unity-agent/
  sessions/
    2026-06-30_183012_login-flow/
      session.json
      unity-console.jsonl
      summary.json
```

`unity-console.jsonl` 每行一条：

```json
{"time":"2026-06-30T18:30:12.123Z","type":"Log","message":"LoginView opened","stackTrace":""}
{"time":"2026-06-30T18:30:14.001Z","type":"Exception","message":"NullReferenceException...","stackTrace":"..."}
```

`summary.json`：

```json
{
  "ok": false,
  "logCount": 128,
  "warningCount": 3,
  "errorCount": 1,
  "exceptionCount": 1,
  "lastError": "NullReferenceException..."
}
```

这里的价值很明确：

> 通用 coding agent 修改完代码后，可以运行 Unity、拿到本次 session 的完整日志，再基于日志判断是否需要继续修复。

下一步如果继续展开，我建议只讨论这个问题：

**session 目录应该由 CLI 创建，还是由 Bridge 创建？**

我的倾向是：**CLI 创建 session 目录，Bridge 只写入指定路径**。这样外部 agent 更容易知道文件在哪里。

> CLI 创建 session 目录，Bridge 只写入指定路径。

同意，这个边界非常干净。

**定案：CLI 创建 session 目录，Bridge 只写入指定路径。**

这样职责分工是：

**CLI 负责：**

- 生成 `session_id`
- 创建 session 目录
- 写入初始 `session.json`
- 调用 Bridge 告诉它当前日志写到哪里
- 在 `stop` 后生成或更新 `summary.json`
- 对外返回 session 路径，方便通用 agent 读取

**Bridge 负责：**

- 接收 `sessionPath`
- 校验路径是否允许写入
- 注册/使用 `Application.logMessageReceived`
- 把 Unity Console log append 到：
  ```text
  <sessionPath>/unity-console.jsonl
  ```
- 在 PlayMode 退出或 session end 时 flush/close
- `/status` 返回当前 session 信息

第一版接口可以加：

```http
POST /session/start
POST /session/end
GET  /session/status
```

`POST /session/start` payload：

```json
{
  "sessionId": "2026-06-30_183012_login-flow",
  "sessionPath": "/Users/elex-mb0203/project/.unity-agent/sessions/2026-06-30_183012_login-flow"
}
```

Bridge 返回：

```json
{
  "ok": true,
  "message": "session started",
  "sessionId": "2026-06-30_183012_login-flow",
  "logPath": "/Users/elex-mb0203/project/.unity-agent/sessions/2026-06-30_183012_login-flow/unity-console.jsonl"
}
```

CLI 使用方式：

```bash
unityctl play --session login-flow
```

执行顺序：

```text
create session dir
write session.json
POST /session/start
POST /play
print JSON with sessionId/sessionPath
```

`unityctl stop`：

```text
POST /stop
POST /session/end
read unity-console.jsonl
write summary.json
print JSON with summary
```

我建议这里再加一个安全限制：

Bridge 不能随便写任意路径。
第一版可以只允许写到当前 Unity project 下的：

```text
<ProjectRoot>/.unity-agent/sessions/
```

否则一个 HTTP localhost 接口如果能写任意文件路径，会有安全风险。

下一步我们可以做两件事之一：

1. 继续细化“运行观测”需求和技术难点
2. 直接把这部分整理成第二份中文开发计划文档

> 1

好，继续细化“运行观测”，但我们还是慢慢来。

现在已经定下来的核心是：

> CLI 创建 session 目录，Bridge 只写入指定路径，日志落盘是最终事实来源。

接下来运行观测可以拆成 4 个小需求：

1. **Session 元数据**
   记录这次运行是谁、什么时候、跑哪个 scene、为什么跑、对应哪个任务。

2. **Unity Console 结构化日志**
   捕获 `Log / Warning / Error / Exception / Assert`，写入 `unity-console.jsonl`。

3. **日志摘要**
   统计 error、warning、exception 数量，提取最后几条关键错误，生成 `summary.json`。

4. **读取与查询**
   CLI 可以读取 latest session、过滤 error、输出最近 N 条日志。

我建议我们先展开 **Session 元数据**，因为它决定后面所有文件怎么组织。

第一版 `session.json` 我建议长这样：

```json
{
  "sessionId": "2026-06-30_183012_login-flow",
  "name": "login-flow",
  "projectPath": "/path/to/unity/project",
  "scenePath": "Assets/Scenes/Login.unity",
  "createdAt": "2026-06-30T18:30:12.123Z",
  "startedAt": null,
  "endedAt": null,
  "status": "created",
  "trigger": "agent",
  "task": "verify login flow after code changes"
}
```

字段保持少，但要能服务 agent 复盘：

- `sessionId`：唯一 ID
- `name`：人类可读名
- `projectPath`：归属项目
- `scenePath`：本次目标场景，可为空
- `createdAt/startedAt/endedAt`：生命周期
- `status`：`created/running/stopped/failed`
- `trigger`：`agent/manual/ci`
- `task`：自然语言任务说明

我的建议：**第一版不要把 git commit、diff、branch 加进来**。
它们有价值，但属于后面的验证报告层。现在先把运行观测闭环做稳。

这个设计你觉得够用吗？还是你希望 `session.json` 第一版就带上 `branch/commit/diff` 这些代码上下文？

> 带与不带有什么优缺点？

简单说：

**不带 `branch/commit/diff`**

优点：

- 第一版更简单，session 只关心“这次 Unity 怎么跑的”
- 和 git 解耦，非 git 项目也能用
- CLI/Bridge 边界更干净
- 不容易因为 dirty worktree、未提交文件、子模块等情况变复杂

缺点：

- 事后复盘时，不一定知道这次日志对应哪份代码
- 多个 agent 连续修改时，session 和代码改动关联弱
- 做“自动验证某次改动是否通过”时证据链不完整

**带 `branch/commit/diff`**

优点：

- 可追溯性强：知道这次运行验证了哪份代码
- 对通用 coding agent 很有价值：它能把“修改 → 运行 → 日志 → 修复”串起来
- 后续生成验证报告、PR 注释、失败归因会更方便

缺点：

- 第一版实现复杂度上升
- dirty worktree 怎么表示会变麻烦
- diff 可能很大，不适合直接塞进 `session.json`
- Unity 项目未必总在 git repo 里
- 容易让“运行观测”混入“代码验证报告”职责

我的建议是折中：

**第一版带轻量 git metadata，但不带完整 diff。**

比如：

```json
{
  "git": {
    "available": true,
    "branch": "feature/login",
    "commit": "abc1234",
    "isDirty": true
  }
}
```

不放完整 diff。

如果需要 diff，后续可以单独落盘：

```text
git.diff
```

这样好处是：

- session 有基本追溯能力
- 不污染 `session.json`
- 实现成本不高
- 后续验证报告可以继续扩展

所以我推荐第一版：

**带 `branch/commit/isDirty`，不带 `diff`。**

> 先不带branch/commit/diff 这些代码上下文

好，第一版 `session.json` 就先不带代码上下文。

这样边界更纯：

> session 只描述一次 Unity 运行，不描述这次运行对应的代码变更。

第一版字段可以定成：

```json
{
  "sessionId": "2026-06-30_183012_login-flow",
  "name": "login-flow",
  "projectPath": "/path/to/unity/project",
  "scenePath": "Assets/Scenes/Login.unity",
  "createdAt": "2026-06-30T18:30:12.123Z",
  "startedAt": null,
  "endedAt": null,
  "status": "created",
  "trigger": "agent",
  "task": "verify login flow after code changes"
}
```

状态流转：

```text
created -> running -> stopped
created -> failed
running -> failed
```

先不做：

- `branch`
- `commit`
- `diff`
- `author`
- `PR`
- `issueId`

这会让第二块的 MVP 很清楚：

1. `unityctl play --session login-flow --scene Assets/Scenes/Login.unity --task "..."`
2. CLI 创建 session 目录和 `session.json`
3. Bridge 写 `unity-console.jsonl`
4. `unityctl stop`
5. CLI 更新 `session.json` 和生成 `summary.json`

下一个小点是 **日志格式**。

我建议 `unity-console.jsonl` 每行这样：

```json
{
  "time": "2026-06-30T18:30:14.001Z",
  "sequence": 12,
  "type": "Exception",
  "message": "NullReferenceException...",
  "stackTrace": "...",
  "isPlayMode": true,
  "scenePath": "Assets/Scenes/Login.unity"
}
```

其中 `sequence` 很有用：同一毫秒内多条日志也能排序。

这个日志字段你觉得是否够用？还是第一版应该再加 `frameCount`？

> frameCount 是什么意思？如果要加需要付出什么？

`frameCount` 指的是 Unity 运行到第几帧。

在 PlayMode 里可以理解成：

```text
进入 PlayMode 后：
第 1 帧
第 2 帧
第 3 帧
...
```

日志里加上它之后，一条 log 会变成：

```json
{
  "time": "2026-06-30T18:30:14.001Z",
  "sequence": 12,
  "frameCount": 356,
  "type": "Exception",
  "message": "NullReferenceException...",
  "stackTrace": "..."
}
```

**它的价值**

- 能知道错误发生在运行后的第几帧
- 对“某个流程跑了几帧后才报错”有帮助
- 后续如果加截图、状态快照，可以按 frame 对齐
- 对卡死、延迟触发、动画/异步流程问题有价值

**代价**

- 技术上不大，Unity 里可以读 `Time.frameCount`
- 但 `Application.logMessageReceived` 有时也会在非 PlayMode 或 Editor 状态触发，此时 `Time.frameCount` 的意义弱
- 如果 domain reload / 重新进 PlayMode，frame 可能重置
- 对纯业务日志、编译日志、Editor log，它不一定有用

实现成本大概是：**低**。

真正的成本不是代码，而是语义解释：
agent 看到 `frameCount: 0` 或非 PlayMode 日志时，不能误以为这是游戏第 0 帧的问题。

我的建议：

**第一版可以加，但字段命名更明确一点：**

```json
{
  "playModeFrame": 356
}
```

如果不在 PlayMode，就写：

```json
{
  "playModeFrame": null
}
```

这样比 `frameCount` 更不容易误解。

所以我推荐日志字段为：

```json
{
  "time": "...",
  "sequence": 12,
  "type": "Exception",
  "message": "...",
  "stackTrace": "...",
  "isPlayMode": true,
  "playModeFrame": 356,
  "scenePath": "Assets/Scenes/Login.unity"
}
```

> 可以加上吧

好，日志格式定下来，第一版加 `playModeFrame`。

`unity-console.jsonl` 每行一条：

```json
{
  "time": "2026-06-30T18:30:14.001Z",
  "sequence": 12,
  "type": "Exception",
  "message": "NullReferenceException...",
  "stackTrace": "...",
  "isPlayMode": true,
  "playModeFrame": 356,
  "scenePath": "Assets/Scenes/Login.unity"
}
```

规则：

- `sequence`：本 session 内递增，从 `1` 开始
- `type`：Unity log type，取值类似 `Log / Warning / Error / Exception / Assert`
- `isPlayMode`：写 log 时 Editor 是否在 PlayMode
- `playModeFrame`：
  - PlayMode 中：写 `Time.frameCount`
  - 非 PlayMode：写 `null`
- `scenePath`：写 log 时当前 active scene path
- `stackTrace`：没有就写空字符串

这样后续 agent 能做几件事：

- 找出本次运行是否有 error / exception
- 知道错误大概发生在流程哪个阶段
- 按 sequence 复原日志顺序
- 未来和截图、状态快照按 frame 对齐

下一个小点是 **summary.json**。

我建议第一版 summary 不做复杂分析，只做统计和最后错误：

```json
{
  "ok": false,
  "logCount": 128,
  "warningCount": 3,
  "errorCount": 1,
  "exceptionCount": 1,
  "assertCount": 0,
  "lastProblem": {
    "type": "Exception",
    "message": "NullReferenceException...",
    "sequence": 87,
    "playModeFrame": 356
  }
}
```

这里 `ok` 的规则也要定：

> 只要 `Error / Exception / Assert` 任意数量大于 0，`ok = false`；否则 `ok = true`。

你觉得 `Warning` 要不要影响 `ok`？我的倾向是第一版 **Warning 不影响 ok**。

> 不影响 ok

好，定下来：

**Warning 不影响 `ok`。**

第一版 `summary.json` 规则：

```text
ok = errorCount == 0 && exceptionCount == 0 && assertCount == 0
```

也就是：

- `Log`：不影响
- `Warning`：不影响
- `Error`：影响，`ok = false`
- `Exception`：影响，`ok = false`
- `Assert`：影响，`ok = false`

`summary.json`：

```json
{
  "ok": false,
  "logCount": 128,
  "warningCount": 3,
  "errorCount": 1,
  "exceptionCount": 1,
  "assertCount": 0,
  "lastProblem": {
    "type": "Exception",
    "message": "NullReferenceException...",
    "sequence": 87,
    "playModeFrame": 356,
    "scenePath": "Assets/Scenes/Login.unity"
  }
}
```

我建议再加两个字段：

```json
{
  "startedAt": "2026-06-30T18:30:12.123Z",
  "endedAt": "2026-06-30T18:31:02.456Z",
  "durationMs": 50333
}
```

这样 agent 能知道：

- 这次运行持续了多久
- 是不是一启动就炸
- 是不是跑了很久后才出问题

这个实现成本很低，因为 `session.json` 里已经有时间。

所以 summary 第一版就可以包含：

- `ok`
- `logCount`
- `warningCount`
- `errorCount`
- `exceptionCount`
- `assertCount`
- `lastProblem`
- `startedAt`
- `endedAt`
- `durationMs`

下一个点是：
`summary.json` 应该由 **CLI 读取 jsonl 后生成**，还是由 **Bridge 在 session end 时生成**？

我的建议还是：**CLI 生成 summary**。Bridge 只负责忠实写日志。

> 按照你的建议来。但是我有一个建议，就是summary 中的ok 不能说出现了Error就不ok,有些Error 其实并不是逻辑出现了错误，而是有些测试打印或者这些报错不影响游戏的运行，有的时候起的是警告作用？这就比较难区分了

你这个提醒很重要。`Error/Exception/Assert => ok=false` 只能当 **默认规则**，不能当最终真理。

更准确的说法应该是：

**summary 里不要只有 `ok`，而要区分“是否有问题信号”和“是否判定失败”。**

我建议改成这样：

```json
{
  "status": "problem_detected",
  "hasProblems": true,
  "hasBlockingProblems": false,
  "logCount": 128,
  "warningCount": 3,
  "errorCount": 2,
  "exceptionCount": 0,
  "assertCount": 0,
  "ignoredProblemCount": 1,
  "blockingProblemCount": 1,
  "lastProblem": {
    "type": "Error",
    "message": "Asset load failed...",
    "severity": "blocking",
    "sequence": 87
  }
}
```

第一版可以这样定义：

- `hasProblems`：只要有 `Error / Exception / Assert` 就是 `true`
- `hasBlockingProblems`：经过规则判断后，是否存在真正阻塞问题
- `status`：
  - `passed`：没有 problem
  - `problem_detected`：有 problem，但不确定是否阻塞
  - `failed`：有明确 blocking problem
- `ok` 可以先不放，避免误导

如果你想保留 `ok` 给 agent 快速判断，也可以定义为：

```text
ok = status == "passed"
```

但我更倾向第一版先不用 `ok`，用 `status` 更诚实。

然后关键是 **规则系统**。

第一版可以支持一个简单配置文件：

```text
.unity-agent/log-rules.json
```

例如：

```json
{
  "ignore": [
    {
      "type": "Error",
      "messageContains": "This error is expected in test mode"
    }
  ],
  "blocking": [
    {
      "type": "Exception"
    },
    {
      "type": "Assert"
    },
    {
      "type": "Error",
      "messageContains": "NullReferenceException"
    }
  ]
}
```

这样：

- 没规则命中的 `Error` 不直接判 `failed`
- `Exception / Assert` 默认 blocking
- 被 ignore 的问题不影响 blocking
- 未归类的 Error 进入 `problem_detected`

我建议第一版规则：

```text
Exception / Assert => blocking
Error => problem_detected
Warning => 不影响
ignore rules => 从 problem 中排除
```

这比简单 `ok=false` 更符合真实 Unity 项目。你这个修正是对的。

> 好的

那我们把 summary 判定规则定成这个版本：

**第一版不使用简单 `ok` 作为主判断，而使用 `status`。**

`summary.json`：

```json
{
  "status": "problem_detected",
  "hasProblems": true,
  "hasBlockingProblems": false,
  "logCount": 128,
  "warningCount": 3,
  "errorCount": 2,
  "exceptionCount": 0,
  "assertCount": 0,
  "ignoredProblemCount": 1,
  "blockingProblemCount": 0,
  "lastProblem": {
    "type": "Error",
    "message": "Asset load failed...",
    "severity": "problem",
    "sequence": 87,
    "playModeFrame": 356,
    "scenePath": "Assets/Scenes/Login.unity"
  },
  "startedAt": "2026-06-30T18:30:12.123Z",
  "endedAt": "2026-06-30T18:31:02.456Z",
  "durationMs": 50333
}
```

`status` 取值：

```text
passed
problem_detected
failed
```

第一版默认规则：

```text
Log      -> ignored
Warning  -> counted, but not problem
Error    -> problem
Exception -> blocking
Assert    -> blocking
```

状态计算：

```text
blockingProblemCount > 0 -> failed
blockingProblemCount == 0 && problemCount > 0 -> problem_detected
problemCount == 0 -> passed
```

再加一个可选配置：

```text
.unity-agent/log-rules.json
```

第一版只支持 `ignore`，先不支持复杂 blocking 自定义，避免做大：

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

被 ignore 命中的日志：

- 仍然保留在 `unity-console.jsonl`
- 不计入 `problemCount`
- 计入 `ignoredProblemCount`

这样不会掩盖事实，也不会让 summary 过度悲观。

到这里，运行观测 MVP 基本成型了：

1. `session.json`
2. `unity-console.jsonl`
3. `summary.json`
4. `.unity-agent/log-rules.json`
5. `unityctl logs/errors/summary`

下一步我们可以开始整理第二部分中文开发计划文档，或者继续讨论最后一个小点：**CLI 查询命令应该怎么设计**。

> 整理开发文档

<details><summary>7 previous messages</summary>

> 我会用 `superpowers:writing-plans` 的格式整理第二部分开发文档：中文说明，代码/命令/API 保持英文。范围只覆盖“运行观测 MVP”：session 目录、落盘日志、summary、ignore rules、CLI 查询。
>
> 我把第二部分定位为第一部分之后的增量计划，所以文档会明确写“依赖 Unity Editor Control 已完成”。这样它不会把运行控制和运行观测混成一个大工程。
>
> <details><summary>Created a file</summary>
>
> - Wrote `./docs/superpowers/plans/2026-06-30-unity-runtime-observability.md` (+1503 -0)
>
> </details>
>
> 第二份开发文档已经写入。我在做自检，主要看三件事：有没有占位符残留、Markdown fence 有没有明显断裂、git 状态是否只出现预期文档。
>
> 扫描命中了 Self-Review 里描述“没有 TBD/TODO”的那句话本身，不是实际占位符；我会改成中文表述，避免后续自动扫描误报。
>
> <details><summary>Edited a file</summary>
>
> - Wrote `./docs/superpowers/plans/2026-06-30-unity-runtime-observability.md` (+1 -1)
>
> </details>
>
> 我再跑一次自检；如果没有新问题，就给你文档路径和下一步选项。
</details>

已整理第二部分中文开发文档：

[2026-06-30-unity-runtime-observability.md](./docs/superpowers/plans/2026-06-30-unity-runtime-observability.md)

它覆盖我们刚定下来的运行观测 MVP：`session.json`、`unity-console.jsonl`、`summary.json`、CLI 创建 session、Bridge 写日志、`ignore` rules、`unityctl logs/errors/summary`。我也做了占位符扫描，没有发现残留；当前只是文档新增，尚未提交。

现在有两份计划文档：

- [Unity Editor Control](./docs/superpowers/plans/2026-06-30-unity-editor-control.md)
- [Unity Runtime Observability](./docs/superpowers/plans/2026-06-30-unity-runtime-observability.md)

> 接下来呢？

接下来我建议有两条路，取决于你现在想“继续想清楚”还是“开始落地”。

我更推荐这个顺序：

1. **先 review 这两份文档**
   - `Unity Editor Control`
   - `Unity Runtime Observability`

2. **确认第一阶段 MVP 边界**
   也就是：
   - 能启动/控制 Unity Editor PlayMode
   - 能创建 session
   - 能落盘本次运行日志
   - 能生成 summary
   - 能让通用 agent 读取结果

3. **然后开始实现第一份文档**
   先做 `Unity Editor Control`，因为第二份运行观测依赖它。

如果我们还不急着写代码，那下一块应该讨论 **游戏操作**：

> agent 如何操作游戏，而不是只启动和观察游戏。

这一块会比日志观测难很多，需要讨论几种路线：

- 系统级点击：低侵入，但脆
- Unity UI 结构化点击：少量侵入，稳定很多
- 游戏内 command bridge：更稳定，但侵入更高
- 录制/回放人工操作：很适合 MVP

我的建议是：**先不要继续扩太远，先把前两份文档 review 一遍，确认没有方向性问题。**
如果你认可，我们下一步可以做一轮“文档评审”：我按产品价值、实现风险、MVP 是否过大三个维度检查这两份计划。

> 先 review 这两份文档

<details><summary>4 previous messages</summary>

> 我来做一轮文档 review，不改实现代码。会按“方向性问题、执行风险、MVP 是否过大、前后依赖是否清楚”来检查，最后给出建议修改点。
>
> 我已经看到几个需要修正的风险点，主要集中在两个地方：第一份的 `HttpListener` 队列响应可能重复写 response；第二份的 session DTO 插入位置、`playModeFrame` 语义和 CLI 测试 monkeypatch 都有可执行性隐患。我继续把行号核准一下。
>
> 我核准了主要问题的行号。结论不是“方向错了”，而是计划里有几处会让执行 agent 照抄后踩坑，尤其是 C# 可编译性和 session 语义一致性。
>
> 还有一个更基础的 C# 编译风险：第二份文档说把 session DTO “追加到文件末尾”，但第一份的 `BridgeResponse.cs` 文件末尾已经在 namespace 外了，照做会把类型放到 namespace 外，后续引用大概率编译不过。
</details>

**Review 结果**

主要方向是对的：两份文档的产品边界清楚，先做 `Editor Control`，再做 `Runtime Observability`，这个顺序合理。MVP 也没有明显过大。需要修的是几个“照文档执行会踩坑”的实现细节。

**发现的问题**

- **P1: `BridgeServer` 可能重复写 HTTP response。**
  [2026-06-30-unity-editor-control.md](./docs/superpowers/plans/2026-06-30-unity-editor-control.md:1195)
  `HandleContext()` 超时后会直接写 `504`，但主线程稍后仍可能在 `ProcessPendingRequests()` 写 `200/500`。这会导致 response stream 已关闭后的异常，也会让请求状态不可靠。建议改成：监听线程只等待结果并负责写 response，主线程只计算 `statusCode + payload` 后 signal；或给 `QueuedRequest` 加 `TimedOut` 标记，超时后主线程跳过写入。

- **P1: Bridge 没有 domain reload / Editor quit 清理逻辑。**
  [2026-06-30-unity-editor-control.md](./docs/superpowers/plans/2026-06-30-unity-editor-control.md:1139)
  Bridge 在 static constructor 自动 `Start()`，但没有 `Stop()`，也没有注册 `AssemblyReloadEvents.beforeAssemblyReload` / `EditorApplication.quitting`。Unity 编译、domain reload、退出 Editor 时可能留下 listener/thread 状态，下一次启动容易端口占用或状态不干净。建议第一份文档增加 `Stop()` 任务。

- **P1: 第二份文档的 DTO 插入位置会导致 C# 编译风险。**
  [2026-06-30-unity-runtime-observability.md](./docs/superpowers/plans/2026-06-30-unity-runtime-observability.md:1041)
  文档写“在 `BridgeResponse.cs` 末尾追加”，但第一份里的 namespace 在文件末尾已经关闭了。照做会把 `SessionStartRequest` / `SessionStatusResponse` 放到 namespace 外，后续 `SessionController` 引用可能编译失败。建议改成“追加到 `namespace Elex.UnityAgentBridge.Editor { ... }` 内、`OpenSceneRequest` 后”。

- **P1: `Application.dataPath.Replace("/Assets", string.Empty)` 不稳。**
  [2026-06-30-unity-runtime-observability.md](./docs/superpowers/plans/2026-06-30-unity-runtime-observability.md:1160)
  这个字符串替换对 Windows 反斜杠、路径中包含多个 `Assets`、大小写等情况都不稳。建议用 `Directory.GetParent(Application.dataPath).FullName` 获取 project root。

- **P2: session start response 没有返回 `sessionId/logPath`，和前面接口设想不一致。**
  [2026-06-30-unity-runtime-observability.md](./docs/superpowers/plans/2026-06-30-unity-runtime-observability.md:1153)
  `StartSession()` 现在只返回 `BridgeResponse.Success("session started")`。这能跑，但对 agent 不够友好。建议加 `SessionStartResponse`，返回 `sessionId/sessionPath/logPath`。

- **P2: `playModeFrame` 数据契约有轻微不一致。**
  [2026-06-30-unity-runtime-observability.md](./docs/superpowers/plans/2026-06-30-unity-runtime-observability.md:1129)
  前面讨论的是非 PlayMode 用 `null`，文档实现改成 `-1`，并说下游解释成 `null`。这可以接受，但应该在“数据约定”里明确写 `-1`，否则 agent 解析时会误解。

**结论**

两份文档可以作为 MVP 基础，但我建议先修上面 4 个 P1，再开始实现。尤其是 `BridgeServer` 生命周期和 response 写入模型，这两个会直接影响稳定性。

我只做了文档 review，没有改文件，也没有跑实现测试。

> 修复P1P2

<details><summary>8 previous messages</summary>

> 我会把这当成一次“收到 review 后修正文档”的工作来处理，先加载对应的 review 处理技能，然后直接改两份计划文档里的 P1/P2 问题。
>
> 我确认这些 P1/P2 都是文档层面的可执行性问题，不需要改产品方向。我会直接修文档里的代码片段和数据约定：让执行者照抄时更稳。
>
> <details><summary>Edited a file</summary>
>
> - Wrote `./docs/superpowers/plans/2026-06-30-unity-editor-control.md` (+35 -3)
>
> </details>
>
> 第一份里的 Bridge 响应模型已经改成“监听线程写 HTTP，主线程只产出结果”，并加了 reload/quit 清理。接下来修第二份里的 session DTO、project root、`playModeFrame` 契约和 start response。
>
> <details><summary>Edited a file</summary>
>
> - Wrote `./docs/superpowers/plans/2026-06-30-unity-runtime-observability.md` (+31 -3)
>
> </details>
>
> 第二份的核心修正已经进去了：DTO 明确放在 namespace 内、`StartSession` 返回结构化 session 信息、project root 改成 `DirectoryInfo(Application.dataPath).Parent`、`playModeFrame=-1` 写入数据约定。现在我做一次扫描，确认没有旧文本残留。
>
> 检查里那条 `rg` 又被 shell 反引号干扰了一下，但文件内容本身正常。我会用单引号重跑，并顺手检查有没有旧的危险写法残留。
>
> 当前没有旧的危险写法残留：`Application.dataPath.Replace` 和 DTO “末尾追加”都不在相关位置了。因为这两个计划文档还是未跟踪文件，`git diff` 不会显示它们，我会用文件扫描做最终确认。
</details>

已修复两份文档里的 P1/P2 问题：

- [Unity Editor Control](./docs/superpowers/plans/2026-06-30-unity-editor-control.md)
  - 修正 `BridgeServer`：HTTP response 现在只由监听线程写，主线程只产出结果，避免超时后重复写 response。
  - 增加 `Stop()`，并接入 `AssemblyReloadEvents.beforeAssemblyReload` / `EditorApplication.quitting`，降低 domain reload 和退出时端口残留风险。

- [Unity Runtime Observability](./docs/superpowers/plans/2026-06-30-unity-runtime-observability.md)
  - 明确 session DTO 必须插入 namespace 内，而不是文件末尾随手追加。
  - 增加 `SessionStartResponse`，`session/start` 成功后返回 `sessionId/sessionPath/logPath`。
  - `projectRoot` 改为通过 `DirectoryInfo(Application.dataPath).Parent` 获取，不再用字符串 replace。
  - 数据约定里明确：非 PlayMode 时 `playModeFrame = -1`。

我做了占位符扫描和基础文档结构检查，没有发现 `TBD/TODO/implement later` 残留。当前仍只是文档变更，未提交。

> 有没有一个plan 来汇总这两个plan,这个plan的作用就是引用，算是一个入口plan 或者说汇总plan

<details><summary>3 previous messages</summary>

> 我会把它做成一个“入口/总控 plan”，作用不是重复两份细节，而是说明执行顺序、依赖关系、阶段验收和跳转链接。用中文描述，保留文件名、命令和技术名为英文。
>
> 我正在使用 `superpowers:writing-plans` 创建入口计划。这个文件会保持短一些，重点是“先执行哪个、完成标准是什么、哪些文档是权威细节”。
>
> <details><summary>Created a file</summary>
>
> - Wrote `./docs/superpowers/plans/2026-07-01-unity-agent-bridge-entry.md` (+339 -0)
>
> </details>
</details>

> 继续

<details><summary>2 previous messages</summary>

> 入口计划已经写入。我继续做收尾检查：占位符扫描、文件头预览、git 状态确认。
>
> <details><summary>Explored a file, a search, ran a command</summary>
>
> <details><summary>Explored a file, a search</summary>
>
> - Read `./docs/superpowers/plans/2026-07-01-unity-agent-bridge-entry.md`
> - Searched for `TBD|TODO|implement later|add appropriate|Similar to Task|Write tests for the above` in `2026-07-01-unity-agent-bridge-entry.md`
>
> </details>
>
> - Ran `git status --short`
>
> </details>
</details>

已创建入口/汇总 plan：

[2026-07-01-unity-agent-bridge-entry.md](./docs/superpowers/plans/2026-07-01-unity-agent-bridge-entry.md)

它的作用是作为总入口，引用并串联：

- [Unity Editor Control](./docs/superpowers/plans/2026-06-30-unity-editor-control.md)
- [Unity Runtime Observability](./docs/superpowers/plans/2026-06-30-unity-runtime-observability.md)

我也做了占位符扫描，没有发现残留。当前 `docs/` 目录仍是未提交状态。

> 你需要把我们聊天的所有关键信息总结到一个文档中，因为我需要在新的项目中使用，这个文档能够帮助新的agent 了解我们想要做什么，并且知道我们沟通过什么，尽量详细

<details><summary>6 previous messages</summary>

> 我会把这做成一份“项目上下文交接文档”，不是简单聊天摘要：它会说明目标、用户背景、需求演进、已做决策、MVP 范围、三个 plan 的位置，以及后续 agent 应该如何继续。先读取现有计划文档，避免漏掉刚刚修过的细节。
>
> <details><summary>Explored 3 files, ran a command</summary>
>
> <details><summary>Explored 3 files</summary>
>
> - Read `./docs/superpowers/plans/2026-07-01-unity-agent-bridge-entry.md`
> - Read `./docs/superpowers/plans/2026-06-30-unity-editor-control.md`
> - Read `./docs/superpowers/plans/2026-06-30-unity-runtime-observability.md`
>
> </details>
>
> - Ran `git status --short`
>
> </details>
>
> 我会新增一份独立的上下文文档，放在 `docs/` 下，名字清楚一点，方便复制到新项目或直接交给新 agent。它会引用现有三个 plan，但不会只依赖它们。
>
> <details><summary>Created 2 files</summary>
>
> - Wrote `./docs/unity-agent-bridge-project-context.md` (+107 -0)
> - Wrote `./docs/unity-agent-bridge-project-context.md` (+888 -0)
>
> </details>
>
> 文档已经生成。我现在做一次检查：确认文件可读、没有占位符残留，并看一下 git 状态。
>
> <details><summary>Explored a file, a search, ran a command</summary>
>
> <details><summary>Explored a file, a search</summary>
>
> - Read `./docs/unity-agent-bridge-project-context.md`
> - Searched for `TBD|TODO|implement later|待补充|占位` in `unity-agent-bridge-project-context.md`
>
> </details>
>
> - Ran `wc -l docs/unity-agent-bridge-project-context.md && git status --short`
>
> </details>
</details>

已生成详细交接文档：

[unity-agent-bridge-project-context.md](./docs/unity-agent-bridge-project-context.md)

它总结了我们这轮聊天里的关键内容，包括：用户背景、Agent Service 定位、市场/需求调研、Unity 运行控制与观测的需求演进、已定技术决策、MVP 范围、session/log/summary 设计、暂不做的方向、后续路线，以及新 agent 应该如何继续。

我也做了占位符扫描，没有发现 `TBD/TODO/待补充` 之类残留。当前 `docs/` 目录仍是未提交状态。
