# unityctl reference：日志与排错

适用场景：查询/过滤 Unity Console 日志、排查错误、配置 log-rules（ignore 降噪 / watch 聚焦）。命令输出均为 JSON 信封（成功 `{"ok": true, ...}`，失败 stderr `{"ok": false, "code", "message"}`）。

## 日志与排错

日志可能非常多（尤其是 Play Mode 期间），不要直接用大 `--limit` 通读全量日志。推荐顺序：

```bash
# 1. 先看有没有错误/异常（已按 log-rules.json 过滤）
unityctl errors --latest

# 2. 再按关键字定位关注的日志（message 子串匹配，不区分大小写）
unityctl logs --latest --grep "关键字"

# 3. 需要看某条日志前后的上下文时，用输出中的 line 字段回到完整日志读取
#    （line 是该条日志在 unity-console.jsonl 中的 1-based 行号）
sed -n '120,140p' <sessionPath>/unity-console.jsonl
```

其他过滤参数：

```bash
unityctl logs --latest --type Error,Exception   # 按日志类型过滤
unityctl logs --latest --after-sequence 500     # 只看 sequence > 500 的增量日志
unityctl logs --latest --limit 20               # 过滤后只取最近 N 条（默认 100）
unityctl logs --latest --run 1                  # 只看第 1 轮 Play Mode 运行的日志
unityctl logs --latest --include-events         # 包含运行边界事件行（type=BridgeEvent，默认过滤）
```

`--after-sequence` 适合"要验证的行为发生在运行后期"的场景：先让游戏跑完初始化，用 `logs --latest --limit 1` 记下当前 sequence 作为游标，触发目标操作后只读游标之后的新日志，跳过全部启动噪音。输出中的 `totalCount`/`matchedCount` 分别是全量条数与命中条数。所有过滤只影响查询结果，`unity-console.jsonl` 始终保留完整日志。

每条日志带 `runIndex` 字段，标记它属于 session 内第几轮 Play Mode 运行（`0` 表示首轮运行开始前的编辑期日志）；每轮的起止由 Bridge 写入的 `BridgeEvent` 边界行（`runStarted`/`runEnded`）标出。一个 session 内 CLI 只触发一轮 play，出现 `runIndex >= 2` 的日志即说明有人手动重新进入过 Play Mode（summary 会同步给出 `manualInterventionDetected: true`），此时用 `--run` 把受控轮次和手动轮次分开判读。

```bash
unityctl open-scene <场景路径>         # 在 Editor 中打开场景
unityctl pause / unityctl resume      # 暂停/恢复 Play Mode
```

`.unity-agent/log-rules.json` 支持两类规则（规则可写 `type`、`messageContains`，同时给出时须同时满足）：

- `ignore`（降噪）：已知无害的 Error 日志（例如第三方插件的固定报错）不再计入问题，`errors` 与 `summary` 按同一套规则过滤，避免误判。
- `watch`（聚焦）：命中的日志会被提取进 `summary.json` 的 `watchedLogs` 字段（带 `line` 行号，最多保留最近 50 条，`watchedCount` 是全量命中数），不影响问题分类。

```json
{
  "ignore": [
    { "type": "Error", "messageContains": "已知无害的报错片段" }
  ],
  "watch": [
    { "messageContains": "本次要验证的关键日志片段" }
  ]
}
```

验证运行后期才发生的行为时，推荐在 `play` 之前把关注点写入 `watch` 规则：`stop --latest` 输出的 summary 会直接带出命中的日志，不需要再从全量日志里捞。
