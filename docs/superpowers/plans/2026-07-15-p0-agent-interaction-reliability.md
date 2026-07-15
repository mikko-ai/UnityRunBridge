# P0 Agent 交互可靠性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为每次进入 `InteractionController` 的 click/input/set-value 调用写入安全、可校验的 JSONL 审计记录，并把可靠的自适应 UI 探索闭环固化到官方 unityctl skill。

**Architecture:** Bridge 新增 `InteractionAuditLog`，由 `InteractionController` 的统一 `AuditAndReturn` 出口调用；审计从原请求构建脱敏摘要，从原响应复制结果事实，写盘失败只告警。CLI 分发一份严格的 draft 2020-12 schema；官方 skill 用 L1/L2/L3 证据等级约束 Agent 的操作结论。

**Tech Stack:** Unity Editor C#、NUnit/EditMode、Unity Test Framework/PlayMode、Python 3.11、pytest、JSON Schema draft 2020-12、Markdown。

## Global Constraints

- 不编辑设计文档 `docs/superpowers/specs/2026-07-14-p0-agent-interaction-reliability-design.md`。
- 仅审计已进入 `InteractionController.Click` / `Input` / `SetValue` 且产生结构化结果的调用；Controller 之前的鉴权、路由、capability 拒绝不在范围内。
- 保持现有 HTTP/CLI 响应字段兼容；尤其 click/set-value 成功响应不得新增顶层 `code`。
- 审计写盘或序列化失败只能 `Debug.LogWarning`，不得改变原操作结果。
- input 的 `text` 与 set-value 的字符串/未知值不得以原文写入审计。
- P0 不新增 `wait-for`、`click --verify`、`runIndex`、审计轮转或 summary 判定。
- 不增加运行时或 Python 第三方依赖。

---

## File Map

**Create**

- `schemas/interaction-actions.schema.json`：仓库级交互审计 JSON Schema。
- `src/unityctl/unityctl/schemas/interaction-actions.schema.json`：CLI 包内分发副本。
- `src/unityctl/tests/test_interaction_audit_schema.py`：零第三方依赖的正反例契约测试，并断言两份 schema 相同。
- `packages/com.mk.unity-agent-bridge/Editor/Features/Interaction/InteractionAuditLog.cs`：请求摘要、响应映射和 append-only 写盘。
- `packages/com.mk.unity-agent-bridge/Tests/Editor/Features/Interaction/InteractionAuditLogTests.cs`：脱敏、字段契约、目录选择和异常隔离测试。

**Modify**

- `src/unityctl/unityctl/config.py`：把新 schema 加入 `SCHEMA_FILENAMES`。
- `src/unityctl/tests/test_config.py`：验证 `unityctl init` 分发新 schema。
- `packages/com.mk.unity-agent-bridge/Editor/Features/Interaction/InteractionController.cs`：三个入口统一通过 `AuditAndReturn` 返回。
- `packages/com.mk.unity-agent-bridge/Tests/Editor/Features/Interaction/InteractionControllerTests.cs`：覆盖三入口的参数错误、Play Mode 门禁和解析错误审计。
- `packages/com.mk.unity-agent-bridge/Tests/Editor/UGUI/EditorIntegration/PointerSimulatorTests.cs`：在单次 Play Mode 会话中增加 Controller click 成功审计。
- `packages/com.mk.unity-agent-bridge/Tests/Editor/UGUI/EditorIntegration/InputSimulatorTests.cs`：在单次 Play Mode 会话中增加 Controller input/set-value 成功审计。
- `src/unityctl/unityctl/skill_assets/unityctl/SKILL.md`：索引自适应探索协议。
- `src/unityctl/unityctl/skill_assets/unityctl/references/interaction.md`：闭环、三级证据、禁止项和审计说明。
- `src/unityctl/tests/test_skills.py`：冻结分发后的协议文案。
- `docs/project-notes.md`：记录 `interaction-actions.jsonl` artifact。
- `README.md`：在 schema 清单中列出新数据契约。

---

### Task 1: Schema、分发与契约反例

**Files:**
- Create: `schemas/interaction-actions.schema.json`
- Create: `src/unityctl/unityctl/schemas/interaction-actions.schema.json`
- Create: `src/unityctl/tests/test_interaction_audit_schema.py`
- Modify: `src/unityctl/unityctl/config.py:27-41`
- Modify: `src/unityctl/tests/test_config.py:72-80`

**Interfaces:**
- Produces: `interaction-actions.schema.json`，约束单行 JSON 对象。
- Produces: `SCHEMA_FILENAMES` 包含 `"interaction-actions.schema.json"`。
- Consumes: 无。

- [ ] **Step 1: 先写 schema 分发失败测试**

在 `test_init_project_config_copies_bundled_schemas` 末尾增加：

```python
assert (schemas_dir / "interaction-actions.schema.json").exists()
```

