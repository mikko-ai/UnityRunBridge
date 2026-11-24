# Unity 2022.3 · 统一运行记录

在同一个 Unity 项目内，用一个只读入口查看 Scenario、Unity Test Framework 和 Midscene 的运行证据：

```bash
unityctl --project /path/to/project runs list
unityctl --project /path/to/project runs list --kind utf --limit 10
unityctl --project /path/to/project runs show scenario:<session-id>
unityctl --project /path/to/project runs show utf:<job-id>
unityctl --project /path/to/project runs show midscene:<run-id>
```

从列表复制 `key`。记录提供已有的失败步骤或测试、运行状态和原始产物的本地绝对路径：

| 类型 | 可查看的证据 |
| --- | --- |
| Scenario | 失败步骤、断言实际值与预期值、该步截图、Unity Console 日志、Scenario 原始 JSON；开启了 `--observe` 的会话还可用 `unityctl watch --session-id ID` 回看。 |
| UTF | 失败测试及堆栈、NUnit XML、Unity 日志和 Test Framework JSON。UTF 不生成 Game View 截图。 |
| Midscene | 失败步骤及对应截图、步骤日志和 Midscene HTML。记录中的 `mode` 区分真实模型与无模型回放；预期的负例拒绝标成 `failed_as_expected`，不计入异常失败列表。 |

`runs show` 成功读取时返回 `ok: true`；**运行是否成功看 `record.status`**。如果某次运行没有生成截图、XML 或报告，不为它合成证据。索引只显示本项目内的文件，不会复制历史报告、跟随符号链接或上传截图。旧 Scenario 和 UTF 无需迁移；仅有孤立 HTML、没有运行元数据的旧 Midscene 报告不会自动入索引，也不会被推断为「通过」。

新 Midscene 示例会把元数据、按步骤保留的截图和报告写到 `.unity-agent/visual-runs/<id>/`，并在终端输出 `key`。不要提交或未经审查共享这些产物。

## 复跑三种失败记录

先在 `examples/midscene-game-view/` 运行 `npm ci --ignore-scripts`，然后在有桌面的 macOS 上执行：

```bash
uv run --project src/unityctl --locked --no-dev python scripts/run-unity-smoke.py records \
  --unity /path/to/Unity.app
```

这项验收只使用临时项目和演示画面，不调用模型。在同一个独立项目里制造三类预期失败，再用 `runs list` 和 `runs show` 核对失败步骤、截图和日志是否可找到。
