---
name: unityctl
description: 使用 unityctl CLI 控制本地 Unity Editor 并验证运行结果。当需要启动 Unity Editor、进入/退出 Play Mode、触发脚本重编译、检查编译错误、收集 Unity Console 日志或生成运行 summary 时使用。适用于改完 Unity 项目代码后验证编译与运行是否正常的场景。
x-unityctl-version: __UNITYCTL_VERSION__
---

# unityctl：Unity 运行与验证

`unityctl` 是控制本地 Unity Editor 的 CLI。所有命令在 Unity 项目根目录或其子目录中执行（也可用 `--project <path>` 指定项目），输出统一为 JSON：成功时 stdout 输出 `{"ok": true, ...}`，失败时 stderr 输出 `{"ok": false, "code": "...", "error": "..."}` 且退出码为 1。

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

## 常见错误码

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