新增 `test_interaction_audit_schema.py`，先只写副本一致性和契约测试入口。测试 helper 必须检查：

```python
COMMON_REQUIRED = {
    "time",
    "action",
    "ok",
    "code",
    "request",
    "durationMs",
    "playModeFrame",
    "activeScenePath",
}
TOP_LEVEL_KEYS = COMMON_REQUIRED | {
    "scene",
    "message",
    "clicked",
    "raycastHit",
    "events",
    "forced",
    "blockedBy",
    "component",
}


def validate_record(record: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(record, dict):
        return ["record must be object"]
    missing = COMMON_REQUIRED - record.keys()
    if missing:
        errors.append(f"missing: {sorted(missing)}")
    if set(record) - TOP_LEVEL_KEYS:
        errors.append("unexpected top-level key")
    if not isinstance(record.get("ok"), bool):
        errors.append("ok must be boolean")
    if record.get("ok") is True and record.get("code") != "ok":
        errors.append("successful record must use code ok")
    if record.get("ok") is False and record.get("code") == "ok":
        errors.append("failed record cannot use code ok")
    if (
        not isinstance(record.get("durationMs"), int)
        or isinstance(record.get("durationMs"), bool)
        or record.get("durationMs", -1) < 0
    ):
        errors.append("durationMs must be non-negative integer")
    if (
        not isinstance(record.get("playModeFrame"), int)
        or isinstance(record.get("playModeFrame"), bool)
        or record.get("playModeFrame", -2) < -1
    ):
        errors.append("playModeFrame must be integer >= -1")
    if not isinstance(record.get("activeScenePath"), str):
        errors.append("activeScenePath must be string")
    action = record.get("action")
    if action not in {"click", "input", "set-value"}:
        errors.append("invalid action")
        return errors
    request = record.get("request")
    if not isinstance(request, dict):
        errors.append("request must be object")
        return errors

    allowed_request_keys = {
        "click": {"path", "force"},
        "input": {"path", "textLength", "submit"},
        "set-value": {"path", "component", "valueKind", "value", "valueLength"},
    }[action]
    if set(request) - allowed_request_keys:
        errors.append("unexpected request key")
    if record.get("code") != "invalid_argument" and not request.get("path"):
        errors.append("path required")
    if action == "click" and not isinstance(request.get("force"), bool):
        errors.append("force required")
    if action == "input" and not isinstance(request.get("submit"), bool):
        errors.append("submit required")
    if action == "input" and "text" in request:
        errors.append("text forbidden")
    if action == "click" and record.get("ok") is True:
        if not {"clicked", "raycastHit", "events", "forced"} <= record.keys():
            errors.append("click success fields required")
    if action != "click" and {
        "clicked",
        "raycastHit",
        "events",
        "forced",
        "blockedBy",
    } & record.keys():
        errors.append("click-only result field")
    if record.get("code") == "occluded" and not record.get("blockedBy"):
        errors.append("occluded requires blockedBy")
    if record.get("code") != "occluded" and "blockedBy" in record:
        errors.append("blockedBy only allowed for occluded")
    if action == "set-value" and record.get("ok") is True:
        if not record.get("component"):
            errors.append("set-value success requires component")
    elif "component" in record:
        errors.append("top-level component only allowed for set-value success")

    if action == "set-value":
        kind = request.get("valueKind")
        value_present = "value" in request
        if kind not in {"number", "boolean", "object", "string", "unknown", "invalid"}:
            errors.append("invalid valueKind")
        if kind in {"number", "boolean", "object"} and not value_present:
            errors.append("value required for typed kind")
        if kind in {"string", "unknown", "invalid"} and value_present:
            errors.append("value forbidden for redacted kind")
        if kind == "number" and (
            isinstance(request.get("value"), bool)
            or not isinstance(request.get("value"), (int, float))
        ):
            errors.append("number value required")
        if kind == "boolean" and not isinstance(request.get("value"), bool):
            errors.append("boolean value required")
        if kind == "object":
            value = request.get("value")
            if (
                not isinstance(value, dict)
                or set(value) != {"x", "y"}
                or any(
                    isinstance(item, bool) or not isinstance(item, (int, float))
                    for item in value.values()
                )
            ):
                errors.append("numeric x/y object required")
    return errors
```

正例必须覆盖：click 成功、occluded、缺 path 的 invalid_argument、脱敏 input、set-value number。反例用 `pytest.mark.parametrize` 覆盖设计文档 7.3 的八类错误；每个反例断言 `validate_record(record)` 非空。

- [ ] **Step 2: 运行测试并确认缺文件失败**

Run:

```bash
cd src/unityctl && uv run pytest tests/test_config.py::test_init_project_config_copies_bundled_schemas tests/test_interaction_audit_schema.py -q
```

Expected: FAIL，原因是 schema 尚不存在或未被分发。

- [ ] **Step 3: 编写严格 schema**

