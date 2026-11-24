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
- 运行事件与现有会话产物相邻保存：`.unity-agent/sessions/<id>/run-events.jsonl`。当前页面只监看启用了观察的 Scenario，不将 UTF 或 Midscene 报告伪装成实时进度。

## 可复跑验收

```bash
uv run --project src/unityctl --locked --no-dev python scripts/run-unity-smoke.py watch --unity /path/to/Unity.app
```

需要桌面会话。临时示例会跑通过和预期失败两轮，检查实际 Unity 运行期间 API 可读到步骤与点击标记、失败现场可回看，并保留 JSON 与截图。无需模型。
