# Review：Play Mode `runIndex` 边界方案改动

- 审查日期：2026-07-09
- 审查对象：`unity-console.jsonl` 新增 `runIndex` + `BridgeEvent` 运行边界行方案（Bridge 侧 `SessionController`/`SessionLogWriter` + CLI 侧 `summary.py`/`cli.py logs` + schema/文档同步更新）
- 审查方式：subagent 代码审查（model: claude-sonnet-5-thinking-high），对本次未提交改动的完整 diff 逐文件审查
- 状态：**问题已记录，尚未修复**（用户决定先记录、暂不改代码）

## 背景

会话（session）生命周期与 Play Mode 生命周期解耦：会话只由 `unityctl play`/`unityctl stop`（对应 Bridge 的 `session/start`/`session/end`）控制。用户在 Unity Editor 中手动停止再手动重新进入 Play Mode 时，Bridge 依靠 `SessionState` 在 domain reload 后自动恢复同一个会话，日志会持续以 Append 模式写入同一个 `unity-console.jsonl`，`sequence` 连续递增，两次 Play Mode 运行之间没有边界，也会污染 `summary.json` 的问题判定。

采纳的方案：

1. 不改变会话生命周期，`session/start`/`session/end` 语义不变。
2. Bridge 侧给每一轮 Play Mode 运行编号（`runIndex`，持久化到 `SessionState`，跨 domain reload 连续递增），每条 Unity Console 日志新增 `runIndex` 字段。
3. Bridge 侧订阅 `EditorApplication.playModeStateChanged`：`ExitingEditMode`（进 Play 流程开始、domain reload 之前）递增 `runIndex` 并写 `BridgeEvent`/`runStarted` 边界行；`EnteredEditMode`（退出流程完全结束后）写 `runEnded` 边界行。边界行与普通日志共用同一条 `sequence` 链。
4. 不做 `triggeredBy`（cli/manual）字段——因为一个 session 内 CLI 只会触发一轮 play，`runIndex >= 2` 本身即可推断"有人手动干预过"。
5. CLI 侧 `build_summary` 按 `runIndex` 分组统计（起止时间、sequence 区间、日志数、问题数），汇总进 `summary.json` 的 `runs` 数组，并给出 `manualInterventionDetected`（`len(runs) > 1` 即为 true）。
6. `unityctl logs` 新增 `--run N` 过滤、`--include-events`（默认过滤 `BridgeEvent` 边界行）。
7. 同步更新 `schemas/unity-console-log.schema.json`、`schemas/summary.schema.json`（含打包副本）、`examples/sessions/*`、`SKILL.md`、`docs/project-notes.md`。
8. 明确不做旧日志/旧 summary 的向前兼容处理（用户明确要求跳过）。

## 总体结论

**可以合入**，未发现会导致数据损坏、编译失败或现有测试回归的阻塞性问题：291 个 Python 测试全部通过，两份 schema 与打包副本字节一致，`examples/sessions/*` 经 schema 校验通过，`SessionLogWriterTests.cs` 覆盖了 `Write`/`WriteEvent` 的序列化逻辑。

但发现一个**应该修复**的设计缺口：`unityctl scenario run` 若一个 scenario 内写了多组 `play`/`stop`（同一个 session 内多次进出 Play Mode），会被误判为 `manualInterventionDetected: true`，直接违反了"一个 session 内 CLI 只会触发一轮 play"这一核心假设——而这个假设正是"不做 `triggeredBy` 字段"这一取舍的理由。另外，C# 侧新增的会话/轮次生命周期逻辑（`StartSession` 的 `runIndex` 初始值、`OnPlayModeStateChanged`、`RestoreActiveSession`）完全没有单测覆盖，只测了 `SessionLogWriter` 的序列化部分。

## 问题清单

### 阻塞级

无。

### 应该修复

**1. `scenario run` 多轮 play/stop 会让 `manualInterventionDetected` 产生误报**

- 位置：`src/unityctl/unityctl/scenario.py`（`CONTROL_ACTIONS` 定义、`play`/`stop` 步骤处理在 `_execute_step` 第 284-302 行）；`src/unityctl/unityctl/summary.py` 第 106-108 行：

  ```python
  # 一个 session 内 CLI 只会触发一轮 play，出现第二轮即说明有人在 Editor 中
  # 手动重新进入过 Play Mode——结果可能混入非受控运行，agent 应据此决定是否重跑。
  manual_intervention_detected = len(runs) > 1
  ```