schema 顶层使用：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://mk.example/schemas/unity-agent-bridge/interaction-actions.schema.json",
  "title": "Unity Agent Bridge Interaction Audit Action",
  "type": "object",
  "additionalProperties": false,
  "required": ["time", "action", "ok", "code", "request", "durationMs", "playModeFrame", "activeScenePath"],
  "properties": {
    "time": { "type": "string", "format": "date-time" },
    "action": { "type": "string", "enum": ["click", "input", "set-value"] },
    "ok": { "type": "boolean" },
    "code": { "type": "string", "minLength": 1 },
    "request": { "type": "object" },
    "scene": { "type": "string", "minLength": 1 },
    "message": { "type": "string" },
    "clicked": { "type": "string", "minLength": 1 },
    "raycastHit": { "type": ["string", "null"] },
    "events": { "type": "array", "items": { "type": "string" } },
    "forced": { "type": "boolean" },
    "blockedBy": { "type": "string", "minLength": 1 },
    "component": { "type": "string", "minLength": 1 },
    "durationMs": { "type": "integer", "minimum": 0 },
    "playModeFrame": { "type": "integer", "minimum": -1 },
    "activeScenePath": { "type": "string" }
  }
}
```

在顶层 `allOf` 中加入以下完整条件：

1. `action=="click"` 时，`request.additionalProperties=false`，只声明 `path` 和必填 `force`。
2. `action=="input"` 时，只声明 `path`、`textLength>=0` 和必填 `submit`。
3. `action=="set-value"` 时，只声明 `path`、`component`、`valueKind`、`value`、`valueLength>=0`，并要求 `valueKind`。
4. `code!="invalid_argument"` 时，要求 `request.path` 为 `minLength:1`。
5. `ok:true` 时要求 `code=="ok"` 且禁止 `message`；`ok:false` 时禁止 `code=="ok"`。
6. click 且 `ok:true` 时要求 `clicked`、`raycastHit`、`events`、`forced`；其他 action 禁止这些字段。
7. `code=="occluded"` 时要求 `blockedBy`；其他 code 禁止 `blockedBy`。
8. set-value 且 `ok:true` 时要求顶层 `component`；其他情况禁止顶层 `component`。
9. set-value 的六个 `valueKind` 分支分别约束 `value`：number/boolean/object 必须存在且类型匹配；object 只能含数值 `x`、`y`；string/unknown/invalid 用 `not: {"required":["value"]}` 禁止 `value`。

完成仓库级 schema 后原样复制到 CLI 包内；禁止维护两份不同内容。

- [ ] **Step 4: 注册 schema 分发**

在 `SCHEMA_FILENAMES` 的 `actions.schema.json` 后加入：

```python
"interaction-actions.schema.json",
```

- [ ] **Step 5: 跑契约测试**

Run:

```bash
cd src/unityctl && uv run pytest tests/test_config.py::test_init_project_config_copies_bundled_schemas tests/test_interaction_audit_schema.py -q
```

Expected: PASS，且两份 schema 字节一致，全部正例通过、全部反例失败。

- [ ] **Step 6: Commit**

```bash
git add schemas/interaction-actions.schema.json src/unityctl/unityctl/schemas/interaction-actions.schema.json src/unityctl/unityctl/config.py src/unityctl/tests/test_config.py src/unityctl/tests/test_interaction_audit_schema.py
git commit -m "feat: define interaction audit contract"
```

---

### Task 2: InteractionAuditLog 安全构建与写盘

**Files:**
- Create: `packages/com.mk.unity-agent-bridge/Editor/Features/Interaction/InteractionAuditLog.cs`
- Create: `packages/com.mk.unity-agent-bridge/Tests/Editor/Features/Interaction/InteractionAuditLogTests.cs`

**Interfaces:**
- Produces: `InteractionAuditLog.BuildRequestSummary(string action, JsonValue body)`.
- Produces: `InteractionAuditLog.AppendFromResponse(string action, JsonValue request, string scene, object response, long durationMs)`.
- Produces: `InteractionAuditLog.SetHooksForTests(Func<string>, Action<string,string>)` 与 `ResetForTests()`。
- Consumes: `ArtifactPathGuard.ResolveArtifactDirectory()`、`JsonValue`、`BridgeResponse`。

- [ ] **Step 1: 写 builder 的失败测试**

测试 fixture 用 `[SetUp]`/`[TearDown]` 调用 `InteractionAuditLog.ResetForTests()`。新增测试：

```csharp
[Test]
public void BuildRequestSummary_Input_RedactsTextAndUsesUtf16Length()
{
    JsonValue body = JsonParser.Parse(
        "{\"path\":\"Main/Login\",\"text\":\"secret😀\",\"submit\":true}");

    JsonValue request = InteractionAuditLog.BuildRequestSummary("input", body);

    Assert.AreEqual("Main/Login", request["path"].AsString);
    Assert.AreEqual("secret😀".Length, request["textLength"].AsInt);
    Assert.IsTrue(request["submit"].AsBoolean);
    Assert.IsFalse(request.ContainsKey("text"));
    StringAssert.DoesNotContain("secret", request.ToString());
}
```

还要覆盖：

- click 缺省 `force:false`；
- set-value number/boolean 原值保留；
- 仅含数值 x/y 的 object 保留且不允许额外键；
- string 只写 `valueKind:"string"` 与 `valueLength`；
- array/null/复杂 object 只写 `valueKind:"unknown"`；
- 缺 value 写 `valueKind:"invalid"`。

- [ ] **Step 2: 写响应映射和 IO 隔离失败测试**

通过 appender hook 收集单行文本：

```csharp
List<string> lines = new List<string>();
InteractionAuditLog.SetHooksForTests(
    () => "/virtual/artifacts",
    (path, text) =>
    {
        Assert.AreEqual(
            Path.Combine("/virtual/artifacts", "interaction-actions.jsonl"),
            path);
        lines.Add(text);
    });
