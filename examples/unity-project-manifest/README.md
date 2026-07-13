# Unity 项目 Packages/manifest.json 示例

将 `com.mk.unity-agent-bridge` 路径替换为本地绝对路径，或改用 git/upm 版本号。

| 文件 | 场景 | 可选依赖 |
|------|------|----------|
| `core-only.json` | 仅 Core（无 UGUI） | 无 |
| `ugui-legacy.json` | UGUI + Legacy Input | `com.unity.ugui` |
| `ugui-inputsystem.json` | UGUI + Input System | `ugui` + `inputsystem` |
| `ugui-tmp.json` | UGUI + TMP（Legacy Input） | `ugui` + `textmeshpro` |
| `full.json` / `manifest.json` | 完整组合 | `ugui` + `tmp` + `inputsystem` |

说明：

- Bridge 包本身不再强依赖 UGUI；缺 `com.unity.ugui` 时 interaction/recording 不可用（CLI 返回 `bridge_capability_missing`）。
- Input System 需在 Player Settings 中将 Active Input Handling 设为 Input System Package 或 Both。
- TMP 需在项目中导入 TMP Essential Resources。
