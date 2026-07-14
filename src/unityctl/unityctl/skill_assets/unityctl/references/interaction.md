# unityctl reference：UI 操作 / 截图 / 录制

适用场景：模拟 UI 操作（click/input/set-value）、截图（snapshot）、录制语义动作（record）。命令输出均为 JSON 信封（成功 `{"ok": true, ...}`，失败 stderr `{"ok": false, "code", "message"}`）。

**Capability 依赖（0.3.0+）**：

| 命令 | 所需 capability | 项目可选依赖 |
|------|-----------------|--------------|
| `snapshot` | `capture` | 无（Core） |
| `click` / `input` / `set-value` | `interaction` | `com.unity.ugui` |
| `record` | `recording` | `com.unity.ugui`（指针后端另需 Legacy Input 或 Input System） |

缺 UGUI 时 Bridge 不声明 `interaction`/`recording`，CLI 返回 `bridge_capability_missing`。完整安装约 **30 路由 / 9 capability**；Core-only（NoUGUI）约 **24 / 7**。TMP 文本控件需额外安装 `com.unity.textmeshpro`；Input System 项目请将 Active Input Handling 设为 Input System Package 或 Both。

## 截图（需 Play Mode）

`unityctl snapshot` 截取当前 Game View 画面并落盘为 PNG，用于给多模态模型看画面或留存证据；底层是异步 job，命令会自动轮询直到完成。

```bash
unityctl snapshot                                    # 默认 reason=agent，落到当前 session 的 artifacts/ 或 .unity-agent/scratch/
unityctl snapshot --reason assert_failure            # 标注触发原因（不同 reason 独立计入配额）
unityctl snapshot --max-long-edge 800                # 单次覆盖输出长边像素上限
```

- 只在 Play Mode 且非 batchmode 下可用；受 `config.json` 里 `capture.screenshot` 配置项管控：`enabled`（总开关）、`allowAgentRequest`（是否允许 `reason=agent` 的主动请求）、`maxPerSession`（配额）、`maxLongEdge`（默认输出长边像素上限）、`agentImageAccess`（`allow`/`deny`，约定多模态模型是否可读取截图内容，Bridge 不做强制）。
- 输出的 `path` 字段是 PNG 的绝对路径；是否把这张图喂给自己（多模态读取）应遵循 `agentImageAccess` 的约定。

## UI 操作（点击/输入/设值，需 Play Mode + UGUI）

`click`/`input`/`set-value` 是模拟真实用户操作 UGUI 的顶层命令（跟 `play`/`stop` 同级，不是 `interaction` 子命令组），底层直接派发 Unity 事件系统的事件链（`IPointerDownHandler`/`onValueChanged` 等），不是修改内部状态。目标节点用 `hierarchy` 的 `path` 或 `instanceId` 定位。

### 目标定位约束（必须遵守）

- 截图仅用于理解当前画面与验证操作结果。截图可能经过长边缩放，尺寸不等于运行时屏幕；**禁止从截图像素坐标推导点击目标，也禁止选择视觉位置“最近”的按钮**。
- 执行 `click` / `input` / `set-value` 前，必须通过 `hierarchy find` / `tree` / `inspect` 将目标解析为唯一的 `path` 或 `instanceId`，再按语义节点操作。
- 查询返回多个候选时继续用节点名称、文本、组件、父子路径或 active 状态消歧；仍无法唯一确定时列出候选并请求用户确认，不得猜测。
- 当前交互命令只支持 UGUI `GameObject`。UI Toolkit 的 `VisualElement` 不属于 `Transform` hierarchy；在 Bridge 提供对应语义查询与交互能力前，不得退化为截图坐标点击。

```bash
unityctl click MainCanvas/ShopWindow/BuyButton              # 默认对目标 screenRect 中心做射线验证
unityctl click MainCanvas/ShopWindow/BuyButton --force      # 跳过射线检测，明知可能被遮挡也强制派发（调试用）
unityctl input MainCanvas/Login/NameField --text "Alice" --submit   # 写入文本并触发 onEndEdit/onSubmit
unityctl set-value MainCanvas/Settings/VolumeSlider --value 0.5              # Slider/Scrollbar 用数字
unityctl set-value MainCanvas/Settings/MusicToggle --value true              # Toggle 用布尔
unityctl set-value MainCanvas/Settings/Scroll --value '{"x": 0.5, "y": 0.2}' --component ScrollRect
```

- `click` 默认走射线验证：命中另一个元素则返回 `occluded` 并带 `blockedBy`（遮挡者的 path），命中链上没有点击处理器返回 `no_click_handler`；成功时返回 `clicked`（实际响应者 path）、`raycastHit`、`events`（实际派发的事件名列表）。只返回派发事实，不等待游戏反应——后续状态验证请配合 `hierarchy inspect` 或 `snapshot`。
- `set-value` 只支持固定组件列表（`Slider`/`Toggle`/`Scrollbar`/`Dropdown`/`TMP_Dropdown`/`ScrollRect`），`--value` 按 JSON 解析（数字/布尔/对象）；节点上有多个可设值组件时必须显式传 `--component`，否则返回 `ambiguous_component`。`TMP_*` 需项目已安装 TMP。
- 三个命令都要求 `editorState == "playing"`（暂停中也拒绝），否则返回 `not_in_play_mode`；场景里没有 `EventSystem` 时返回 `no_event_system`。

## 录制 UGUI 语义动作（需 Play Mode + UGUI）

`unityctl record` 把手工操作（点击、输入框失焦）录成结构化的 `actions.jsonl`，用来事后复盘、或作为 Phase 3 `scenario from-recording` 生成回放草稿的原料。只录 UGUI 语义动作（按 `path` 记录，不是坐标/像素），不录非 UI 的 gameplay 输入（WASD/摇杆等）。

```bash
unityctl record start                              # 不指定目录时落到当前 session 的 artifacts/，无 session 落 .unity-agent/scratch/
unityctl record start --latest                     # 显式落到最近 session 的 artifacts/
unityctl record start --session-path <path>        # 显式落到指定 session 的 artifacts/
# 手工点击/输入若干次……
unityctl record status                             # 查看是否在录制、已录制多少条
unityctl record stop                                # 停止录制，返回 actionsPath / actionCount / interrupted
```

- 产物两份：`recording-meta.json`（开始时间、activeScene、loadedScenes、屏幕分辨率、sessionId）与 `actions.jsonl`（每行一条动作，`click` 带 `screenPos` 附注、`input` 带失焦时的最终文本；两者都带 `scene` + `path`，多场景场景下用于消歧）。
- domain reload 或退出 Play Mode 会打断录制（监听状态无法跨越这两者存活）；`status`/`stop` 会如实返回 `interrupted: true`，已落盘的动作不会丢失，只是不会再有新动作被追加。
- 若项目未启用任何受支持的输入后端，`record start` 可能返回 `no_input_backend`（检查 Player Settings 的 Active Input Handling）。
- 回放不在本命令的范围内：`actions.jsonl` → scenario 草稿的转换由 `unityctl scenario from-recording` 承接（见 `scenario.md`）。