- 问题：`scenario` 的 `steps` 是线性步骤表，`validate_scenario` 没有限制一个 scenario 内只能出现一次 `play`。测试"重启后能否正确读档"之类流程的 scenario（`play → ... → stop → play → ... → stop`）会在同一个 session 目录下产生两轮真实的 `ExitingEditMode`，Bridge 侧据此写出 `runIndex=1` 和 `runIndex=2` 两轮边界事件——这是 CLI 自己触发的，不是人工干预，但 `len(runs) > 1` 会把它误判为 `manualInterventionDetected: true`。
- 为什么是问题：一旦"一个 session 内 CLI 只会触发一轮 play"这个假设不成立，`manualInterventionDetected` 这个字段本身就不可靠，会误导 agent 认为"结果混入了非受控运行"而要求重跑，浪费 CI 时间，也可能让 agent 忽略掉这轮里真实出现的问题。
- 建议方向：给 scenario 引擎自己触发的 play/stop 打一个"受控轮次"标记（例如记录 CLI 侧已知的 play 次数，在 summary 阶段用这个数字而不是单纯 `len(runs)` 来判断"是否存在额外的、CLI 不知道的轮次"），或至少在文档里明确说明这个已知限制。

**2. C# 侧新增的会话/轮次生命周期逻辑完全没有单测**

- 位置：`packages/com.mk.unity-agent-bridge/Editor/SessionController.cs` 第 42-77 行（`StartSession` 里 `runIndex` 初始化）、第 165-196 行（`OnPlayModeStateChanged`）、第 101-132 行（`RestoreActiveSession`）。
- 问题：新写的测试全部落在 `SessionLogWriterTests.cs`，只验证了 `SessionLogWriter.Write`/`WriteEvent` 的 JSON 序列化格式，没有测到 `SessionController` 里任何新逻辑。既有的 `SessionControllerTests.cs` 也未同步补充。
- 为什么是问题：这批改动里风险最高的部分（`ExitingEditMode`/`EnteredEditMode` 时机、domain reload 后的恢复）恰恰是没有测试的部分，只靠代码审查和对 Unity 生命周期文档的记忆来保证正确性，日后重构容易在不知情的情况下破坏它。

### 建议改进

**3. `cli.py` 硬编码 `"BridgeEvent"` 字符串，没有复用 `summary.BRIDGE_EVENT_TYPE` 常量**

- 位置：`src/unityctl/unityctl/cli.py` 第 1415-1416 行：

  ```python
  if not args.include_events:
      filtered = [row for row in filtered if row.get("type") != "BridgeEvent"]
  ```

  对比 `summary.py` 第 13 行已定义 `BRIDGE_EVENT_TYPE = "BridgeEvent"`，`cli.py` 已从 `unityctl.summary` 导入多个符号却没有一起导入这个常量。
- 为什么是问题：两处硬编码同一个字符串值，未来若类型名要改容易漏改一处；属于命名一致性上的小瑕疵，不影响当前行为。

**4. `runIndex` 覆盖到"上一轮结束到下一轮开始之间"的编辑期日志，可能污染上一轮的 `problemCount`**

- `runEnded` 之后、下一轮 `runStarted` 之前的编辑期日志（例如手改代码触发的编译错误）仍会被计入"上一轮"的 `problemCount`，因为 `runIndex` 只在下一次 `ExitingEditMode` 才递增。
- 这个行为在 schema 里有隐含说明（"发生在第 N 轮开始之后、第 N+1 轮开始之前的日志标记为 N"），语义自洽不是 bug，但没有在 `docs/project-notes.md`/`SKILL.md` 里明确提醒 agent 这个具体副作用，容易让读 summary 的一方误解某一轮 Play Mode 本身出了问题。

**5. `WriteBoundaryEvent`/`OnLogMessageReceived` 没有任何异常防护**

