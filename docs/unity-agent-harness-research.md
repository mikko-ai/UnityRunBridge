# Unity 2023 Agent / Harness 调研：UnityRunBridge 落地判断

原报告：本地 Git 忽略目录中的 `tmp_refs/unity-2023-agent-harness-midscene-research.md`。下面是针对 UnityRunBridge 的技术取舍，不把原报告中的 Star、性能数字、工具数量或兼容范围当作验收结果。

## 结论：保留一个 Bridge，分三层验收

| 报告建议 | 仓库现状与决策 |
| --- | --- |
| Unity CLI / 官方 Agent Plugin | [官方仓库](https://github.com/Unity-Technologies/unity-agent-plugin#works-with) 将实时编辑器集成的产品目标列为 Unity 6+。可借鉴 Skill 的按需加载与检查清单，不把该工具链作为本项目的 Unity 2023 前提，也不据此断言所有独立技能都无法用于旧版。 |
| uloop / Unity-Skills / Coplay MCP | 项目已有 Editor-only 本地 HTTP Bridge、Token 握手、状态收敛、任务轮询、会话、日志和 CLI/Skill。已有的能力无需再移植一套；借鉴有明确信息差的功能，例如测试执行报告以及经 Unity 编辑器 API 的可回滚资源操作。 |
| 语义理解与静态分析 | Serena/LSP 是上层编码 Agent 的可选工具，不是 Editor Bridge 职责。Microsoft.Unity.Analyzers 可作为项目侧可选编译检查；需针对实际 Unity Roslyn 版本验证兼容 DLL、导入方式和诊断产物，不应将 NuGet 包或最新版 DLL 直接设成 UPM 强依赖。 |
| Midscene | [官方自定义接口](https://www.midscenejs.com/integrate-with-any-interface) 提供截图、尺寸和动作接口，不等于有 Unity 原生驱动。本项目已有 PNG 与 `hit-test`，缺口是基于同一像素坐标的安全点击。本次补齐 UGUI 像素点击与可选 SDK 示例，暂不接入通用输入、动态 C# 或运行状态写入。 |
| Unity Test Framework / CI | 确定性逻辑用 UTF / Scenario，视觉语义用 Midscene，构建及包体用 `build` / `build-size`。图形验证与 batchmode CI 分离，不让 CI 在没有 Game View 时误报视觉通过。 |

报告里提到的 Domain Reload 与 MCP/CLI 开销值得纳入选型，但不应使用固定的 10–30 秒或固定 Token 差值作产品承诺。Play Mode 设置、脚本变化、项目规模、桥接器版本和宿主能力都会改变结果。沿用 `unityctl` 已有的等待与重新发现机制；点击和其他有副作用的调用不做盲目重试。

## 首期实现

- `snapshot` 公开截图的坐标系、未缩放渲染尺寸及模型读取策略；保留原来的截图文件与配额。
- `click-at` 接收图像及原始渲染尺寸，映射并在同一个 Editor 请求中完成 UGUI Raycast 和事件派发。需要未暂停的 Play Mode，尺寸变化时在派发前失败。不会穿透遮挡；同尺寸的 UI 内容变化仍需要下一次截图与断言验证。
- [Midscene Game View 示例](../examples/midscene-game-view/README.md) 使用独立 npm 依赖，仅暴露 `Tap`，不操控 Play Mode 生命周期，不把第三方服务带入 Editor，也不引入玩家包体依赖。

## 后续优先级

1. **当前只验收 Unity 2022.3**：以本机 `2022.3.62f2` 覆盖截图、坐标点击和 UTF。用获准的模型跑 Midscene `aiTap → aiAssert` 仍需配置；不安排 Unity 2023 验收。
2. **UTF 结构化入口已实现**：[使用说明](unityctl-utf.md)。借鉴 Coplay 的任务 ID 和状态查询，用独立 batchmode Unity 进程运行，不依赖正在打开的 Editor/Bridge；产出 JSON、NUnit XML 和 Unity 日志。
3. **最后扩展能力**：若实际需要，分别考虑 UI Toolkit 输入和带预览的 Editor 资源操作。对场景、Prefab、资产批量写入先做预览/Undo，交由人类审批高风险修改；不默认启用动态 C#、生产包运行时控制或云端中继。

建议单次开发流程：读取代码与场景 → 计划并确认高风险写入 → 最小修改 → `refresh` 后核对编译结果 → UTF / Scenario 断言 → 必要时 Midscene 或真机视觉验证 → 汇总失败、日志、截图及已验证范围给人工验收。未执行的门禁不标记通过。

## 参考快照（仅调研，未引入产品）

| 上游 | 本地目录（置于 `tmp_refs`） | 快照 | 用途 |
| --- | --- | --- | --- |
| [Midscene](https://github.com/web-infra-dev/midscene) | `midscene` | `8a0f9949e` | 自定义 Device 接口；示例使用公开 npm 版本 `1.18.2` |
| [unity-cli-loop](https://github.com/hatayama/unity-cli-loop) | `unity-cli-loop` | `3cbff9ba` | CLI 工作流与编辑器调试 |
| [Unity-Skills](https://github.com/Besty0728/Unity-Skills) | `Unity-Skills` | `656c50c` | 编辑器操作和 Undo 范式 |
| [CoplayDev/unity-mcp](https://github.com/CoplayDev/unity-mcp) | `coplay-unity-mcp` | `19b66ec` | 异步测试、能力分组 |
| [Microsoft.Unity.Analyzers](https://github.com/microsoft/Microsoft.Unity.Analyzers) | `Microsoft.Unity.Analyzers` | `3696796` | Unity 特有静态诊断 |
