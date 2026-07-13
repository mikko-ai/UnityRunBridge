# Changelog

本文件随 UPM 包一起分发（`com.mk.unity-agent-bridge` tarball 顶层）。

格式参考 [Keep a Changelog](https://keepachangelog.com/)，版本号遵循 [SemVer](https://semver.org/)。

## [0.3.0] - 2026-07-13

### 模块化重构（破坏性：内部程序集边界）

Editor-only 包从单体程序集拆为 **八个生产程序集**（均 `includePlatforms: Editor`）：

| 程序集 | 职责 |
|--------|------|
| `Mk.UnityAgentBridge.Editor.Core` | 契约、路由/能力 runtime、JSON、Jobs、Hierarchy 核心扫描；**无** UGUI/TMP/Input System 引用 |
| `Mk.UnityAgentBridge.Editor.Host` | Composition root：`[InitializeOnLoad]`、HTTP 管线、事务装配 |
| `Mk.UnityAgentBridge.Editor.Features` | Capability Module（core/jobs/hierarchy/capture/interaction/gameplay/recording/profiling/health） |
| `Mk.UnityAgentBridge.Editor.Build` | 独立 batchmode Player 构建入口 |
| `Mk.UnityAgentBridge.Editor.Adapters.UGUI` | UGUI 交互/录制后端与节点 Enricher（`defineConstraints: MK_HAS_UGUI`） |
| `Mk.UnityAgentBridge.Editor.Adapters.TMP` | TMP 文本控件与 Enricher（需 UGUI + TMP） |
| `Mk.UnityAgentBridge.Editor.Adapters.LegacyInput` | Legacy Input Manager 指针后端（`ENABLE_LEGACY_INPUT_MANAGER`） |
| `Mk.UnityAgentBridge.Editor.Adapters.InputSystem` | Input System 指针后端（`MK_HAS_INPUT_SYSTEM` + `ENABLE_INPUT_SYSTEM`） |

- `package.json` 的 `dependencies` 为空：`com.unity.ugui` / TMP / Input System 改为**项目侧可选依赖**；缺包时对应 Adapter 不参与编译。
- Host 通过 `[BridgeAdapter]` / `[BridgeModule]` + TypeCache 发现类型，事务装配候选 runtime；失败回滚，不产出半成品。
- Interaction / Recording 仅在存在 `IInteractionBackend` / `IRecordingSemanticBackend`（由 UGUI Adapter 注册）时声明 capability 并挂路由。

### 外部协议保持（非破坏）

对外 HTTP 信封、错误码、路径与能力名保持兼容：

- **完整安装**（含 UGUI）：**30** 条路由 / **9** 个 capability（含 `interaction`、`recording`）。
- **Core-only / NoUGUI**：**24** 条路由 / **7** 个 capability（无 `interaction`、`recording`）；CLI 对 UI 操作返回 `bridge_capability_missing`。
- `GET /capabilities` 仍按 ordinal 排序输出 capability 列表；路由 method/path 顺序与既有契约测试一致。
- CLI（`unityctl`）命令面与 session / artifacts 落盘约定不变。

### 其他

- 版本号同步为 `0.3.0`（`package.json` / `BridgeConfig.Version`）。
- 示例 manifest 见仓库 `examples/unity-project-manifest/`（`core-only` / `ugui-legacy` / `ugui-inputsystem` / `ugui-tmp` / `full`）。
