# unityctl reference：完整错误码表

适用场景：遇到主文件高频表之外的错误码时查询。命令输出均为 JSON 信封（成功 `{"ok": true, ...}`，失败 stderr `{"ok": false, "code", "message"}`）。

## 常见错误码

| code | 含义与处理 |
|------|-----------|
| `compilation_failed` | 编译错误，读取 `compilationErrors` 修复代码后重跑 `unityctl refresh` |
| `timeout` | 等待状态收敛超时，可用 `--timeout <秒>` 放宽后重试 |
| `editor_exited` | Unity Editor 进程退出，运行 `unityctl start` 重新启动 |
| `editor_already_running` | 项目被占用但 Bridge 未就绪，运行 `unityctl doctor` 检查 |
| `bridge_unreachable` | Bridge 不可达，通常 Editor 未启动，运行 `unityctl start` |
| `bridge_capability_missing` | Bridge（UPM 包）版本过旧，缺少所需能力，升级 UPM 包后重试 |
| `node_not_found` / `ambiguous_path` | hierarchy 查询的 path/instanceId 找不到或有歧义，见 `hierarchy.md` |
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