```

断言成功 click 行具有公共必填字段、`code:"ok"`、原样 `events`、nullable `raycastHit`；occluded 行具有 `message` 与 `blockedBy`；set-value 成功复制顶层 `component`。另用抛异常 appender：

```csharp
InteractionAuditLog.SetHooksForTests(
    () => "/virtual/artifacts",
    (_, __) => throw new IOException("disk full"));
LogAssert.Expect(
    LogType.Warning,
    "Unity Agent Bridge: 写入 interaction-actions.jsonl 失败：disk full");
Assert.DoesNotThrow(() => InteractionAuditLog.AppendFromResponse(
    "click", request, null, response, 3));
```

- [ ] **Step 3: 运行测试并确认类不存在**

Run:

```bash
UNITY_BIN="${UNITY_BIN:-/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity}" \
  ./scripts/run-unity-matrix.sh --set pr
```

Expected: FAIL，`InteractionAuditLog` 尚未定义。

- [ ] **Step 4: 实现请求摘要**

`BuildRequestSummary` 必须只读取白名单键：

```csharp
internal static JsonValue BuildRequestSummary(string action, JsonValue body)
{
    JsonValue request = JsonValue.NewObject();
    if (body != null && body.TryGetString("path", out string path) &&
        !string.IsNullOrWhiteSpace(path))
    {
        request["path"] = path;
    }

    if (action == "click")
    {
        request["force"] = body?.GetBoolean("force", false) ?? false;
    }
    else if (action == "input")
    {
        request["submit"] = body?.GetBoolean("submit", false) ?? false;
        if (body != null && body.TryGetString("text", out string text))
        {
            request["textLength"] = text.Length;
        }
    }
    else if (action == "set-value")
    {
        if (body != null && body.TryGetString("component", out string component) &&
            !string.IsNullOrWhiteSpace(component))
        {
            request["component"] = component;
        }

        JsonValue value = body != null && body.TryGet("value", out JsonValue item)
            ? item
            : null;
        AppendSafeValueSummary(request, value);
    }

    return request;
}
```

`AppendSafeValueSummary` 按设计文档 4.3 分类；object 只有 `Count==2`、键集合恰为 x/y 且两值均为 number 时才复制。

- [ ] **Step 5: 实现响应提取和 JSONL append**

类内默认 hook：

```csharp
private const string FileName = "interaction-actions.jsonl";
private static Func<string> directoryResolver =
    ArtifactPathGuard.ResolveArtifactDirectory;
private static Action<string, string> appendText =
    (path, text) => File.AppendAllText(path, text);
```

`BuildLine` 必须：

- 同时支持 `BridgeResponse` 和 object 类型的 `JsonValue` 响应；
- 成功审计合成 `code:"ok"`，失败取原响应 `code`；
- 失败且 message 非空时复制 message；
- 仅复制白名单结果字段；
- `time=DateTime.UtcNow.ToString("O")`；
- `durationMs=Math.Max(0,durationMs)`；
- `playModeFrame=Application.isPlaying ? Time.frameCount : -1`；
- `activeScenePath=EditorSceneManager.GetActiveScene().path ?? string.Empty`；
- scene 非空时放顶层，不放入 request。

写盘实现：

```csharp
internal static void AppendFromResponse(
    string action,
    JsonValue request,
    string scene,
    object response,
    long durationMs)
{
    try
    {
        JsonValue line = BuildLine(action, request, scene, response, durationMs);
        string path = Path.Combine(directoryResolver(), FileName);
        appendText(path, line.ToString() + "\n");
    }
    catch (Exception ex)
    {
        Debug.LogWarning(
            $"Unity Agent Bridge: 写入 interaction-actions.jsonl 失败：{ex.Message}");
    }
}
```

- [ ] **Step 6: 增加真实目录测试**

按最终审查时的用户决策，以设计 spec 和数据安全为准：注入唯一临时 directory resolver，但保留默认真实 `File.AppendAllText` appender，禁止读写或备份恢复项目真实 scratch。覆盖两种目录形状：

1. resolver 指向 `<unique-temp>/.unity-agent/scratch`；调用一次 `AppendFromResponse` 后断言实际生成 `interaction-actions.jsonl`，行数恰好为 1。
2. resolver 指向 `<unique-temp>/.unity-agent/sessions/interaction-audit-test/artifacts`；追加后断言文件实际位于该目录。

这两个测试都断言实际文件内容可被 `JsonParser.Parse`，不得只断言路径；finally 仅删除自己的唯一临时根，不调用或改变 `SessionService`。

- [ ] **Step 7: 跑测试**

Run:

```bash
UNITY_BIN="${UNITY_BIN:-/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity}" \
  ./scripts/run-unity-matrix.sh --set pr