- 位置：`packages/com.mk.unity-agent-bridge/Editor/SessionController.cs` 第 198-203 行：

  ```csharp
  private static void WriteBoundaryEvent(string eventName)
  {
      sequence += 1;
      logWriter.WriteEvent(eventName, sequence, runIndex);
      SessionState.SetInt(SequenceKey, sequence);
  }
  ```

- 若 `logWriter.WriteEvent`（同步磁盘 I/O）因磁盘满、文件被外部程序占用等原因抛异常，会导致 `sequence` 已在内存里 `+= 1` 但 `SessionState.SetInt` 没执行，内存值与持久化值出现偏差。概率低，风险可控，属于建议改进而非必须修复。

### 无关小问题

- `docs/project-notes.md` 与 `SKILL.md` 的更新内容与代码实现逐句对得上，没有发现文档滞后或描述不准确的地方。
- `examples/sessions/summary.json`、`examples/sessions/unity-console.jsonl` 的更新经实测对新 schema 校验通过，没有遗漏字段。
- 两份 schema 的打包副本与仓库根 `schemas/*.json` 逐字节比对完全一致。
- `schemas/summary.schema.json` 新增的 `run` `$defs` 字段列表与 `summary.py` 的 `_run_entry` 实际产出字段完全匹配。

## 六个重点风险点逐条结论

**① 时序正确性：`ExitingEditMode` 是否真的在 domain reload 之前完成，回调会不会被 reload 打断？**

不成立（设计可靠）。`playModeStateChanged` 的订阅回调在主线程同步、顺序调用，Unity 会等所有订阅者的回调执行完毕后才继续走到 domain reload 阶段；不存在"回调执行到一半被 reload 打断"的机制（除非回调本身抛异常，见问题 5，但那也不会导致 reload 打断回调，只是回调没跑完就退出，reload 依然会照常发生）。"递增 `runIndex` → 持久化 `SessionState` → 写边界行"这几步同步代码在 `ExitingEditMode` 里能可靠跑完再进入 reload。

**② `RestoreActiveSession` 路径：reload 后是否正确重新订阅了 `playModeStateChanged`？快速进出 Play 会不会漏事件/重复事件？**

不成立（未发现问题）。`RestoreActiveSession` 由 `BridgeServer` 的 `[InitializeOnLoad]` 静态构造函数在每次 domain reload 后调用，内部先 `-=` 再 `+=` 做了防重复订阅处理。Unity 保证"domain reload → `InitializeOnLoad` 静态构造函数执行 → 才触发 `EnteredPlayMode`/`EnteredEditMode`"这一严格顺序，所以订阅一定在事件真正触发前重新建立，不会漏事件；每次 reload 都先反订阅再订阅，也不会重复订阅。若项目关闭了 Domain Reload（Enter Play Mode Options），静态状态不会被清空，订阅原样保留，同样不会丢失。此结论未被测试验证。

**③ `StartSession` 里 `runIndex = EditorApplication.isPlaying ? 1 : 0`：这轮永远没有 `startedAt`，是否符合预期？**

成立，且是已知、已文档化的设计取舍，不算 bug。这个分支只在"session 在 Play Mode 进行中启动"时触发（例如 `unityctl play` 收到 `already_playing`），这一轮的 `ExitingEditMode` 早已在 session 创建之前发生过，Bridge 不可能补写 `runStarted` 事件，所以 `run["startedAt"]` 会永久是 `null`。`schemas/summary.schema.json` 与 `summary.py` 文档字符串已明确写出这一点。可考虑用 session 级别的启动时间或该轮第一条日志的 `time` 兜底，避免被误读为"数据缺失"，但属于锦上添花。

**④ `EndSession` 未清理 `playModeStateChanged` 但会话未激活时，`OnPlayModeStateChanged`/`WriteBoundaryEvent` 是否绝对安全？**

不成立（是安全的）。代码维持了一个不变式：**"已订阅 `playModeStateChanged`" 当且仅当 "`logWriter != null`"**——`StartSession`/`RestoreActiveSession` 在把 `logWriter` 置为非 null 时才订阅；`EndSession` 只有在 `logWriter != null` 的分支才会反订阅并置回 null。`OnPlayModeStateChanged` 开头的 `if (logWriter == null) return;` 是双重防御，即使不变式被破坏也不会 NRE 或误写。未发现能打破这个不变式的路径。

