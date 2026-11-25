---
name: unityctl
description: 用 unityctl CLI 验证 Unity 项目。适用于旧工程 Bridge 版本与能力诊断、启动 Editor、重编译、Play Mode、Console 日志、Hierarchy/截图、UI Scenario、实时监看、运行记录查询、通过测试逐步积累玩法经验、记录卡点、询问待确认问题与吸收用户纠正、性能回归、离线 .meta/GUID 健康检查与构建体积预算。只写 Unity 代码、不执行验证，或只编写项目专属 Skill 时不使用。
x-unityctl-version: __UNITYCTL_VERSION__
---

# unityctl：Unity 运行与验证

`unityctl` 是控制本地 Unity Editor 的 CLI。所有命令在 Unity 项目根目录或其子目录中执行（也可用 `--project <path>` 指定项目），输出统一为 JSON：成功时 stdout 输出 `{"ok": true, ...}`，失败时 stderr 输出 `{"ok": false, "code": "...", "message": "..."}` 且退出码为 1。

## 操作前检查

首次接手工程、切换工程，或 CLI、Skill、Bridge 更新后，先运行一次 `unityctl doctor`。如果 Agent 加载的不是工程默认 Skill，使用 `--skills-target <Skill 根目录>` 检查实际加载的那份；传入安装 Skill 时指定的根目录，而不是 Skill 文件路径。只查历史记录、版本或诊断信息时，不要求 Editor 已启动；即使 Editor 离线，仍可从 stdout 读取 `doctor` 报告。

- 看 `versions` 和 `warnings`：对照 Skill 与 CLI、Bridge 声明与实际加载版本，以及 `configSchemaVersion` 和 `expectedConfigSchemaVersion`。配置格式版本不是产品版本。版本不同只提示，不因版本号不同就禁止使用；缺版本不等于兼容，不猜测或补写。
- 执行点击、输入等有副作用的操作前，用 `doctor --require-capability` / `--require-route` 核验任务所需能力。例如坐标点击需 `unityctl doctor --require-capability interaction --require-route POST interaction/click-at`。所需项 `missing` 就停止相关操作；`unverified` 时先排查，不能当作已核验。同一工程、工具和 Editor 环境未变时，可复用本次任务已通过的检查，不必每步重复查询。
- 默认只诊断。涉及更新 Skill、迁改配置或切换 UPM 依赖时，先说明原因、拟改动和复验方法，取得用户明确确认再修复。修复后重跑诊断与任务所需能力检查。

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

- `play` 未指定 `--scene` 时，使用 `config.json` 的 `defaultScene`（`unityctl init --scene <路径>` 可写入）；若也未配置，则播放 Editor 当前已打开的场景。`--scene` 优先于 `defaultScene`。

判读规则：

- `refresh` 返回的 `compilationSucceeded` 为 `false` 时，`compilationErrors` 数组包含文件、行号和错误信息，先修复编译错误再继续。
- `summary` 的 `status` 为 `passed` 表示本次运行没有问题；`problem_detected` 表示出现了普通 `Error` 日志（不必然是业务失败，需要结合日志判断）；`failed` 表示出现 `Exception`/`Assert` 等 blocking problem，或发生了进程级失败（`failedReason` 字段记录原因，如 `compilation_failed`、`timeout`、`editor_exited`）。
- `summary` 的 `manualInterventionDetected` 为 `true` 表示 session 期间有人在 Unity Editor 中手动重新进入过 Play Mode——日志和问题统计混入了非受控运行，不要直接采信整体结论：先看 `runs` 数组（按 Play Mode 轮次分组的 `problemCount`/`blockingProblemCount`），用 `unityctl logs --run 1` 只看 CLI 触发的第一轮；如果问题出在手动轮次，建议重新 `play` 一个干净的 session 复现后再下结论。

## 环境准备

