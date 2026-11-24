# Midscene × Unity Game View

用现有 `unityctl` 将 **Unity Editor 的 Game View 截图 → Midscene 定位 → UGUI 像素点击 → 新截图视觉断言** 串起来。不需要 uloop、第二个 MCP Server、OS 鼠标注入，也不在 Unity Player 包内嵌入运行时 SDK。本示例独立安装 Node 依赖，不改变默认 CLI/UPM 的依赖。

## 快速开始

1. 在测试项目中安装包含 `click-at` 的 **CLI 和 Editor Bridge**、安装 UGUI，准备具有点击处理器和 EventSystem 的场景。可以复用 [弹窗回归演示](../verification/ui/README.md)。
2. 在有图形界面的 Editor 中显示 Game View，选固定分辨率。确认模型供应商可以接收这些画面，再按 [Midscene 文档](https://www.midscenejs.com/model-api-setup) 配置模型；没有授权，不要发送未发布游戏画面或真实用户数据。示例遵循 `capture.screenshot.allowAgentRequest`，并且只在 `agentImageAccess=allow` 时读取 PNG；该配置不能替代对云端数据传输的授权。
3. 确保 `unityctl` 在 PATH 上，从本目录安装依赖和运行：

```bash
npm ci --ignore-scripts
npm test
unityctl --project "$UNITY_PROJECT" play
npm run smoke -- "$UNITY_PROJECT" "画面中央的蓝色按钮" "中央出现弹窗，包含上下两个按钮"
unityctl --project "$UNITY_PROJECT" stop
```

运行完成会输出 `midscene:<id>`；用 `unityctl --project "$UNITY_PROJECT" runs show midscene:<id>` 查看截图、失败步骤和 HTML 路径。产物在该项目的 `.unity-agent/visual-runs/` 下，仅本机保存。

实际游戏应替换视觉提示和断言。`smoke` 不启停 Editor 或 Play Mode、不重试点击、不改变配置。失败后若 Play Mode 是你开启的，请按需退出。

## 适用边界

- 当前仅暴露 `Tap`。它对最上层 UGUI 射线命中派发点击，不穿透遮挡，不是通用键鼠、UI Toolkit 或 3D Gameplay 驱动。
- 每次点击前需要界面新截图。保持一个 Device 对应一个串行流程；如分辨率变化则重启流程。同尺寸下动态页面仍可能移动，应用稳定后再定位，点击后用独立断言验证实际结果。
- 截图使用已有配额且需要可读的 Game View 渲染纹理。不能在 Unity batchmode 或无图形环境中用此示例；打包后的桌面/移动端回归应使用相应的黑盒驱动。
- `npm test` 使用公开发布的 Midscene SDK 和假的 `unityctl` 执行器，验证适配契约，不调用模型。模型视觉结果只作体验证据，不能取代 Unity Test Framework 和确定性的 Scenario 断言。