```

Expected: PASS。

- [ ] **Step 8: Commit**

```bash
git add packages/com.mk.unity-agent-bridge/Editor/Features/Interaction/InteractionAuditLog.cs packages/com.mk.unity-agent-bridge/Tests/Editor/Features/Interaction/InteractionAuditLogTests.cs
git commit -m "feat: add safe interaction audit log"
```

---

### Task 3: Controller 统一审计出口与失败路径

**Files:**
- Modify: `packages/com.mk.unity-agent-bridge/Editor/Features/Interaction/InteractionController.cs:1-169`
- Modify: `packages/com.mk.unity-agent-bridge/Tests/Editor/Features/Interaction/InteractionControllerTests.cs:8-112`

**Interfaces:**
- Consumes: Task 2 的 `BuildRequestSummary` 与 `AppendFromResponse`。
- Produces: `Click`、`Input`、`SetValue` 每个结构化 return 恰好审计一次。
- Produces: 测试 seam `InteractionController.SetPlayModeStateProviderForTests(Func<string>)` 与 `ResetForTests()`，仅替换 Play Mode 状态读取，不伪造业务后端。

- [ ] **Step 1: 扩展现有失败测试，先观察漏审计**

每个测试安装内存 appender，并记录 `before = lines.Count`。分别覆盖：

- Click/Input/SetValue 缺 path → `invalid_argument`；
- Click/Input/SetValue idle → `not_in_play_mode`；
- 注入 `"playing"` 后传不存在路径 → `node_not_found`。

统一断言：

```csharp
Assert.AreEqual(before + 1, lines.Count);
JsonValue audit = JsonParser.Parse(lines[before]);
Assert.AreEqual(expectedAction, audit["action"].AsString);
Assert.IsFalse(audit["ok"].AsBoolean);
Assert.AreEqual(expectedCode, audit["code"].AsString);
Assert.AreEqual(expectedCode, ((BridgeResponse)result).code);
```

input body 使用秘密值并断言审计行不含秘密原文。每个 fixture teardown 重置 Controller 和 AuditLog hooks。

- [ ] **Step 2: 运行并确认审计行数失败**

Run:

```bash
UNITY_BIN="${UNITY_BIN:-/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity}" \
  ./scripts/run-unity-matrix.sh --set pr
```

Expected: FAIL，现有 Controller 不写审计行。

- [ ] **Step 3: 在三个入口建立统一上下文**

每个方法第一段采用相同形状：

```csharp
Stopwatch stopwatch = Stopwatch.StartNew();
JsonValue body = ctx.Body;
JsonValue request = InteractionAuditLog.BuildRequestSummary("click", body);
string scene = body != null && body.TryGetString("scene", out string sceneValue)
    ? sceneValue
    : null;
```

注意：

- request 必须在 path 校验前构建，才能审计缺 path；
- input 原始 text 只保留在方法局部，不传给 AuditLog；
- `services = BridgeServices.Current(services)` 可留在参数校验后，避免参数错误依赖 runtime。

- [ ] **Step 4: 实现唯一返回 helper**

```csharp
private static object AuditAndReturn(
    string action,
    JsonValue request,
    string scene,
    object response,
    Stopwatch stopwatch)
{
    InteractionAuditLog.AppendFromResponse(
        action, request, scene, response, stopwatch.ElapsedMilliseconds);
    return response;
}
```

把三个方法中所有结构化 `return response/gate/failure/occludedJson` 改成 `return AuditAndReturn(...)`。不得在分支中直接调用 `AppendFromResponse`，防止重复或漏记。

- [ ] **Step 5: 增加 Play Mode 状态 seam**

默认 provider 仍调用 `EditorStateProvider.DeriveState(...)`；测试 hook 只让 EditMode 构造后半段 `NodePath.Resolve` 失败，不替换 NodePath、PointerSimulator 或 InputSimulator。

```csharp
private static Func<string> playModeStateProvider = DeriveEditorState;