```bash
unityctl doctor            # 只读诊断：工程配置、CLI/UPM/运行态版本、Bridge 连通性
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

### 旧工程接入与能力修复

命令返回 `bridge_capability_missing` 时，不要盲目重试。按任务核验需要的能力或路由，例如验证坐标点击：

```bash
unityctl doctor --require-capability interaction --require-route POST interaction/click-at
```

1. 读取 `versions` 和 `warnings`。Git 分支、提交和本地包路径不一定声明版本；`declaredUpmVersion: null` 时保留引用，不从文件名猜版本。仅版本不同不是失败；声明和加载版本不同，先检查 Package Manager 是否完成解析和编译。
2. 读取 `requirements`。只对任务需要且明确 `missing` 的项规划修复；`unverified` 表示 Editor 不可达或元数据不足，不要当成缺失。用只读检查排除可选依赖和编译问题，例如无 UGUI 的工程并不会因升级 Bridge 就出现坐标点击能力。
3. 按 `repairGuidance` 收集证据并给出最小修复方案。若确实要升级，先确认目标包支持任务和 Unity 2022.3，展示现有和目标引用、拟改动和回滚方式。凡 `requiresApproval: true`，取得用户明确授权后才执行：退出 Play Mode，保留原引用，只更新 Bridge 依赖，等待 Unity 解析并重新编译。不要猜测正式标签、手改 lock 文件、升级 Unity Editor 或覆盖项目配置；`init --install-package` 不会替换已有依赖，`init --force` 也不是升级工具。
4. 使用 `verify_repair` 的 `argv` 重新运行诊断（按参数数组调用，不拼成 shell 字符串），核对实际加载版本和所需能力，再重跑获准的最小任务。没拿到通过证据就报告阻塞，不称已修复。

## 能力索引

执行下列能力前，**必须先读取对应的 reference 文件**（相对本文件的 `references/` 目录），不要凭记忆猜测参数：

| 能力 | 命令 | reference |
|---|---|---|
| 日志查询与排错、log-rules 降噪/聚焦 | `logs` / `errors` | `references/logs.md` |
| 场景 Hierarchy 结构化查询（只读；Core，不依赖 UGUI） | `hierarchy` | `references/hierarchy.md` |
| 运行 UTF EditMode / PlayMode、查询测试结果 | `test run --mode` / `test status` | `references/tests.md` |
| UI 操作、截图、动作录制、自适应 UI 探索（UI 操作和录制需 UGUI） | `click` / `click-at` / `input` / `set-value` / `snapshot` / `record` | `references/interaction.md` |
| 零侵入调用游戏逻辑 | `gameplay` | `references/gameplay.md` |
| 可复跑验证脚本 | `scenario` | `references/scenario.md` |
| 本机实时监看 Scenario 或 Agent 操作、回看截图、查询运行记录 | `watch` / `agent-run` / `scenario run --observe` / `runs list` / `runs show` | `references/observation.md` |
| 性能采样 / Player 构建 / 构建大小 / 健康检查 | `profile` / `build` / `build-size` / `health` | `references/profiling-build-health.md` |

项目专属知识（界面约定等）不在本 skill 中：查看项目 `.agents/skills/` 下的其他 skill；如何编写见仓库 README「为你的项目编写自定义 skill」一节。

## 玩法学习与用户纠正

用户要求探索玩法、复玩、沉淀经验、查询测试中待确认的问题或纠正流程时，先读 [玩法经验工作流](references/gameplay-learning.md)。同一游戏工程内先复用已验证的路线，再补本次新发现；没把握就留下可回答的问题。用户答复先记为待复验，测试证据确认后才升级为可复用路线。玩法内容保存在各自工程，不写进通用 Skill；只问问题或解释知识时不需要启动 Unity。

## 高频错误码

完整错误码表见 `references/error-codes.md`，以下是最常见的 5 个：

| code | 含义与处理 |
|------|-----------|
| `compilation_failed` | 编译错误，读取 `compilationErrors` 修复代码后重跑 `unityctl refresh` |
| `timeout` | 等待状态收敛超时，可用 `--timeout <秒>` 放宽后重试 |
| `editor_exited` | Unity Editor 进程退出，运行 `unityctl start` 重新启动 |
| `editor_already_running` | 项目被占用但 Bridge 未就绪，运行 `unityctl doctor` 检查 |
| `bridge_unreachable` | Bridge 不可达，通常 Editor 未启动，运行 `unityctl start` |

## 注意事项

- `play`/`stop`/`refresh` 默认阻塞直到目标状态达成，不需要自行轮询 `status`。超时秒数默认读取 `config.json`，可用 `--timeout <秒>` 覆盖；`play`/`stop` 支持 `--no-wait` 立即返回（跳过状态收敛，一般不建议 agent 使用）。
- Unity 编译（domain reload）期间 Bridge 会短暂中断，CLI 已内部处理重连，无需干预。
- session 产物位于 `.unity-agent/sessions/<sessionId>/`（`session.json`、`unity-console.jsonl`、`summary.json`），可直接读取文件做进一步分析。
- 本文只覆盖常用流程；完整参数运行 `unityctl <命令> --help` 查看。
