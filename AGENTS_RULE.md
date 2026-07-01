# AGENTS_RULE.md

## 语言规范 / Language Rules

### 1. 主语言

Agent 在与用户交互时，**必须使用中文**作为主要的回复语言。包括但不限于：对话回复、代码解释、方案说明、问题分析等。

### 2. 代码注释

代码中的注释**优先使用中文**编写，尤其是以下场景：

- 业务逻辑说明
- 复杂算法的步骤描述
- 方法/函数的功能描述
- TODO / FIXME / HACK 标记后的描述

示例：

```csharp
// 计算玩家与目标之间的距离，忽略 Y 轴高度差
float distance = Vector3.Distance(
    new Vector3(playerPos.x, 0, playerPos.z),
    new Vector3(targetPos.x, 0, targetPos.z)
);
```

### 3. 日志输出

代码中的日志/调试输出**优先使用中文**，方便非英语母语的开发者快速定位问题。

示例：

```csharp
Debug.Log($"已连接至 Unity Editor：{editorVersion}");
Debug.LogWarning("场景加载超时，请检查场景路径是否正确。");
Debug.LogError($"REST 请求失败，状态码：{statusCode}");
```

### 4. 专业术语保留英文

以下类型的词汇**保持英文原样**，不翻译为中文：

- **编程语言关键字和 API 名称**（如 `GameObject`、`MonoBehaviour`、`async/await`）
- **设计模式名称**（如 `Singleton`、`Observer`、`Factory`）
- **框架/库名称**（如 `Unity`、`NUnit`、`Newtonsoft.Json`）
- **计算机科学通用术语**（如 `HTTP`、`JSON`、`REST`、`WebSocket`、`TCP`、`GC`）
- **文件名、路径、命名空间**
- **Git 相关术语**（如 `branch`、`merge`、`rebase`、`commit`）

示例（好的写法）：

```csharp
// 通过 HTTP Bridge 发送 REST 请求到 Unity Editor
public async Task<Response> SendRequestAsync(string endpoint, object payload)
{
    // 将 payload 序列化为 JSON
    var json = JsonConvert.SerializeObject(payload);
    // ...
}
```

示例（不好的写法）：

```csharp
// 通过超文本传输协议桥接发送表征状态转移请求到统一编辑器
// "超文本传输协议" — 不自然，直接用 HTTP
// "表征状态转移" — 不自然，直接用 REST
```

### 5. 总结

| 场景 | 语言选择 |
|------|----------|
| Agent 对话回复 | 中文 |
| 代码注释 | 中文（优先） |
| 日志/调试输出 | 中文（优先） |
| 专业术语 | 英文 |
| 代码标识符（变量名/方法名等） | 英文（遵循项目现有规范） |
