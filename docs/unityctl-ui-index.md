# UI 索引（Unity 2022.3、UGUI）

UI 索引用于预先发现 Prefab 中的候选控件。同步只读 Unity 导入后的资产，不打开业务场景、触发监听器或修改资产；查找不需要 Unity 在线。缓存不包含运行时像素位置，也不证明控件可点击或回调行为正确。

```bash
# Unity 保持空闲 Edit Mode；先确认 Bridge 支持扫描
unityctl doctor --require-capability ui-index --require-route POST ui-index/scan
unityctl ui-index sync --root Assets/UI
unityctl ui-index find --root Assets/UI "确认" --type Button

# 只在有依据时补充用途；不会触发点击或调用模型
unityctl ui-index annotate --root Assets/UI <ID> --alias confirm   --purpose "提交当前弹窗的选择" --origin user-confirmed --evidence F-012
unityctl ui-index find --root Assets/UI --alias confirm
```

- 省略 `--root` 使用 `Assets`。每个目录有独立快照，按相同 `--root` 查找。同步不重抽未变化的 Prefab；`--full` 重新抽取整个指定目录，不清除其他目录。结果包含本次实际抽取、未变化、删除和未识别身份的控件计数。首次使用大型工程时建议先限定一个目录。
- 查询支持名称、Prefab 路径、层级路径、组件类型以及显式别名，可用 `--id` 查询精确候选。用 `syncedAt`、`ambiguous`、`truncated` 判断证据范围。即使只有一条候选，离线查询也总是 `liveVerified: false`。
- 机器索引是 `Library/UnityRunBridge/ui-index.sqlite3`，扫描失败不会替换上一次完整快照。已确认损坏或版本不兼容时，先退出同步、备份该文件再重新同步；工具不擅自重写不兼容数据库。
- 注释是单独的 `.unity-agent/ui-index-annotations.sqlite3`，可标记源码推断、人工确认或实机验证，并附项目内证据引用。请遵守当前工程的 Git 和凭据规则。不要填入账号、密钥、截图、原始日志或业务数据。注释与依赖指纹不匹配时标为 `stale`；控件身份变化时需重新核验并重新关联。删缓存不会删注释。
- 本期静态范围不包含 `.unity` 中独有的控件和纯动态 UI，也不分析 Lua/C# 动态监听的业务语义。持续用既有 Hierarchy、截图和玩法知识发现这些目标。

## 运行态定位与点击

静态索引不直接指向运行对象。对**场景里已保存的 Prefab 实例**，在当前 Editor 会话配好一次绑定：

```bash
# 先在 Edit Mode 打开对应场景并同步；场景必须已保存且无未保存改动。
unityctl doctor --require-capability ui-index --require-route POST ui-index/bind
unityctl ui-index bind <ID> --root Assets/UI --scene Assets/Scenes/Demo.unity --instance-root "Canvas/Dialog"
unityctl play --scene Assets/Scenes/Demo.unity
unityctl ui-index resolve <ID> --root Assets/UI --scene Assets/Scenes/Demo.unity --instance-root "Canvas/Dialog"
# resolve 可选：click 自身会重新核验身份和顶层射线。
unityctl ui-index click <ID> --root Assets/UI --scene Assets/Scenes/Demo.unity --instance-root "Canvas/Dialog"
```

- `--scene` 必须是已加载场景的完整资源路径。静态绑定的实例根须按名称逐层唯一匹配；不要用旧索引、相似名称或 `[0]` 猜测根。对根内的重复控件，系统核对实际槽位和来源身份，而不是取第一个。
- Unity 2022.3 的测试场景进入 Play Mode 后会丢失 Prefab 来源链接；Edit Mode 绑定保存在当前 Editor SessionState，不写场景、不跨 Editor 重启。它把已验证的来源与场景对象身份对应，运行时再次核验两者及依赖指纹。不符合时拒绝；重新同步、绑定或只读观察，没有自动坐标降级。
- 对**运行时动态创建**或无法证明来源的控件，先从当前 Hierarchy 获取精确路径与 instanceId。在 Play Mode 用 `ui-index resolve --scene <path> --runtime-path <path> --instance-id=<id>` 签发凭证，再用 `ui-index click --scene <path> --runtime-token <token>` 执行。凭证属于当前 Play Mode，约 120 秒过期，验证目标变更或消费后不可复用。它不是可持久化定位 ID，不写进注释、脚本或运行审计。
- `resolve` 只核验身份，不宣称能点击；`click` 才检查当前分辨率边界、Canvas、顶层 UGUI 射线、唯一点击处理器与可交互性。返回成功只表示按预期对象派发了 `pointerClick`，不代表业务流程通过。遇到遮挡、失效或结果不明，先重新观察，不盲重试。
- Bridge 为每次收到的索引点击尝试在会话 `artifacts/interaction-actions.jsonl` 写一行审计（无会话时在既有 scratch 目录），写入异常会告警。旧版或无 UGUI 工程不会自动调用其他点击接口。
