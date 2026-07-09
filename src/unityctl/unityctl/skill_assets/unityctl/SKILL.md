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

- `play` 未指定 `--scene` 时，使用 `config.json` 的 `defaultScene`（`unityctl init --scene <路径>` 可写入）；若也未配置，则播放 Editor 当前已打开的场景。`--scene` 优先于 `defaultScene`。

判读规则：

- `refresh` 返回的 `compilationSucceeded` 为 `false` 时，`compilationErrors` 数组包含文件、行号和错误信息，先修复编译错误再继续。
- `summary` 的 `status` 为 `passed` 表示本次运行没有问题；`problem_detected` 表示出现了普通 `Error` 日志（不必然是业务失败，需要结合日志判断）；`failed` 表示出现 `Exception`/`Assert` 等 blocking problem，或发生了进程级失败（`failedReason` 字段记录原因，如 `compilation_failed`、`timeout`、`editor_exited`）。
- `summary` 的 `manualInterventionDetected` 为 `true` 表示 session 期间有人在 Unity Editor 中手动重新进入过 Play Mode——日志和问题统计混入了非受控运行，不要直接采信整体结论：先看 `runs` 数组（按 Play Mode 轮次分组的 `problemCount`/`blockingProblemCount`），用 `unityctl logs --run 1` 只看 CLI 触发的第一轮；如果问题出在手动轮次，建议重新 `play` 一个干净的 session 复现后再下结论。

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

## 能力索引

执行下列能力前，**必须先读取对应的 reference 文件**（相对本文件的 `references/` 目录），不要凭记忆猜测参数：

| 能力 | 命令 | reference |
|---|---|---|
| 日志查询与排错、log-rules 降噪/聚焦 | `logs` / `errors` | `references/logs.md` |
| 场景 Hierarchy 结构化查询（只读） | `hierarchy` | `references/hierarchy.md` |
| UI 操作、截图、动作录制 | `click` / `input` / `set-value` / `snapshot` / `record` | `references/interaction.md` |
| 零侵入调用游戏逻辑 | `gameplay` | `references/gameplay.md` |
| 可复跑验证脚本 | `scenario` | `references/scenario.md` |
| 性能采样 / Player 构建 / 健康检查 | `profile` / `build` / `health` | `references/profiling-build-health.md` |

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
