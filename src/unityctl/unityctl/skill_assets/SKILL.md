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

# 2. 编译通过后，进入 Play Mode 并记录 session
unityctl play --session <名称> [--scene Assets/Scenes/Xxx.unity]

# 3. 观察一段时间后退出 Play Mode，自动生成 summary
unityctl stop --latest

# 4. 读取运行结果
unityctl summary --latest
```

判读规则：

- `refresh` 返回的 `compilationSucceeded` 为 `false` 时，`compilationErrors` 数组包含文件、行号和错误信息，先修复编译错误再继续。
- `summary` 的 `status` 为 `passed` 表示本次运行没有问题；`problem_detected` 表示出现了普通 `Error` 日志（不必然是业务失败，需要结合日志判断）；`failed` 表示出现 `Exception`/`Assert` 等 blocking problem，或发生了进程级失败（`failedReason` 字段记录原因，如 `compilation_failed`、`timeout`、`editor_exited`）。

## 环境准备

```bash
unityctl doctor            # 诊断：项目配置、UPM 包、Editor 进程、Bridge 连通性
unityctl start             # 启动 Unity Editor 并等待 Bridge 就绪（已在运行则幂等返回 already_running）
unityctl status            # 查询 editorState、编译状态、当前场景
```

- 项目未初始化时（缺 `.unity-agent/config.json`），先运行 `unityctl init --yes`，再在 `.unity-agent/config.local.json` 中配置 `unityExecutablePath`。
- `start` 返回 `editor_already_running` 表示项目被另一个 Editor 实例占用但 Bridge 未就绪，此时不要重试 `start`，先运行 `unityctl doctor` 检查，必要时请用户处理已打开的 Unity 窗口。

## 日志与排错

```bash
unityctl logs --latest --limit 100    # 最近一次 session 的 Unity Console 日志
unityctl errors --latest              # 只看 problem/blocking 级别的日志
unityctl open-scene <场景路径>         # 在 Editor 中打开场景
unityctl pause / unityctl resume      # 暂停/恢复 Play Mode
```

## 常见错误码

| code | 含义与处理 |
|------|-----------|
| `compilation_failed` | 编译错误，读取 `compilationErrors` 修复代码后重跑 `unityctl refresh` |
| `timeout` | 等待状态收敛超时，可用 `--timeout <秒>` 放宽后重试 |
| `editor_exited` | Unity Editor 进程退出，运行 `unityctl start` 重新启动 |
| `editor_already_running` | 项目被占用但 Bridge 未就绪，运行 `unityctl doctor` 检查 |
| `bridge_unreachable` | Bridge 不可达，通常 Editor 未启动，运行 `unityctl start` |

## 注意事项

- `play`/`stop`/`refresh` 默认阻塞直到目标状态达成，不需要自行轮询 `status`。
- Unity 编译（domain reload）期间 Bridge 会短暂中断，CLI 已内部处理重连，无需干预。
- session 产物位于 `.unity-agent/sessions/<sessionId>/`（`session.json`、`unity-console.jsonl`、`summary.json`），可直接读取文件做进一步分析。
