# Unity Agent Bridge 项目上下文交接文档

本文档用于把当前对话中的关键信息、需求演进、技术决策和后续计划沉淀下来，方便在新项目中交给新的 agent 使用。

新 agent 阅读本文后，应当能够理解：

- 我们想做什么
- 为什么要做
- 已经讨论过哪些方向
- 哪些方向暂时不做
- MVP 的边界是什么
- 当前有哪些实现计划文档
- 下一步应该如何继续

本文档是上下文交接文档，不是最终架构说明书，也不是完整实现计划。真正执行开发时，应进入本文后面列出的 plan 文档。

---

## 1. 用户背景与工作场景

用户是一名 Unity 游戏开发者，同时也是“一人超级公司”的创始人。

这意味着当前项目有两个目标维度：

1. **提高 Unity 正职工作的效率**
   - 减少手动运行、点击、验证、查日志的时间。
   - 让通用 coding agent 的产出能够更快被验证。
   - 把用户从重复性 Unity 验证工作中释放出来。

2. **探索副业/一人公司产品方向**
   - 如果某个自用 agent service 真的有效，可以进一步产品化。
   - 产品化对象可能是 Unity 开发者、独立游戏团队、Asset Store 工具作者，或一人公司开发者。
   - 但当前阶段不急于商业化，先从真实自用场景中找高价值需求。

用户目前已经在 Cursor / Codex 等通用 coding agent 中配置了一部分能力，包括：

- 工程大体知识库
- 获取任务需求的 skill
- 提交代码流程 skill
- 任务展开流程 skill
- 查询游戏配表的 skill

已有能力主要帮助通用 agent “理解项目、展开任务、写代码、查配置”。当前瓶颈不是让 agent 写代码，而是：

- **验证需要人手动运行 Unity、点击、观察、看日志**
- **UI Prefab 拼接仍然高度依赖人工**

经过讨论，当前优先选择从“Unity 游戏运行与验证服务”切入，而不是直接做 UI Prefab 自动拼接。

---

## 2. 最初讨论的 Agent Service 定位

一开始讨论的是“垂直领域 agent 开发”的技术选型。

用户明确表示：想做的不是另一个通用 Codex，而是一个特定领域的 agent service。

这个 service 应满足：

- 是一种垂直领域服务，而不是泛用聊天机器人。
- 支持人机交互，用户可以通过自然语言或 UI 与它交互。
- 支持 agent loop。
- 支持 MCP / skills / tools 等扩展机制。
- 支持定时任务、后台任务、持续监控。
- 能对通用 agent 暴露接口，例如 CLI、HTTP API、MCP tools。
- 能让通用 coding agent 调用它做验证、查询、运行、报告生成。

最终抽象为：

```text
垂直 Agent Service
  = 特定领域服务
  + agent 能力
  + 对人交互
  + 对 agent 暴露接口
  + 可验证、可审计、可落盘的执行结果
```

对于 Unity 场景，这个 service 不应该只是“在 Unity 里聊天”，而应该围绕具体高频痛点提供服务能力。

---

## 3. 市场与需求调研阶段结论

我们简单讨论过 Unity 游戏开发者可能需要哪些 agent service。

考虑过的方向包括：

1. **Build / CI / 发布诊断 Agent**
   - 分析构建失败、Addressables、Cloud Build、iOS/Android 打包、shader variant、包体大小、依赖冲突。
   - 工程化程度高，适合自动读日志、改配置、跑验证。

2. **性能优化 / Profiling Agent**
   - 分析 Profiler、内存、GC、Draw Call、资源加载、帧率波动。
   - 价值高，但需要更多 Unity runtime 数据和 profiling 数据。

3. **项目健康检查 Agent**
   - 检查 asmdef、Packages、资源目录、Prefab 引用、Addressables 配置、Editor 脚本风险、升级风险。
   - 适合做成 Unity 项目体检服务。