internal static void SetPlayModeStateProviderForTests(Func<string> provider)
{
    playModeStateProvider = provider ?? DeriveEditorState;
}

internal static void ResetForTests()
{
    playModeStateProvider = DeriveEditorState;
}
```

- [ ] **Step 6: 冻结响应兼容性**

在测试中对 click/set-value 成功形状的已有断言保留为：`JsonValue` 不含 `code`。失败结果继续是原 `BridgeResponse` 或既有 occluded `JsonValue`，不得为了审计统一而改为新 envelope。

- [ ] **Step 7: 跑失败路径测试**

Run:

```bash
UNITY_BIN="${UNITY_BIN:-/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity}" \
  ./scripts/run-unity-matrix.sh --set pr
```

Expected: PASS；每个调用审计恰好 `+1`。

- [ ] **Step 8: Commit**

```bash
git add packages/com.mk.unity-agent-bridge/Editor/Features/Interaction/InteractionController.cs packages/com.mk.unity-agent-bridge/Tests/Editor/Features/Interaction/InteractionControllerTests.cs
git commit -m "feat: audit every interaction controller result"
```

---

### Task 4: Controller 三条真实成功路径

**Files:**
- Modify: `packages/com.mk.unity-agent-bridge/Tests/Editor/UGUI/EditorIntegration/PointerSimulatorTests.cs:68-207`
- Modify: `packages/com.mk.unity-agent-bridge/Tests/Editor/UGUI/EditorIntegration/InputSimulatorTests.cs:78-170`

**Interfaces:**
- Consumes: Task 3 的真实 Controller 审计。
- Produces: PlayMode 自动化证明 click/input/set-value 成功返回均经过 Controller 和统一出口。

- [ ] **Step 1: 在 PointerSimulator 的单次 PlayMode 测试加入 Controller click**

不要新增第二次 `EnterPlayMode`。在已进入 Play Mode 的同一个 `UnityTest` 中创建 EventSystem、Canvas、Button，安装内存 audit sink，然后：

```csharp
string path = NodePath.BuildPath(button.transform);
object raw = InteractionController.Click(
    BridgeRequestContext.ForTests(
        rawBody: $"{{\"path\":\"{path}\",\"force\":false}}"));
JsonValue response = (JsonValue)raw;

Assert.IsTrue(response["ok"].AsBoolean);
Assert.IsFalse(response.ContainsKey("code"));
Assert.AreEqual(path, response["clicked"].AsString);
Assert.AreEqual(1, lines.Count);
JsonValue audit = JsonParser.Parse(lines[0]);
Assert.IsTrue(audit["ok"].AsBoolean);
Assert.AreEqual("ok", audit["code"].AsString);
Assert.AreEqual(path, audit["request"]["path"].AsString);
CollectionAssert.Contains(
    audit["events"].Items.ConvertAll(item => item.AsString),
    "pointerClick");
```

用 `try/finally` 重置 AuditLog hook 并销毁对象。

- [ ] **Step 2: 在 InputSimulator 的现有 PlayMode 会话加入 Controller input**

复用真实 EventSystem/InputField，body 的 text 使用可检索秘密值：

```csharp
const string secret = "controller-secret";
string path = NodePath.BuildPath(field.transform);
object raw = InteractionController.Input(
    BridgeRequestContext.ForTests(
        rawBody: $"{{\"path\":\"{path}\",\"text\":\"{secret}\",\"submit\":false}}"));

Assert.IsTrue(((BridgeResponse)raw).ok);
Assert.AreEqual("ok", ((BridgeResponse)raw).code);
Assert.AreEqual(secret, field.text);
Assert.AreEqual(1, lines.Count);
StringAssert.DoesNotContain(secret, lines[0]);
JsonValue audit = JsonParser.Parse(lines[0]);
Assert.AreEqual(secret.Length, audit["request"]["textLength"].AsInt);
```

- [ ] **Step 3: 在同一 PlayMode 会话加入 Controller set-value**

创建 active Slider，调用真实 Controller：

```csharp
string path = NodePath.BuildPath(slider.transform);
object raw = InteractionController.SetValue(
    BridgeRequestContext.ForTests(
        rawBody: $"{{\"path\":\"{path}\",\"value\":0.75}}"));
JsonValue response = (JsonValue)raw;

Assert.IsTrue(response["ok"].AsBoolean);
Assert.IsFalse(response.ContainsKey("code"));
Assert.AreEqual("Slider", response["component"].AsString);
Assert.AreEqual(0.75f, slider.value, 0.001f);
JsonValue audit = JsonParser.Parse(lines.Single());
Assert.AreEqual("ok", audit["code"].AsString);
Assert.AreEqual("Slider", audit["component"].AsString);
Assert.AreEqual("number", audit["request"]["valueKind"].AsString);
Assert.AreEqual(0.75, audit["request"]["value"].AsDouble, 0.001);
```

- [ ] **Step 4: 验证 appender 抛错不改变成功响应**

在其中一条真实成功路径把 appender 改为抛 `IOException("disk full")`，用 `LogAssert.Expect` 接收 Warning，随后继续断言控件已变化且响应仍成功。

- [ ] **Step 5: 跑 UGUI EditorIntegration**

Run:

```bash
UNITY_BIN="${UNITY_BIN:-/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity}" \
  ./scripts/run-unity-matrix.sh --set pr
