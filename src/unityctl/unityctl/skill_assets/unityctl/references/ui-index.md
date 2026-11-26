# UI 索引：已知 UGUI 流程提速

索引让你提前查到「哪个 Prefab 可能包含目标」，不是截图识别、运行态对象或点击授权。未知 UI 可以先只读查看 Hierarchy 或 Game View，不能从资产名或按钮名推断业务效果。

1. **先核实目标和能力。** 查当前工程已验证的玩法路线及测试授权。用 `unityctl doctor --require-capability ui-index --require-route POST ui-index/scan` 检查同步能力；执行运行态操作前按需核对 `POST ui-index/bind`、`POST ui-index/resolve` 或 `POST ui-index/click`。缺能力时先报告，不能自动升级工程、切包或改走坐标点击。只查询本地快照不需要 Editor。
2. **已知目录优先同步。** 空闲 Edit Mode 执行 `unityctl ui-index sync --root Assets/UI`，用 `unityctl ui-index find --root Assets/UI "目标名" --type Button` 查询。常规复测复用同一 scope，下次只同步有变化的资产；不要每步全扫。多个候选、结果截断、缓存过期时，不取第一项：缩小范围，核对资产路径、根内层级、组件类型和当前界面。明确知道稳定来源后才选精确 ID。
3. **预先绑定保存过的实例。** 在已加载、已保存且无未保存更改的场景中执行 `unityctl ui-index bind <ID> --root Assets/UI --scene Assets/Scenes/Demo.unity --instance-root "Canvas/Dialog"`。绑定只留在当前 Editor，会在场景或资产来源变化时失效，不要把动态实例声明成静态 Prefab。同一已确认环境的重复测试无需每步重新绑定。
4. **运行时用一个命令校验并点击。** 确认 Play Mode 与当前界面就绪后执行 `unityctl ui-index click <ID> --root Assets/UI --scene Assets/Scenes/Demo.unity --instance-root "Canvas/Dialog"`。非强制点击会在同一 Bridge 请求中复核实例、当前顶层命中和可点击性。若先想只读核对身份，可以运行同参数的 `ui-index resolve`；它不保证可点击。在每次测试的验收点另验证弹窗、状态或回调结果；点击返回成功不等于游戏结果正确。
5. **动态界面用当前证据。** 从 Hierarchy 取得当前节点精确路径和 instanceId，用 `unityctl ui-index resolve --scene <scene> --runtime-path <path> --instance-id=<id>` 获取一次性凭证，再用 `unityctl ui-index click --scene <scene> --runtime-token <token>`。Hierarchy 标为 `DontDestroyOnLoad` 时，两条命令都显式传 `--scene DontDestroyOnLoad`；不要替换成激活场景。同一节点可有多个启用的点击处理器，凭证绑定本次核验的集合，不会改点其他节点。凭证仅在本轮 Play Mode 生效，不写进玩法记录、命令示例产物或审计。找不到、遮挡、失效或操作无响应时停下并重新观察；不要自动重试、猜坐标、强制点击或改点其他候选。
6. **记录用途，而非猜测。** 确定后用 `unityctl ui-index annotate --root Assets/UI <ID> --alias <alias> --purpose <purpose> --origin <source-inference|user-confirmed|runtime-verified> --evidence <reference>` 显式记录；只引用已脱敏的源码/玩法条目/运行证据。过期注释仅是线索。将可复用的业务流程与关键断言写到工程玩法知识里，别把原始截图、账号、密钥、存档或运行态凭证放进索引注释。

范围：Unity 2022.3、静态扫描只含 UGUI Prefab。场景独有节点和纯动态 UI 用当前 Hierarchy；看布局、文本截断、过渡、遮挡等仍要看实际画面。索引点击审计与原有交互审计同处，不替代产品验收。
