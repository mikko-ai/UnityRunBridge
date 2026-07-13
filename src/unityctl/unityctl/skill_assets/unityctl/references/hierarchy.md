# unityctl reference：Hierarchy 查询

适用场景：以只读方式查询场景 Hierarchy 结构（roots/tree/find/ancestors/inspect）。命令输出均为 JSON 信封（成功 `{"ok": true, ...}`，失败 stderr `{"ok": false, "code", "message"}`）。

**Capability**：`hierarchy` 属于 Core 能力，**不依赖** `com.unity.ugui`。无 UGUI 时仍可查询普通 GameObject；Button/`screenRect`/文本等 UGUI·TMP 富化字段仅在对应 Adapter 已编译时出现。

## 查询场景 Hierarchy（只读）

`unityctl hierarchy` 提供跟 Editor Hierarchy 窗口等价的结构化查询能力，Play Mode 内外都能用；只读、不修改场景，全部输出原样为 Bridge 的 JSON 信封。

```bash
unityctl hierarchy roots                                   # 列出所有已加载场景（含 DontDestroyOnLoad）的根节点
unityctl hierarchy tree MainCanvas --depth 2                # 从指定节点向下遍历子树
unityctl hierarchy find --component Button --active-only    # 全 AND 过滤，见 --help 看全部过滤器
unityctl hierarchy find --component Canvas --sort-by Canvas.sortingOrder --desc --page-size 1  # 取某属性最值
unityctl hierarchy ancestors MainCanvas/ShopWindow/BuyButton # 列出祖先（近到远）
unityctl hierarchy inspect MainCanvas/ShopWindow/BuyButton   # 查看完整组件与属性详情
```

- 节点用 `path`（`/` 分隔，同名兄弟带 `[index]` 后缀，如 `Item[0]`）或 `instanceId`（纯数字）定位；两者都可以直接作为 `tree`/`ancestors`/`inspect` 的位置参数传入。
- 多场景 Additive 加载导致同一 `path` 在多个场景命中时返回 `ambiguous_path`，用 `--scene <场景名>` 消歧（DontDestroyOnLoad 的场景名固定为 `DontDestroyOnLoad`）。
- `find` 分页统一用 `--page-size`（默认 50，上限 500）+ `--cursor`（取上次响应的 `nextCursor`）；响应里 `truncated: true` 说明还有更多结果。
- `find --where "Component.property<op>value"`（op 为 `= != > < >= <=`）用于按组件公开属性做单条件过滤；组件短名有歧义时报错并列出候选 FQN，改用完整类型名即可。
- 项目未安装 UGUI 时，`--component Button` 等 UI 类型过滤可能找不到类型（`unknown_component`）；Core-only 场景请用通用组件名或 `instanceId`。
