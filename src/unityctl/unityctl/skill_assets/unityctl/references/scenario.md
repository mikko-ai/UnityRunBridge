# unityctl reference：Scenario 验证脚本

适用场景：编写/校验/执行可复跑验证脚本（scenario validate/run/from-recording）。命令输出均为 JSON 信封（成功 `{"ok": true, ...}`，失败 stderr `{"ok": false, "code", "message"}`）。

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
