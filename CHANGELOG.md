# Changelog

本文件随 UPM 包一起分发（`com.mk.unity-agent-bridge` tarball 顶层）。

格式参考 [Keep a Changelog](https://keepachangelog.com/)，版本号遵循 [SemVer](https://semver.org/)。

## [0.6.0]（开发中）

- UGUI Bridge 可按目录增量抽取 Prefab 控件和持久回调线索；仅空闲 Edit Mode，读取导入资产，不执行回调。
- 新增 `unityctl ui-index sync/find/annotate`：事务更新工程本地 SQLite、离线发现控件，将用途与证据保存在独立注释库。
- UI 索引支持 Edit Mode 来源绑定和 Play Mode 同请求校验点击；动态控件使用一次性凭证，拒绝失效、遮挡和歧义，不走强制路径。
- 修复动态索引无法定位 `DontDestroyOnLoad` 常驻 UI：支持显式运行时范围，保留一次性凭证和原有点击安全校验。
- 索引点击支持同一节点的多个点击处理器；动态凭证核验实际组件集合，派发前重新核验原目标和顶层射线。
- 索引点击中止时，错误和审计保留已派发的指针事件，避免将部分执行误当作无副作用。
- 内置 Skill 说明如何复用已绑定的 UGUI 控件；UI 索引同步以 100 ms 间隔查询任务，缩短本机增量任务完成后的等待。

## [0.5.0]（未发布）

- 内置 Agent Skill 可跨会话复用工程内的玩法路线，记录待答问题、吸收用户纠正，并在复验后提升为已验证经验；无需新增 Bridge 能力。
- Watch 显示实时总耗时、步骤相对时间与单步耗时，并区分执行中和等待 Agent 下一步；旧记录无需迁移。
- `unityctl doctor` 对照 CLI、工程声明的 UPM 依赖和实际加载的 Bridge 版本；支持只读核验所需能力/路由，输出 Agent 可执行的升级指引和人工审批边界。
- `unityctl doctor` 同时报告 Skill 版本与工程配置格式版本；Agent Skill 增加操作前检查与修复前确认规则。
- 可选 Midscene 插件支持 `~/.unity-agent-bridge/plugins/midscene.jsonc` 用户级共享配置，同时兼容已有的 `midscene.json`；两者同时存在时明确报错，可在不启动 Unity 或调用模型的情况下检查。
- 新增 `unityctl plugins init midscene`：从任意目录创建带字段注释的 JSONC 模板，不覆盖或迁移已有配置、不读取模型密钥。
- Midscene 共享配置新增可选 `protocol`，支持选择 Chat Completions 或 Responses；初始化模板和配置检查提示合法值及兼容限制。

## [0.4.1]（已发布）

### 修复

- 修复同秒同名会话撞目录；Scenario 在 Play Mode 切换时允许状态查询短暂断开，结束会话失败仍保留本地报告和终态，且不会重复执行点击或播放命令。
- 补充 Game View 渲染尺寸超出 Unity 输入边界时的排查和分辨率调整方法，不绕过遮挡与射线检查。

## [0.4.0]（未单独发布）

### 编辑器 Bridge

- UGUI 支持从截图像素点击（`POST /interaction/click-at`）；只处理顶层命中，不穿透遮挡。
- 普通截图结果增加 `coordinateSpace`、`referenceScreen`，截图结果额外报告项目的 `agentImageAccess` 配置。
- 增加 UGUI 命中检查、长按与拖拽等操作；修复普通路径点击成功时提前返回、未写入审计记录的问题。

### CLI、测试与 Agent

- 新增本地中文 `watch` 和 `agent-run`：在 Unity Game View 的步骤截图上显示实际命令、操作理由、点击落点和结构化断言。使用当前 Agent 操作，无需为 Midscene 配置模型。
- `unityctl test run/status` 支持独立 Unity 进程执行 UTF EditMode / PlayMode，归档 JSON、NUnit XML 和 Unity 日志。
- `unityctl runs list/show` 统一查询 Agent、Scenario、UTF 和可选 Midscene 的运行证据。
- 扩展离线资源健康检查和构建体积分析；补充性能、弹窗 UI 回归示例和内置 Skill 触发评测。
- 验收范围保持 Unity 2022.3；远端日常 CI 只做不启动 Unity 的检查。Unity 全量矩阵、Game View 和监看在本机验证。

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