```

Expected: PASS；只发生一轮 Enter/Exit Play Mode，无 EventSystem 状态污染。

- [ ] **Step 6: Commit**

```bash
git add packages/com.mk.unity-agent-bridge/Tests/Editor/UGUI/EditorIntegration/PointerSimulatorTests.cs packages/com.mk.unity-agent-bridge/Tests/Editor/UGUI/EditorIntegration/InputSimulatorTests.cs
git commit -m "test: verify controller success audit paths"
```

---

### Task 5: 自适应探索协议与文档

**Files:**
- Modify: `src/unityctl/unityctl/skill_assets/unityctl/SKILL.md:55-68`
- Modify: `src/unityctl/unityctl/skill_assets/unityctl/references/interaction.md:28-51`
- Modify: `src/unityctl/tests/test_skills.py:250-279`
- Modify: `docs/project-notes.md:99`
- Modify: `README.md:419-433`

**Interfaces:**
- Produces: Agent 可执行的自适应探索闭环和 L1/L2/L3 结论规则。
- Consumes: Task 1 的 schema 名称和 Task 2 的 artifact 文件名。

- [ ] **Step 1: 先扩展 skill 分发契约测试**

在 `test_real_assets_install` 中读取分发后的主 skill 与 interaction reference，并断言：

```python
assert "自适应 UI 探索" in content
assert "自适应探索闭环" in interaction_md
assert "三级证据" in interaction_md
assert "不能宣称" in interaction_md
assert "一次性长 shell/Python" in interaction_md
assert "interaction-actions.jsonl" in interaction_md
assert "local path=" in interaction_md
```

保留已有“禁止像素坐标”和 `path`/`instanceId` 断言。

- [ ] **Step 2: 运行并确认文案缺失**

Run:

```bash
cd src/unityctl && uv run pytest tests/test_skills.py::test_real_assets_install -q
```

Expected: FAIL，缺少新协议关键词。

- [ ] **Step 3: 在主 SKILL.md 增加入口**

把 UI 能力索引描述改为：

```markdown
| UI 操作、截图、动作录制、自适应 UI 探索 | `click` / `input` / `set-value` / `snapshot` / `record` | `references/interaction.md` |
```

主文件只做索引，不复制完整协议。

- [ ] **Step 4: 在 interaction.md 写单步闭环**

在“目标定位约束”之后新增：

```markdown
### 自适应探索闭环

未知流程或下一步依赖当前状态时，每一步必须：

1. 用 `hierarchy find` / `tree` / `inspect` 消歧为唯一 `path` 或 `instanceId`。
2. 直接执行一条 `unityctl ...`，不要把未知多步流程打包。
3. 保留完整 JSON 回执；需要复盘时对照当前 session 的
   `artifacts/interaction-actions.jsonl`（无 session 时位于 `.unity-agent/scratch/`）。
4. 用 hierarchy / gameplay / log 验证预期业务变化。
5. 必要时截图理解或复核画面，但不得由像素推导点击目标。
6. 根据验证结果再决策；`occluded` 时先读取并处理 `blockedBy`。

已知、稳定、可复跑的流程使用官方 `unityctl scenario`。
```

- [ ] **Step 5: 写三级证据和禁止项**

明确：

- L1：命令到达且未被参数/能力门拒绝，不能宣称成功；
- L2：click 的 `clicked/events`，或 input/set-value 对应 adapter 已接受并应用，仍不能宣称业务成功；
- L3：hierarchy/gameplay/log/snapshot 显示业务状态符合意图，才可宣称“界面已打开”等。

禁止项逐字覆盖：

- 未知探索使用一次性长 shell/Python；
- `|| true` 吞错；
- grep `"clicked"` 代替 JSON 语义；
- 无观测空等；
- 截图像素/欧氏距离选最近按钮；
- path 含 `[index]` 时不加引号；
- zsh 函数使用 `local path=`，因为会绑定并破坏 `PATH`。

- [ ] **Step 6: 更新 artifacts/schema 文档**

`docs/project-notes.md` 的 session artifacts 列表加入 `interaction-actions.jsonl`，说明它与手工录制 `actions.jsonl` 分离。README 的 schema 清单加入：

```text
schemas/interaction-actions.schema.json  # Bridge 交互命令产出的 interaction-actions.jsonl（逐行）
```

- [ ] **Step 7: 跑 skill 测试**

Run:

```bash
cd src/unityctl && uv run pytest tests/test_skills.py::test_real_assets_install -q
```

Expected: PASS。

- [ ] **Step 8: Commit**

```bash
git add src/unityctl/unityctl/skill_assets/unityctl/SKILL.md src/unityctl/unityctl/skill_assets/unityctl/references/interaction.md src/unityctl/tests/test_skills.py docs/project-notes.md README.md
git commit -m "docs: define reliable adaptive UI exploration"
```

---

### Task 6: 全量验证与契约核对

**Files:**
- Verify only; any fix must stay within files listed above unless a compiler error proves an adjacent generated/meta file is required.

**Interfaces:**
- Consumes: Tasks 1-5。
- Produces: 可复现的测试证据，不产生新功能。

- [ ] **Step 1: 运行 Python 全套测试**

Run:

```bash
cd src/unityctl && uv run pytest -q
```

Expected: PASS，无失败。

- [ ] **Step 2: 运行 Core/Features Editor 测试**

Run:

```bash
UNITY_BIN="${UNITY_BIN:-/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity}" \
  ./scripts/run-unity-matrix.sh --set pr
