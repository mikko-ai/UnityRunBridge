# Midscene × Unity Game View

用现有 `unityctl` 将 **Unity Editor 的 Game View 截图 → Midscene 定位 → UGUI 像素点击 → 新截图视觉断言** 串起来。不需要 uloop、第二个 MCP Server、OS 鼠标注入，也不在 Unity Player 包内嵌入运行时 SDK。本示例独立安装 Node 依赖，不改变默认 CLI/UPM 的依赖。

## 快速开始

1. 在测试项目中安装包含 `click-at` 的 **CLI 和 Editor Bridge**、安装 UGUI，准备具有点击处理器和 EventSystem 的场景。可以复用 [弹窗回归演示](../verification/ui/README.md)。
2. 在有图形界面的 Editor 中显示 Game View，选固定分辨率。按下文配置本机模型并确认允许发送画面。示例遵循 `capture.screenshot.allowAgentRequest`，并且只在 `agentImageAccess=allow` 时读取 PNG；该配置不能替代对云端数据传输的授权。
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

## UnityRunBridge 用户级模型配置

使用 **`unityctl 0.5.0+`**，在任意目录执行：

```bash
unityctl plugins init midscene
```

它只在两种配置都不存在时创建 **`~/.unity-agent-bridge/plugins/midscene.jsonc`**。模板带字段注释，可使用 `//` 或 `/* ... */`，其余遵循标准 JSON 语法（不使用尾逗号）。初始化不需要 Unity 或 Node.js。所有 Unity 工程复用这份文件；不在项目配置或 JSONC 里存放 API Key。

已有 **`midscene.json`** 可以继续按标准 JSON 使用，不会被覆盖或迁移。`midscene.jsonc` 和 `midscene.json` 同时存在时，初始化和配置检查都会报错，请手动决定保留哪一份。

编辑生成的模板，按 [模型服务商配置](https://www.midscenejs.com/model-api-setup) 填写地址、ID 和类型。例如：

```jsonc
{
  // API 前缀，不包含 /chat/completions 或 /responses
  "baseUrl": "https://your-model-provider.example/v1",
  "modelName": "your-vision-model",
  "modelFamily": "qwen3-vl",
  "protocol": "openai-chat",
  "apiKeyEnv": "UNITY_BRIDGE_MIDSCENE_API_KEY"
}
```

`protocol` 可省略，省略时使用 `openai-chat`。只接受下列两个值（区分大小写）：

| 值 | 请求路径（追加到 `baseUrl`） | 何时使用 |
| --- | --- | --- |
| `openai-chat`（默认） | `/chat/completions` | 服务商提供 OpenAI Chat Completions。 |
| `openai-responses` | `/responses` | 网关支持 Responses，且所选模型适用；本示例锁定的 Midscene SDK 仅允许 `gpt-5` / `gpt-6` 类型使用。 |

`baseUrl` 填服务商的 API 前缀，如 `https://gateway.example/v1` 或 `https://gateway.example/api/v3`。不要把 `/chat/completions` 或 `/responses` 写进去。已有配置不用重建；需要切换时直接编辑 `protocol`。

`apiKeyEnv` 是环境变量的**名字**。在启动命令的终端或密钥管理器中注入对应变量，再从本示例目录运行 `npm run model:check`。它会校验协议和配置，显示所选协议；不会输出密钥、启动 Unity 或验证远端连通性。

`smoke` 和仓库的 `run-unity-smoke.py model` 使用用户级配置；两种文件都不存在时才兼容原有的 `MIDSCENE_*` 环境变量方式。一旦生成模板，需填完后才能使用；有配置文件但无效时直接报错，不悄悄改用另一个模型。普通 `watch`、Scenario、UTF 和无模型报告不加载该文件；项目截图权限仍由各 Unity 工程管理。

## 适用边界

- 当前仅暴露 `Tap`。它对最上层 UGUI 射线命中派发点击，不穿透遮挡，不是通用键鼠、UI Toolkit 或 3D Gameplay 驱动。
- 每次点击前需要界面新截图。保持一个 Device 对应一个串行流程；如分辨率变化则重启流程。同尺寸下动态页面仍可能移动，应用稳定后再定位，点击后用独立断言验证实际结果。
- 截图使用已有配额且需要可读的 Game View 渲染纹理。不能在 Unity batchmode 或无图形环境中用此示例；打包后的桌面/移动端回归应使用相应的黑盒驱动。
- `npm test` 使用公开发布的 Midscene SDK 和假的 `unityctl` 执行器，验证适配契约，不调用模型。模型视觉结果只作体验证据，不能取代 Unity Test Framework 和确定性的 Scenario 断言。
