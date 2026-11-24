# Unity Test Framework

- 项目需安装 UTF 并配置 Unity 路径。关闭该项目的 Editor，或使用独立副本；不会自动关闭 Editor。
- `unityctl test run --mode EditMode`；`unityctl test run --mode PlayMode`；可用 `--filter`、`--timeout` 及 `--unity`。
- `run` 等待完成。若 Harness 后台运行，预先指定唯一 `--job-id`，另一进程用 `unityctl test status ID` 查询。
- 只有 `status: "passed"` 才通过；`ok: true` 也可能只是运行中。检查 `.unity-agent/test-runs/ID/` 下的 JSON、NUnit XML 和日志，不以空结果代替验证。
- PlayMode 为 Editor 内逻辑验证；不替代 Game View 视觉验收或真机回归。
