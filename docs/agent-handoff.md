# UnityRunBridge · Agent 开发交接

基线：`main` 的 `2a95ce0`（点击审计修复）。本文是接手入口，不替代各功能手册。代码和实际运行证据优先于旧调研、设计稿及没有更新的计划勾选框。修改范围、门禁或优先级时，更新本页并注明验收对应的提交。

## 当前范围

- 服务对象是需要开发和测试 Unity 项目的 Agent：从 `unityctl` 和内置 Skill 进入，经本地 HTTP Bridge 操作 Unity Editor。**只以 Unity 2022.3 为验收范围，实测版本为 2022.3.62f2。** 历史调研里的 Unity 2023 不代表支持承诺。
- 旧工程先用 `unityctl doctor` 对照 CLI、UPM 声明和运行态 Bridge，再按任务加 `--require-capability` / `--require-route`。版本不同只提示；能力缺失时按 `repairGuidance` 排查，项目依赖变更需要人工确认。见 [旧工程升级诊断](../README.md#旧工程升级诊断)。
- 确定性验证优先用 UTF（EditMode / PlayMode）或 Scenario。当前 Agent 可直接读取 Game View PNG、选择坐标并通过 `agent-run` 记录操作。只读的本地中文 `watch` 显示主动提供的操作理由、命令、点击落点和断言，不显示内部推理；画面是按步骤更新的截图，不是视频。
- 0.6.0 分支新增 [UI 索引](unityctl-ui-index.md)：静态 Prefab 同步、SQLite 离线发现与独立用途注释；已保存实例在 Edit Mode 绑定，在 Play Mode 才核验和非强制点击。UGUI 之外仍依赖当前 Hierarchy/截图，不自动改用旧点击。
- `watch` 不调用模型，不需要 Midscene。Midscene 是独立可选适配器；其自主视觉判断才需要模型。不要默认发送截图、开启 Gameplay 权限或暴露回环端口。Agent、Scenario、UTF、Midscene 四类历史记录统一通过 `unityctl runs list/show` 查询；并非四类都能实时监看。
- 普通 GitHub CI 只跑 Python、无模型 Midscene 适配器和 UPM 包校验，不运行 Unity，不恢复自托管 Mac Runner。Unity 实机回归在本机。Release 是独立的标签发布流程；未获授权，不创建或推送标签、不发布。

## 主要代码入口

| 要改什么 | 从这里开始 |
|---|---|
| CLI 命令、Bridge 请求、状态等待 | [cli.py](../src/unityctl/unityctl/cli.py)、[client.py](../src/unityctl/unityctl/client.py)、[convergence.py](../src/unityctl/unityctl/convergence.py) |
| Unity HTTP Host、路由和模块边界 | [BridgeServer.cs](../packages/com.mk.unity-agent-bridge/Editor/Host/BridgeServer.cs)、[BridgeModules.cs](../packages/com.mk.unity-agent-bridge/Editor/Features/BridgeModules.cs)、[Editor Adapters](../packages/com.mk.unity-agent-bridge/Editor/Adapters) |
| Game View 截图、点击及审计 | [CaptureController.cs](../packages/com.mk.unity-agent-bridge/Editor/Features/Capture/CaptureController.cs)、[InteractionController.cs](../packages/com.mk.unity-agent-bridge/Editor/Features/Interaction/InteractionController.cs)。改点击返回路径时同时验证点击响应、回调和审计写入；不要用一个提前返回绕过审计。 |
| Scenario、UTF 和记录索引 | [scenario.py](../src/unityctl/unityctl/scenario.py)、[utf.py](../src/unityctl/unityctl/utf.py)、[run_records.py](../src/unityctl/unityctl/run_records.py) |
| Agent 会话、事件流和监看界面 | [agent_run.py](../src/unityctl/unityctl/agent_run.py)、[run_events.py](../src/unityctl/unityctl/run_events.py)、[watch.py](../src/unityctl/unityctl/watch.py)、[watch_assets](../src/unityctl/unityctl/watch_assets) |
| UI 索引与运行态绑定 | [ui_index.py](../src/unityctl/unityctl/ui_index.py)、[UiIndexScan.cs](../packages/com.mk.unity-agent-bridge/Editor/Features/UiIndexScan.cs)、[UiIndexRuntime.cs](../packages/com.mk.unity-agent-bridge/Editor/Features/UiIndexRuntime.cs) |
| Skill、Midscene 适配器和测试 | [内置 Skill](../src/unityctl/unityctl/skill_assets/unityctl/SKILL.md)、[Midscene 示例](../examples/midscene-game-view/README.md)、[Python 测试](../src/unityctl/tests)、[Unity 测试](../packages/com.mk.unity-agent-bridge/Tests) |

功能细节见 [watch](unityctl-watch.md)、[运行记录](unityctl-runs.md)、[UTF](unityctl-utf.md)；架构背景见 [项目笔记](project-notes.md)；[旧实施计划](superpowers/plans) 只用于回查。

## 可复跑的测试

以下从仓库根目录运行。Python 用 `uv`；适配器用 Node.js 22；Unity 实机检查需要已激活的 2022.3.62f2，截图相关套件还需要可用的桌面会话。使用仓库测试工程，不要直接在用户游戏项目上试验。

```bash
# 不启动 Unity、不调用视觉模型
bash scripts/run-python-tests.sh
(cd examples/midscene-game-view && npm ci --ignore-scripts && npm test)
python3 scripts/eval-skill-triggers.py --check

# 本机 9 种 EditMode 组合：3 种 UI 配置 × 3 种输入模式
export UNITY_BIN="/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity"
mkdir -p .tmp
out="$(mktemp -d "$PWD/.tmp/matrix.XXXXXX")"
UNITY_MATRIX_RESULTS="$out/results" UNITY_MATRIX_LOGS="$out/logs" \
  bash scripts/run-unity-matrix.sh --set full

# 本机 UTF + 横竖屏 Game View 截图与坐标点击 + Scenario 监看
uv run --project src/unityctl --locked --no-dev python scripts/run-unity-smoke.py all

# 已安装适配器依赖后，验证 Agent 实时监看和四类记录（不调用模型）
uv run --project src/unityctl --locked --no-dev python scripts/run-unity-smoke.py records
```

检查打包或安装时，用 [分发包验收](unity-2022-smoke.md#从分发包验收) 的 `delivery`，而不是只跑源码模式。测试完成后检查退出码、NUnit XML 的通过／失败／跳过数量及相应日志；预期失败必须有对应断言和产物，异常退出或缺结果不能算通过。矩阵及 smoke 证据在本机 `.tmp/`，不会随 Git clone 分发；需要时用上述命令重建。不要把含本机路径、截图或凭据的日志直接提交。

## 已验证与未验证

0.6.0 UI 索引后续修复的验证范围和未跑项目，见 [最新验收状态](superpowers/plans/2026-11-26-ui-index-0.6.md#后续修复的验收状态2026-11-27)。下面的历史结果不代表最新候选已复跑。

| 状态 | 证据与边界 |
|---|---|
| 已验证：九配置全量矩阵 | `2a95ce0` 的单行修复在提交前用本机 Unity 2022.3.62f2 完整复跑：9 组、3,105 项通过、0 失败、42 跳过。原先失败的点击审计断言在 6 种带 UGUI 的配置均通过；测试断言未改。 |
| 已验证：无模型分发闭环 | 合并基线 `fbd6d9c` 用新构建的 wheel 和 UPM tarball，在临时弹窗工程跑通点击、监看、UTF 正反例和四类记录。同一合并版本本机 453 项 Python 测试、8 项适配器测试及包校验通过；后续审计修复单独验收见上一行。 |
| 已验证：远端轻量检查 | [合并基线 CI](https://github.com/mikko-ai/UnityRunBridge/actions/runs/45385218703) 的 Python、无模型适配器和 UPM 三项通过。这不是 Unity 实机结果。 |
| 已验证：旧 Bridge 诊断 | `0.5.0` 候选 CLI 源码连接 Unity 2022.3.62f2 临时工程中正式发布的 `0.4.1` UPM 包：版本不一致只告警；Core 状态接口可用；无 UGUI 时能报告坐标点击能力缺失并给出审批步骤。诊断前后 manifest、lock 和两份配置内容不变；没有实际执行升级。 |
| 未纳入本期：真实模型和生产项目验收 | Midscene 真实模型正反例按决定暂不执行。弹窗和 fixture 的证据不能代替指定游戏工程、真机或 Unity 其他版本的验收。 |
| 未验证：本批改动的新版本发布 | 本批没有打新标签或做发布端到端验收。旧 Release 的成功不能替代新版本验收。 |

## 下一步优先级（建议，按授权执行）

1. **先在一个获准的真实 Unity 2022.3 工程试点。** 用已打包的 CLI 和 UPM，跑一条低风险流程：安装 → Bridge 就绪 → Play Mode → Game View → 点击与断言 → 监看与记录。先确认能暴露哪些问题，再决定要扩展什么。
2. **按试点反馈补稳定性与可观测性。** 优先补可复现的失败和证据缺口，例如重连后状态、旧帧拒绝、审计缺失或运行记录不一致；先加能复现问题的回归，不默认增加新的 Bridge 或模型依赖。
3. **只有明确准备发版时才进入发布流程。** 用候选提交重跑本机全量矩阵及分发验收，核对 CI；确认范围后另行申请标签与发布授权。只有重新批准模型验收且配置可用时，才执行 Midscene 真实模型套件。
