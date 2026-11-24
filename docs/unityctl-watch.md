# Unity 2022.3 · 本地实时监看

在同一 Unity 项目使用两个终端。先启动 Unity Editor，再开启监看服务：

```bash
unityctl --project /path/to/project watch
```

打开终端 JSON 中的 `url`。然后执行带 `--observe` 的 Scenario：

```bash
unityctl --project /path/to/project scenario run /path/to/scenario.json --observe
```

界面会显示 Editor 是否在线、用例状态、步骤进度和 Game View 画面。点击有截图的步骤可回看，选择「返回最新画面」可继续跟随。用例结束或失败后，可继续查看截图；重启服务时可用 `watch --session-id ID` 固定到历史会话。关闭服务用 Ctrl+C，不会关闭 Unity。

- 画面是按步骤获取的 PNG，不是连续视频。显式 Scenario 截图和失败断言的自动截图遵循原有设置；开启观察后，UGUI `click` 在点击前尝试留一帧，且只在点击与截图的原始渲染尺寸吻合时标记真实落点。没有可用截图时，步骤状态仍然会推进。
- `--observe` 默认关闭，没有额外截屏。开启时仍受项目截图开关、`onScenarioStep`、失败截图开关及配额限制。建议给监看用例保留足够配额；自动截图在快变画面上不能代替视觉断言。
- 监看只读，且只绑定本机回环地址，访问地址含随机凭据。不要分享该地址或转发端口。截图不会上传，也不需要 Midscene 或模型。
- 运行事件与现有会话产物相邻保存：`.unity-agent/sessions/<id>/run-events.jsonl`。页面可监看启用了观察的 Scenario 或显式记录的 Agent 会话，不把 UTF 或 Midscene 报告当作实时进度。

## 可复跑验收

```bash
uv run --project src/unityctl --locked --no-dev python scripts/run-unity-smoke.py watch --unity /path/to/Unity.app
```

需要桌面会话。临时示例会跑通过和预期失败两轮，检查实际 Unity 运行期间 API 可读到步骤与点击标记、失败现场可回看，并保留 JSON 与截图。无需模型。

## 监看当前 Agent 自己执行的步骤

不启动 Midscene。让具备看图能力的 Agent 读取 Unity Editor Game View 的 PNG，然后把明确需要展示的命令放进 `agent-run step`。页面仍是只读，本身不执行任意命令。

```bash
unityctl agent-run start --name "弹窗验证"
# 从输出复制 sessionId 给 SID；另一个终端运行 unityctl watch
unityctl agent-run step --session-id "$SID" --why "进入 Play Mode" -- play
unityctl agent-run step --session-id "$SID" --why "查看点击前的画面" -- snapshot --max-long-edge 640
# 查看返回的 PNG；把坐标、图片尺寸及 referenceScreen 尺寸替换成此次截图的实测值。
unityctl agent-run step --session-id "$SID" --why "按画面定位蓝色按钮" --frame screenshot-1.png -- \
  click-at --x 320 --y 180 --image-width 640 --image-height 360 --reference-width 1280 --reference-height 720
unityctl agent-run step --session-id "$SID" --why "验证焦点确实到了确认按钮" \
  --expect 'result="confirm"' -- gameplay invoke UnityRunBridge.Examples.UiReviewDemo.FocusedControl
unityctl agent-run step --session-id "$SID" --why "留存点击后的画面" -- snapshot --max-long-edge 640
unityctl agent-run step --session-id "$SID" --why "结束测试并退出播放" -- stop
unityctl agent-run finish --session-id "$SID"
```

该示例的 Gameplay 探针需按弹窗示例说明启用。只在独立测试项目开放探针。监看显示主动提供的操作理由、实际执行的命令、点击标记和依 CLI JSON 自动比较的预期/实际结果；不记录内部推理。若没有成功的结构化断言，结束状态为“未断言”，不是“已通过”。出错后不要自动重试点击；再次点击前重新截图。不要在理由、探针命名或参数里写入秘密。暂不监听 Agent 在记录命令之外的行为。

历史 Agent 会话同样支持 `unityctl runs list --kind agent` 和 `unityctl runs show agent:ID`。
