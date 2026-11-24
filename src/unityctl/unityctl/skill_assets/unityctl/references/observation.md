# 实时监看与运行记录

所有命令从 Unity 项目根目录运行，或在命令前加 `unityctl --project PATH` 指定项目。

## 运行中看画面和步骤

1. 在单独的终端运行 `unityctl watch`，保留服务进程，打开其首条 JSON 输出里的本机 URL。URL 含随机访问凭据，不要分享、转发端口或写进共享日志。
2. 另一个终端运行 `unityctl scenario run PATH --observe`。页面跟随最新启用观察的 Scenario；未加 `--observe` 的运行不会出现在监看时间线中。
3. 画面按步骤刷新，不是视频。点击有截图的步骤可回看；用 `unityctl watch --session-id ID` 可固定到已有会话。用 Ctrl+C 退出只关闭监看服务，不退出 Unity 或停止 Scenario。

截图、失败留图和点击标记受项目截图配置与配额限制。没有可用帧时，不要把步骤状态当作视觉证据。watch 目前不实时监看 UTF 或 Midscene；也不会自动捕获普通终端命令。

## 运行结束后查证据

- `unityctl runs list` 列出当前项目的 Scenario、UTF 和 Midscene 记录；可用 `--kind scenario|utf|midscene` 和 `--limit N` 缩小范围。
- 从列表复制 `key`，执行 `unityctl runs show KEY`。外层 `ok: true` 只表示查询成功；验收必须看 `record.status`，再读失败步骤及其 `screenshot`、日志和报告路径。
- Midscene 的 `mode: offline` 是无模型回放，不代表模型已通过视觉验收。旧的孤立 HTML 如果没有运行元数据，不会自动入索引。

## 由当前 Agent 自己看图（可选）

如果当前 Agent 能看图且能执行 CLI，可以直接按 `interaction.md` 使用 `snapshot → 查看图片 → click-at → 再截图`，无需启动 Midscene 或配置额外的模型端点。读图片前遵守截图的 `agentImageAccess` 和项目的数据传输授权；命中定位可用 `hit-test` 辅助，不能确定时优先用 `hierarchy` 和确定性断言。不要把 Agent 的人工可读结论标成 Midscene `aiTap` / `aiAssert` 的通过结果。

用 `unityctl agent-run start --name NAME` 建立可监看的 Agent 会话。操作用 `unityctl agent-run step --session-id ID --why "公开的操作目的" -- COMMAND ...`，填入简短目的，不写内部推理。截图后，按真实 PNG 选点，点击命令额外加 `--frame 截图文件名`（放在 `--` 前面）。确定性验证可用 `--expect 'result="confirm"'` 比较实际 JSON 返回值。执行 `unityctl agent-run finish --session-id ID` 后，可以用 `watch --session-id ID` 回看；没有通过的结构化断言不算验收通过。