**⑤ CLI 侧 `_run_entry`/`_track_run_sequence` 对异常 `runIndex` 输入的健壮性；`runIndex == 0` 被排除在 runs 之外的设计是否与 schema 描述一致？**

代码本身健壮，但缺少测试覆盖这个健壮性声明。`row.get("runIndex", 0)` 默认为 0（等同编辑期日志）；非 int（字符串/None/浮点）时 `isinstance` 判断为 False，静默降级为不归入任何 `runs` 分组但仍计入 `logCount`/问题分类；负数同样被 `>= 1` 挡掉。`_track_run_sequence` 对 `sequence` 做了同样的 `isinstance` 判断，非法值直接 `return`。`runIndex == 0` 排除在外的设计在文档字符串、schema 描述、`--run` 参数帮助文本、`project-notes.md`、`SKILL.md` 里表述完全一致。缺口：这些健壮性路径目前没有任何单测直接验证。

**⑥ `manualInterventionDetected` 的推断逻辑（`len(runs) > 1`）是否有遗漏场景，尤其是 `scenario.py` 的 play/stop 逻辑？**

不成立——确认存在漏洞，即"应该修复 1"。`validate_scenario` 不限制一个 scenario 内 `play`/`stop` 出现的次数，`run_scenario` 的执行引擎会原样把每个 `play`/`stop` 步骤转发给 Bridge，没有做"同一 session 只允许一次 play"的约束或提示。`_teardown` 只在"最后一次进入过 play 且还没退出"时补一次 `stop`，不会额外触发 `runIndex` 递增，但如果 scenario 本身写了两个完整的 `play → stop` 步骤对，会切实产生两轮真实的 Play Mode 运行，让 `manualInterventionDetected` 对一次完全由 CLI/scenario 控制、没有任何人工介入的运行报出 `true`。这是这批改动里最值得关注的逻辑缺口。

## 测试覆盖建议

当前测试只覆盖了"happy path"和 JSON 序列化格式，建议补充：

**C# 侧（目前完全空白，建议加进 `SessionControllerTests.cs`）：**

1. `StartSession` 在 `EditorApplication.isPlaying == false` 时 `runIndex` 初始为 0，在 `true` 时初始为 1（若 Unity EditMode 测试环境下无法真实模拟 Play Mode，至少应把判断逻辑拆成可注入/可测的形式）。
2. `EndSession` 在 `logWriter == null` 时调用两次不会抛异常、`SessionState` 的四个 key 都被正确清空。
3. 通过反射直接调用私有的 `OnPlayModeStateChanged`（传入 `ExitingEditMode`/`EnteredEditMode`）在 `logWriter == null` 时是纯粹的 no-op（不写文件、不改 `SessionState`）。
4. 通过反射调用 `OnPlayModeStateChanged(ExitingEditMode)` 验证 `runIndex` 严格 +1 且 `SessionState.GetInt(RunIndexKey)` 同步更新。
5. `RestoreActiveSession` 在 `SessionState` 里有合法数据时能正确恢复 `runIndex`/`sequence`，且不会重复订阅事件（可用计数器包装事件订阅次数验证"先减后加"确实只订阅了一次）。

**Python 侧（建议加进 `test_summary.py`）：**

6. 一轮 run 只有普通日志、没有对应的 `runStarted` 事件（模拟 `StartSession` 里 `runIndex = 1` 的场景），验证 `run["startedAt"] is None` 且不崩溃。
7. `unity-console.jsonl` 里出现 `runIndex` 为字符串、负数、浮点、缺失字段的行，验证 `build_summary` 不崩溃、该行不进入任何 `runs` 分组、也不会污染其它轮次统计。
8. `unityctl scenario run` 对应一个含两个 `play`/`stop` 步骤对的 scenario，验证当前实现下 `manualInterventionDetected` 会被误置为 `true`——先写成"红"（失败/标注为已知问题）作为修复问题 1 的回归基线，修复后再转绿。

**建议加进 `test_cli.py`：**

9. `unityctl logs --run 0` 只返回编辑期日志（当前只测了 `--run 2`，没测边界值 0）。
10. `--run` 与 `--include-events` 组合使用、`--run` 命中一个不存在的轮次号（返回空列表而不是报错）。
