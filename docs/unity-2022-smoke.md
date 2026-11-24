# Unity 2022.3 回归验收

在 Unity **2022.3.62f2** 上执行。脚本为每次运行创建独立的测试项目，不修改现有游戏工程，也不读取模型配置。

```bash
# UTF：EditMode 通过、PlayMode 通过、预期断言失败（须返回失败及堆栈）
uv run --project src/unityctl --locked --no-dev python scripts/run-unity-smoke.py utf --unity /path/to/Unity.app

# Game View：1280×720 / 720×1280 抓帧、缩放坐标点击、错误尺寸拒绝和遮挡
uv run --project src/unityctl --locked --no-dev python scripts/run-unity-smoke.py visual --unity /path/to/Unity.app

# 监看：步骤、点击标记和失败现场
uv run --project src/unityctl --locked --no-dev python scripts/run-unity-smoke.py watch --unity /path/to/Unity.app

# 全部依次执行；也可从 UNITY_BIN 读取编辑器路径
uv run --project src/unityctl --locked --no-dev python scripts/run-unity-smoke.py all
```

`visual` 需要可交互的桌面会话：会启动临时 Editor，并切换到 Game View。不要在无图形或只允许后台服务的 Runner 上把它标成通过。每次结果保留在 `.tmp/unity-smoke/run-*/`，可用 `--output` 指定父目录。临时目录及其 Unity Library 由调用方按需清理。

CI 默认运行 UTF 三例与无模型 Midscene 适配器测试；有可用桌面的自托管 Runner 时，从 CI 的手动触发入口启用 `visual_smoke`（图形回归及实时监看验收）。日志、XML、报告和截图在任务结束后可下载；**未选择图形回归不表示图形通过**。Midscene 的真实模型验收不属于这组无模型测试。