```

Expected: PASS，InteractionAuditLog/Controller 测试全部通过。

- [ ] **Step 3: 运行 UGUI EditorIntegration**

Run:

```bash
UNITY_BIN="${UNITY_BIN:-/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity}" \
  ./scripts/run-unity-matrix.sh --set pr
```

Expected: PASS，三个 Controller 成功路径均自动化覆盖。

- [ ] **Step 4: 运行项目全量测试**

Run:

```bash
./scripts/run-full-tests.sh
```

Expected: exit code 0。

- [ ] **Step 5: 检查敏感数据与响应冻结**

执行定向搜索：

```bash
rg -n '"text"\s*:' packages/com.mk.unity-agent-bridge/Editor/Features/Interaction/InteractionAuditLog.cs schemas/interaction-actions.schema.json
rg -n 'response\["code"\]' packages/com.mk.unity-agent-bridge/Editor/Features/Interaction/InteractionController.cs
```

Expected:

- 第一条只允许 schema 中用于禁止/描述的结构，不得发现把 input 原文写进 request 的实现；
- 第二条不得出现为 click/set-value 成功响应补 `code` 的代码。

- [ ] **Step 6: 核对改动范围**

Run:

```bash
git diff --check
git status --short
```

Expected: `git diff --check` 无输出；设计 spec 未修改；用户原有 `.codegraph/.gitignore` 改动保持不动且未误纳入本功能提交。

- [ ] **Step 7: 最终提交（仅在验证修复产生未提交改动时）**

```bash
git add schemas/interaction-actions.schema.json \
  src/unityctl/unityctl/schemas/interaction-actions.schema.json \
  src/unityctl/unityctl/config.py \
  src/unityctl/unityctl/skill_assets/unityctl/SKILL.md \
  src/unityctl/unityctl/skill_assets/unityctl/references/interaction.md \
  src/unityctl/tests/test_config.py \
  src/unityctl/tests/test_interaction_audit_schema.py \
  src/unityctl/tests/test_skills.py \
  packages/com.mk.unity-agent-bridge/Editor/Features/Interaction/InteractionAuditLog.cs \
  packages/com.mk.unity-agent-bridge/Editor/Features/Interaction/InteractionController.cs \
  packages/com.mk.unity-agent-bridge/Tests/Editor/Features/Interaction/InteractionAuditLogTests.cs \
  packages/com.mk.unity-agent-bridge/Tests/Editor/Features/Interaction/InteractionControllerTests.cs \
  packages/com.mk.unity-agent-bridge/Tests/Editor/UGUI/EditorIntegration/PointerSimulatorTests.cs \
  packages/com.mk.unity-agent-bridge/Tests/Editor/UGUI/EditorIntegration/InputSimulatorTests.cs \
  docs/project-notes.md README.md
git commit -m "fix: close interaction audit verification gaps"
```

若没有验证修复，不创建空提交。

---

## Acceptance Checklist

- [ ] 三个 Controller 入口的每个结构化返回恰好写一条审计。
- [ ] 缺 path、not_in_play_mode、node_not_found 和三条真实成功路径均自动化覆盖。
- [ ] click/set-value 成功 HTTP/CLI 响应不新增 `code`。
- [ ] input 秘密原文、set-value 字符串/未知值不落盘。
- [ ] 写盘失败只产生 Warning，原成功/失败响应不变。
- [ ] session 使用 `artifacts/interaction-actions.jsonl`，无 session 使用 scratch。
- [ ] 两份 schema 完全一致，init 可分发，正反例契约通过。
- [ ] skill 明确单步闭环、三级证据、禁止像素猜测、禁止长脚本及 zsh `path` 陷阱。
- [ ] Python、Features、UGUI EditorIntegration 和 `run-full-tests.sh` 全部通过。
