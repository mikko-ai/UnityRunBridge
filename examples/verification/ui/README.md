# UGUI 弹窗焦点与横竖屏回归

同一场景跑横屏和竖屏两次：打开弹窗时默认选中确认按钮，关闭后恢复到打开按钮。每次运行保留弹窗打开和关闭的 PNG，场景断言同时核对 Game View 尺寸和实际截图尺寸，不会把一轮横屏截图误当成竖屏结果。

## 准备独立测试场景

1. 在已安装 Bridge 的测试项目中安装 UGUI。演示脚本用 `StandaloneInputModule`，项目的 Active Input Handling 需要包含旧 Input Manager（Input Manager 或 Both）。用于已有游戏时，保留项目实际的输入后端，不要再添加第二个 EventSystem。
2. 把 [UiReviewDemo.cs](UiReviewDemo.cs) 放入测试项目的 `Assets/`。新建空场景 `Assets/Scenes/UiReview.unity`，只在一个空的 GameObject 上挂载该脚本。运行时会创建 UI，不需要预制件、图片或额外字体。
3. 把以下字段合并进测试项目的 `.unity-agent/config.json`，不覆盖其他设置；不要在生产项目开启 Gameplay 白名单。

```json
{
  "gameplay": {
    "enabled": true,
    "whitelist": [
      "UnityRunBridge.Examples.UiReviewDemo.FocusedControl",
      "UnityRunBridge.Examples.UiReviewDemo.ViewportSize"
    ]
  },
  "capture": {
    "screenshot": {
      "enabled": true,
      "onScenarioStep": true,
      "maxLongEdge": 1280
    }
  }
}
```

每个会话至少需要允许两张截图。探针只观察 EventSystem 的选中对象和 Canvas 的实际像素区域，不会替测试设置焦点或分辨率。

## 运行两轮

1. 打开 **有图形界面**的 Unity Editor，让 Game View 可见并选中该标签页。可先运行 `unityctl refresh`。
2. 在 Game View 分辨率下拉菜单选 **固定像素尺寸** 1280 × 720，不选 Free Aspect 或仅 16:9 比例。运行 [landscape.json](landscape.json)。
3. 等前一轮退出 Play Mode、`unityctl status` 返回 `editorState: idle`。改为固定 720 × 1280，运行 [portrait.json](portrait.json)。

```bash
unityctl scenario validate landscape.json
unityctl scenario run landscape.json --session modal-landscape
unityctl scenario validate portrait.json
unityctl scenario run portrait.json --session modal-portrait
```

脚本路径可以是绝对路径。若分辨率与预期不符，先确认 Game View 的固定尺寸、屏幕/设备模拟器是否替换了 Game View，以及截图是否被 `maxLongEdge` 降采样。不要为了让测试变绿而把预期尺寸改成已经抓到的错误尺寸。

## 机器断言与人工验收分开

- **机器断言**：核对视口，点击打开与关闭，判断弹窗可见性、默认焦点和恢复焦点；两张截图都必须写出且符合像素尺寸。读取会话的 `artifacts/scenario-result.json`：步骤 `dialog-open`、`dialog-closed` 的 `evidence` 记录相应 PNG 路径及宽高。
- **人工看图**：打开横、竖各两张 PNG，确认两枚按钮和文字完整、没有重叠，焦点样式与悬停有区别；关闭后背景恢复，打开按钮未被遮挡。截图尺寸通过不代表布局通过，也不是视觉差分。
- **键盘与手柄**：需要验证真实输入设备时，在 Game View 手动用上下方向键或手柄在两个弹窗按钮间移动，按确认/取消后观察焦点是否恢复。Scenario 的鼠标点击与 EventSystem 读取不验证设备映射、平台安全区或所有导航路径。

接入自己的游戏时，只移植只读探针和相应 Scenario，换成现有弹窗路径与真实业务期望。对刘海屏、安全区或本地化，另选目标设备和语言录制证据，不能从此演示推断通过。