4. **资源与 Asset Store 决策 Agent**
   - 辅助插件/资产采购前审计。
   - 查兼容版本、维护状态、依赖风险、替代方案。

5. **玩法原型验证 Agent**
   - 把设计想法转为最小 Unity prototype，并自动跑 smoke test / play mode test / editor validation。
   - 价值高，但和 Unity 官方 AI 助手、通用 coding agent 更接近。

6. **垂直发行/运营 Agent**
   - Steam 页面检查、移动端商店素材规范、埋点完整性、版本发布 checklist、崩溃日志归因。
   - 更偏一人公司商业闭环。

阶段性判断：

- Unity 官方和生态里已经有很多通用 AI / MCP / Assistant 方向。
- 泛用“Unity AI 助手”会正面撞官方和已有工具。
- 更有机会的是垂直、高频、可验证的 agent service。
- 对用户当前最有价值的切入点是：**自动化运行与验证 Unity 项目**。

曾参考的公开信号：

- [Unity AI](https://unity.com/features/ai)
- [Unity MCP overview](https://docs.unity3d.com/Packages/com.unity.ai.assistant%402.0/manual/unity-mcp-overview.html)
- [Unity MCP servers blog](https://unity.com/blog/mcp-servers-game-development)
- [Unity Gaming Report](https://unity.com/resources/gaming-report)

---

## 4. 当前聚焦问题

用户指出，在实际 Unity 开发工作中，最耗时的部分包括：

1. **需求开发、业务逻辑任务后的验证**
   - 通用 agent 能写代码，但验证仍然需要人手动运行 Unity。
   - 人需要点击、观察、看日志、判断是否成功。
   - 这是 coding agent 闭环中的断点。

2. **UI Prefab 拼接**
   - 需要根据效果图拼 Unity UI Prefab。
   - 这是另一个瓶颈，但更复杂，暂不作为 MVP 第一优先级。

我们把第一阶段目标聚焦到：

```text
Unity 游戏运行与验证 service 的基础设施
```

这个 service 先解决：

- 如何启动 Unity Editor
- 如何进入/停止/暂停/恢复 PlayMode
- 如何打开指定 scene
- 如何为一次运行创建 session
- 如何收集本次运行日志
- 如何让通用 agent 读取本次运行结果

暂时不解决：

- 自动理解游戏画面
- 自动点击游戏 UI
- 自动生成完整测试流程
- 自动拼 UI Prefab

---

## 5. 用户对侵入性的要求

用户明确提出：

```text
希望是无侵入式 service，或者少量侵入式 service。
```

经过讨论得出：

- **完全无侵入** 可以做到启动 Unity 进程、杀进程、读外部日志。
- 但完全无侵入很难稳定控制 PlayMode、Pause、Resume、打开 scene。
- 如果用系统级 UI 自动化去点 Unity Editor 的 Play 按钮，会很脆。

因此接受一个非常薄的少量侵入方案：

```text
Editor-only Unity Bridge package
```

要求：

- 只包含 Editor 代码。
- 不进入 runtime build。
- 不修改业务代码。
- 不污染游戏运行逻辑。
- 只在 Unity Editor 内提供控制通道。
- 对外通过本地 HTTP / CLI 暴露能力。

---

## 6. 需求大方向拆分

我们把 Unity 游戏运行 service 的需求分为几个大方向：

1. **运行控制**
   - 启动 Unity Editor。
   - 指定 Unity project、scene、参数。
   - 进入 PlayMode。
   - 停止 PlayMode。
   - 暂停/恢复 PlayMode。
   - 关闭/重启 Editor。

2. **运行观测**
   - 获取 Editor 状态。
   - 收集 Unity Console log。
   - 收集 Error / Exception / Assert。
   - 生成本次运行 summary。
   - 把日志和 summary 落盘。

3. **游戏内容结构化**
   - 让 service 理解当前游戏里有什么。
   - 可能包括 UI、文本、按钮、弹窗、玩家状态、任务状态、资源状态。
   - 这是核心难点，暂不进入 MVP。

4. **游戏操作**
   - 让 agent 能点击、输入、等待、选择、拖拽、触发流程。
   - 无侵入方案较脆，少量侵入方案更稳定。
   - 后续可探索录制/回放、UI tree 操作、gameplay command bridge。

5. **验证与报告**
   - 判断这次运行是否通过。
   - 输出错误日志、关键断言、截图、报告。
   - 未来可以和 coding agent 的修改闭环结合。

6. **对外接口**
   - 给 Codex / Cursor / CLI / MCP / HTTP 调用。
   - 例如 `run_game`、`get_state`、`click_ui`、`assert_text`、`stop_game`、`get_report`。

当前 MVP 只覆盖：

- 运行控制
- 运行观测中的日志落盘与 summary

---

## 7. 第一阶段：运行控制

第一阶段被命名为：

```text
Unity Editor Control
```

目标：

```text
让外部 agent 能稳定控制单个 Unity Editor 的 PlayMode。
```

具体能力：

- 启动 Unity Editor。
- 查询 Unity Editor 状态。
- 进入 PlayMode。
- 停止 PlayMode。
- 暂停 PlayMode。
- 恢复 PlayMode。
- 打开指定 scene。

第一版约束：

- 单 Unity 项目。
- 单 Unity Editor 实例。
- 固定本地地址：`127.0.0.1`。
- 固定默认端口：`17890`。
- 固定 Bridge URL：`http://127.0.0.1:17890`。
- 暂不做多项目 discovery。
- 暂不做 MCP。
- 暂不做 WebSocket。

推荐架构：

```text
通用 Agent / 人
    ↓
uv run unityctl CLI
    ↓
本地 HTTP
    ↓
Unity Editor Bridge package
    ↓
Unity Editor API
```

Bridge package 中使用：

- `EditorApplication.isPlaying`
- `EditorApplication.isPaused`
- `EditorSceneManager.OpenScene`
- `EditorApplication.isCompiling`
- `EditorApplication.isUpdating`

技术注意事项：

- `HttpListener` 回调不在 Unity 主线程。
- Unity Editor API 必须在主线程执行。
- 因此 Bridge 需要后台监听线程 + 主线程 command queue。
- 文档中已修正：HTTP response 由监听线程统一写，主线程只产出结果，避免超时后重复写 response。
- 文档中已修正：Bridge 需要在 `AssemblyReloadEvents.beforeAssemblyReload` 和 `EditorApplication.quitting` 时清理 listener。

对应计划文档：

- `docs/superpowers/plans/2026-06-30-unity-editor-control.md`

---

## 8. 第二阶段：运行观测

第二阶段被命名为：

```text
Unity Runtime Observability
```

目标：

```text
让每次 Unity PlayMode 运行都有一个可审计的 session，包含 session metadata、Unity Console 结构化日志和 summary。
```

核心设计原则：

```text
CLI 创建 session 目录，Bridge 只写入指定路径。
```

职责划分：

### CLI 负责

- 创建 `session_id`。
- 创建 session 目录。
- 写入初始 `session.json`。
- 调用 Bridge 的 `/session/start`。
- 调用 Bridge 的 `/play`。
- 在 `stop` 后调用 `/session/end`。
- 读取 `unity-console.jsonl`。
- 生成 `summary.json`。
- 对人和 agent 提供 `logs/errors/summary` 查询命令。

### Bridge 负责

- 接收 `sessionId` 和 `sessionPath`。
- 校验 `sessionPath` 必须位于当前 Unity project 的 `.unity-agent/sessions` 下。
- 注册 `Application.logMessageReceived`。
- 把 Unity Console log append 到 `unity-console.jsonl`。
- 在 session end 时 flush/close。
- 在 `/status` 或 `/session/status` 中返回当前 session 信息。

### 文件系统负责

文件系统是最终事实来源。

这点非常重要，因为：

- Editor 内存状态会丢。
- Bridge 缓存不适合长期复盘。
- 通用 agent 更容易读取和审计文件。
- session 目录可以和日志、summary、未来截图、报告放在一起。

---

## 9. Session 数据结构

Session 目录结构：

```text
<ProjectRoot>/.unity-agent/sessions/<sessionId>/
  session.json
  unity-console.jsonl
  summary.json
```

第一版 `session.json` 不包含代码上下文：

- 不包含 `branch`
- 不包含 `commit`
- 不包含 `diff`
- 不包含 PR 信息

原因：

- 第一版让 session 只描述一次 Unity 运行。
- 不与 git 强绑定。
- 非 git 项目也能用。
- 避免 dirty worktree、子模块、大 diff 等复杂性。
- 后续如果需要可扩展为 `git.json` 或 `git.diff`。

第一版 `session.json` 示例：

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

---

## 10. Unity Console 日志格式

Bridge 通过 `Application.logMessageReceived` 捕获 Unity Console logs。

写入文件：

```text
unity-console.jsonl
```

每行一条 JSON：

```json
{"time":"2026-06-30T18:30:14.001Z","sequence":12,"type":"Exception","message":"NullReferenceException...","stackTrace":"...","isPlayMode":true,"playModeFrame":356,"scenePath":"Assets/Scenes/Login.unity"}
```

字段说明：

- `time`
  - UTC 时间。
- `sequence`
  - 当前 session 内递增序号，从 `1` 开始。
  - 用于同一毫秒内多条日志排序。
- `type`
  - Unity log type。
  - 常见值：`Log`、`Warning`、`Error`、`Exception`、`Assert`。
- `message`
  - 日志正文。
- `stackTrace`
  - 堆栈信息，没有则为空字符串。
- `isPlayMode`
  - 写日志时 Editor 是否在 PlayMode。
- `playModeFrame`
  - PlayMode 中写入 `Time.frameCount`。
  - 非 PlayMode 中写入 `-1`。
  - 由于 Unity `JsonUtility` 不支持 nullable int，所以不用 `null`。
- `scenePath`
  - 写日志时当前 active scene path。

---

## 11. Summary 设计

第一版 `summary.json` 不使用简单的 `ok = true/false` 作为主判断。

原因：

- Unity 项目里有些 `Error` 可能是测试打印、已知问题，或实际只起 warning 作用。
- 如果所有 `Error` 都直接判失败，会过于悲观。
- 需要区分“发现问题信号”和“明确阻塞失败”。

因此使用：

```text
status
```

取值：

```text
passed
problem_detected
failed
```

默认规则：

```text
Log       -> ignored
Warning   -> counted, but not problem
Error     -> problem
Exception -> blocking
Assert    -> blocking
```

状态计算：

```text
blockingProblemCount > 0 -> failed
blockingProblemCount == 0 && problemCount > 0 -> problem_detected
problemCount == 0 -> passed
```

`Warning` 不影响 `status`。

`Error` 默认不直接 failed，而是 `problem_detected`。

`Exception` 和 `Assert` 默认 failed。

示例：

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

---

## 12. Ignore Rules

第一版支持一个简单配置文件：

```text
<ProjectRoot>/.unity-agent/log-rules.json
```

第一版只支持 `ignore`，不支持复杂 blocking 自定义。

示例：

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

规则含义：

- 命中 ignore 的日志仍保留在 `unity-console.jsonl`。
- 命中 ignore 的日志不计入 `problemCount`。
- 命中 ignore 的日志计入 `ignoredProblemCount`。

设计意图：

- 不掩盖事实。
- 不让 summary 过度悲观。
- 保持第一版足够简单。

---

## 13. 对外接口形态

当前决定优先支持：

```text
HTTP Bridge + Python CLI
```

其中：

- HTTP Bridge 运行在 Unity Editor 内。
- CLI 是推荐给通用 coding agent 使用的入口。
- Python CLI 使用 `uv` 管理；除非命令显式使用 `--project`，`uv run unityctl ...` 默认在 `src/unityctl` 目录下执行。
- MCP 暂时不做，未来可以作为外层适配。
- WebSocket 暂时不做，日志先通过落盘和 CLI 查询实现。

第一阶段 CLI：

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run unityctl status
uv run unityctl play
uv run unityctl pause
uv run unityctl resume
uv run unityctl stop
uv run unityctl open-scene Assets/Scenes/Login.unity
uv run unityctl start-editor --unity "/path/to/Unity" --project "/path/to/unity/project"
```

第二阶段 CLI：

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run unityctl play \
  --project "/path/to/unity/project" \
  --session login-flow \
  --scene Assets/Scenes/Login.unity \
  --task "verify login flow"

uv run unityctl stop \
  --project "/path/to/unity/project" \
  --session-path "<ProjectRoot>/.unity-agent/sessions/<sessionId>"

uv run unityctl logs --session-path "<ProjectRoot>/.unity-agent/sessions/<sessionId>" --limit 100
uv run unityctl errors --session-path "<ProjectRoot>/.unity-agent/sessions/<sessionId>"
uv run unityctl summary --session-path "<ProjectRoot>/.unity-agent/sessions/<sessionId>"
```

---

## 14. 已创建的计划文档

当前已有三份计划文档。

### 入口计划

```text
docs/superpowers/plans/2026-07-01-unity-agent-bridge-entry.md
```

作用：

- 总入口。
- 串联两个子计划。
- 明确执行顺序。
- 明确阶段验收。

### Phase 1: Unity Editor Control

```text
docs/superpowers/plans/2026-06-30-unity-editor-control.md
```

作用：

- 实现 Editor-only Bridge。
- 实现 `unityctl` 基础 CLI。
- 实现 PlayMode 控制。
- 实现 scene 打开。

### Phase 2: Unity Runtime Observability

```text
docs/superpowers/plans/2026-06-30-unity-runtime-observability.md
```

作用：

- 实现 session-based 运行观测。
- 实现日志落盘。
- 实现 summary。
- 实现 ignore rules。
- 实现 logs/errors/summary 查询。

新的 agent 应先读入口计划，再按入口计划进入 Phase 1 和 Phase 2。

---

## 15. 当前不做的方向

以下方向已经讨论过，但不进入当前 MVP。

### 不做：游戏画面结构化

原因：

- 让 LLM 理解游戏展示内容非常难。
- 如果依赖截图给多模态模型，速度慢、成本高、不稳定。
- 对 coding agent 验证闭环来说，不应作为第一主路径。

未来可能路线：

- UI tree 结构化
- runtime state snapshot
- accessibility-like metadata
- screenshot 作为辅助证据，而非主判断来源

### 不做：多模态截图分析作为主路径

原因：

- 可能拖慢节奏。
- 判断不稳定。
- 不适合作为自动验证的核心事实来源。

可以作为兜底：

- 黑屏检测
- UI 明显错位
- 视觉 diff
- 人类报告辅助图

### 不做：agent 自动操作游戏

原因：

- 操作游戏比运行与观测更难。
- 系统级点击无侵入但很脆。
- 稳定方案需要 UI tree 或 gameplay command bridge。

未来可能路线：

- 录制/回放人工操作
- 结构化 UI click
- gameplay command bridge
- test-only runtime command

### 不做：UI Prefab 拼接

原因：

- 这是用户真实瓶颈之一，但复杂度更高。
- 需要设计图理解、资源匹配、Prefab 层级规范、布局验证。
- 最好依赖运行控制与观测能力作为验证基础。

未来可作为单独产品线或后续计划。

### 不做：MCP 第一版

原因：

- CLI 已足够适合 Codex / Cursor / Claude Code 等通用 coding agent 调用。
- MCP 更适合作为外层适配，而不是核心协议。
- 先保证核心运行控制和观测闭环稳定。

---

## 16. 后续潜在路线

MVP 完成后，可以继续探索：

1. **截图与基础画面观测**
   - 截图落盘到 session。
   - 判断黑屏、窗口尺寸、是否卡死。
   - 生成带截图的 report。

2. **UI tree 结构化**
   - 低侵入读取 UGUI / UI Toolkit 层级。
   - 输出当前 UI、按钮、文本、panel。
   - 让 agent 不靠截图也能理解当前界面。

3. **游戏操作**
   - click button
   - input text
   - wait for UI
   - select item
   - drag

4. **录制/回放**
   - 先由人跑一次。
   - 记录操作流程。
   - 生成可重复执行的验证脚本。

5. **验证断言**
   - assert text exists
   - assert UI visible
   - assert no blocking problems
   - assert scene loaded
   - assert state changed

6. **MCP adapter**
   - 把 `unityctl` 能力包装成 MCP tools。
   - 给通用 agent 提供更结构化的 tool schema。

7. **多项目与多 Editor 实例**
   - discovery file
   - dynamic port
   - `unityctl list`
   - `unityctl status --project`

8. **CI 集成**
   - batchmode
   - headless test
   - report artifact
   - PR comment

---

## 17. 对新 agent 的执行建议

如果新 agent 要继续这个项目，请按以下顺序执行：

1. 先阅读本文档。
2. 再阅读入口计划：

   ```text
   docs/superpowers/plans/2026-07-01-unity-agent-bridge-entry.md
   ```

3. 不要直接开始 Phase 2。
4. 先完成 Phase 1：

   ```text
   docs/superpowers/plans/2026-06-30-unity-editor-control.md
   ```

5. Phase 1 验收通过后，再执行 Phase 2：

   ```text
   docs/superpowers/plans/2026-06-30-unity-runtime-observability.md
   ```

6. 执行时优先使用：

   ```text
   superpowers:subagent-driven-development
   ```

   或：

   ```text
   superpowers:executing-plans
   ```

7. 每个 task 按计划中的 TDD 步骤执行。
8. 不要擅自扩大 MVP 范围。
9. 不要把截图、多模态、UI tree、自动点击提前塞进第一版。
10. 如果发现计划中的代码片段无法编译，应优先修计划，再执行实现。

---

## 18. 语言与协作偏好

用户明确要求：

```text
所有 agent-user 交互必须使用中文。
```

但以下内容保持英文：

- 代码
- 注释
- 变量名
- 文件名
- 技术术语
- API 名称
- CLI 命令

协作偏好：

- 不要一上来长篇大论。
- 讨论要循序渐进。
- 先分大方向，再逐步展开。
- 用户会指出边界，agent 应收敛而不是扩散。
- 文档可以详细，但对话中要克制。

---

## 19. 当前仓库状态

当前仓库最初是一个空 git 仓库，没有已有代码实现。

目前已经创建的是文档：

```text
docs/superpowers/plans/2026-06-30-unity-editor-control.md
docs/superpowers/plans/2026-06-30-unity-runtime-observability.md
docs/superpowers/plans/2026-07-01-unity-agent-bridge-entry.md
docs/unity-agent-bridge-project-context.md
```

截至本文档创建时：

- 尚未实现 `packages/com.elex.unity-agent-bridge`。
- 尚未实现 `src/unityctl`。
- 尚未运行测试。
- 尚未提交 git commit。

---

## 20. 一句话总结

我们要做的是一个低侵入的 Unity Agent Bridge：让通用 coding agent 不再只能写 Unity 代码，而是能通过 CLI 控制 Unity Editor 运行，并拿到本次运行的结构化落盘日志和 summary，从而逐步形成“写代码 -> 运行 Unity -> 观察日志 -> 判断问题 -> 继续修复”的自动化闭环。
