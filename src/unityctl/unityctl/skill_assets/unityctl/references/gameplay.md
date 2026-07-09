# unityctl reference：Gameplay 命令桥

适用场景：绕开 UI 直接调用游戏逻辑（gameplay list/invoke），默认关闭需配置开启。命令输出均为 JSON 信封（成功 `{"ok": true, ...}`，失败 stderr `{"ok": false, "code", "message"}`）。

## Gameplay 命令（零侵入调用游戏代码，需 Play Mode，默认关闭）

`unityctl gameplay` 调用游戏侧暴露的命令，绕开 UI 直接触达 gameplay 逻辑（发货、加钱、切关卡等）。**默认关闭**（安全默认，需在 `config.json` 显式开启，见下）。两条发现通道完全独立：

1. **Duck-typed attribute**：游戏代码给公开静态方法标注一个短名为 `AgentCommandAttribute` 的 attribute（游戏自己定义这个类，不需要引用本包），即可被发现；attribute 若有 `Name` 属性则用作命令名，否则命令名默认为 `类名.方法名`。
2. **白名单直调**：`config.json` 的 `gameplay.whitelist` 里列出完全限定方法名（`Namespace.Class.Method`），无需游戏代码配合。

```json
{
  "gameplay": {
    "enabled": true,
    "whitelist": ["MyGame.CheatManager.AddGold"]
  }
}
```

```bash
unityctl gameplay list                                              # 查看当前可调用命令菜单（含参数/返回类型/是否可调用）
unityctl gameplay invoke CheatManager.AddGold --args '{"amount": 100}'
```

- 参数仅支持 `bool`/`int`/`long`/`float`/`double`/`string`/枚举（枚举可传名字字符串或整数）；`list` 输出里 `invocable: false` 的命令签名不受支持，`invoke` 会拒绝并说明原因。
- 每次 `invoke` 都会追加一行到当前 session 的 `artifacts/gameplay-invokes.jsonl`（无 session 时落 `.unity-agent/scratch/`），记录命令、参数、结果摘要、耗时，供事后审计。
- `invoke` 是任意代码执行入口：只在明确需要绕过 UI 直接验证/构造游戏状态时使用，且应在测试/开发环境启用，不建议对生产分支常开。
