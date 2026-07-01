# Unity Runtime Observability 实现计划

> **给 agentic worker 的要求：** 实施本计划时必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`。所有步骤都使用 checkbox（`- [ ]`）格式，方便逐项跟踪。

**目标：** 在 Unity Editor Control 的基础上增加 session-based 运行观测能力，让外部 agent 可以为每次 PlayMode 运行创建 session，持续落盘 Unity Console 日志，并生成可审计的 `summary.json`。

**架构：** CLI 负责创建 session 目录、写入 `session.json`、调用 Bridge 开始/结束 session，并在运行结束后读取 `unity-console.jsonl` 生成 `summary.json`。Bridge 只负责接收 CLI 指定的 session 路径，捕获 Unity `Application.logMessageReceived`，把结构化日志 append 到 session 目录。文件系统是最终事实来源，HTTP 和 CLI 查询只是便捷视图。

**技术栈：** Unity Editor C# UPM package、`Application.logMessageReceived`、`EditorApplication`、`EditorSceneManager`、JSON Lines、Python 3.11+、`uv`、`argparse`、`urllib.request`、`pytest`。

---

## 前置条件

先完成并合入第一部分计划：

- `docs/superpowers/plans/2026-06-30-unity-editor-control.md`

本计划假设以下文件已经存在：

- `src/unityctl/unityctl/client.py`
- `src/unityctl/unityctl/cli.py`
- `src/unityctl/unityctl/editor.py`
- `packages/com.elex.unity-agent-bridge/Editor/BridgeResponse.cs`
- `packages/com.elex.unity-agent-bridge/Editor/BridgeServer.cs`
- `packages/com.elex.unity-agent-bridge/Editor/EditorStateProvider.cs`

## 范围

本计划覆盖：

- CLI 创建 session 目录
- `session.json`
- Bridge session start/end/status
- Bridge 捕获 Unity Console log
- `unity-console.jsonl`
- CLI 生成 `summary.json`
- `.unity-agent/log-rules.json` 的 `ignore` 规则
- `unityctl logs`
- `unityctl errors`
- `unityctl summary`

本计划不覆盖：

- 截图
- UI tree
- 游戏内状态结构化
- MCP tools
- 多 Unity project discovery
- WebSocket 实时日志流
- 完整 git metadata
- 完整 diff 归档

## 数据约定

Session 目录由 CLI 创建：

```text
<ProjectRoot>/.unity-agent/sessions/<sessionId>/
  session.json
  unity-console.jsonl
  summary.json
```

`session.json` 第一版不包含 `branch`、`commit`、`diff`：

```json
{
  "sessionId": "2026-06-30_183012_login-flow",
  "name": "login-flow",
  "projectPath": "/path/to/unity/project",
  "scenePath": "Assets/Scenes/Login.unity",
  "createdAt": "2026-06-30T18:30:12.123Z",
  "startedAt": null,
  "endedAt": null,
  "status": "created",
  "trigger": "agent",
  "task": "verify login flow after code changes"
}
```

`unity-console.jsonl` 每行一条日志：

```json
{"time":"2026-06-30T18:30:14.001Z","sequence":12,"type":"Exception","message":"NullReferenceException...","stackTrace":"...","isPlayMode":true,"playModeFrame":356,"scenePath":"Assets/Scenes/Login.unity"}
```

`playModeFrame` 约定：

- PlayMode 中写入 `Time.frameCount`。
- 非 PlayMode 中写入 `-1`。这是因为 Unity `JsonUtility` 不支持 nullable int；下游展示时可以把 `-1` 显示为 `null` 或 `not_in_play_mode`。

`summary.json` 使用 `status`，不把所有 `Error` 都直接判成失败：

```json
{
  "status": "problem_detected",
  "hasProblems": true,
  "hasBlockingProblems": false,
  "logCount": 128,
  "warningCount": 3,
  "errorCount": 2,
  "exceptionCount": 0,
  "assertCount": 0,
  "ignoredProblemCount": 1,
  "blockingProblemCount": 0,
  "lastProblem": {
    "type": "Error",
    "message": "Asset load failed...",
    "severity": "problem",
    "sequence": 87,
    "playModeFrame": 356,
    "scenePath": "Assets/Scenes/Login.unity"
  },
  "startedAt": "2026-06-30T18:30:12.123Z",
  "endedAt": "2026-06-30T18:31:02.456Z",
  "durationMs": 50333
}
```

默认判定规则：

```text
Log       -> ignored
Warning   -> counted
Error     -> problem
Exception -> blocking
Assert    -> blocking
```

`status` 计算规则：

```text
blockingProblemCount > 0 -> failed
blockingProblemCount == 0 && problemCount > 0 -> problem_detected
problemCount == 0 -> passed
```

`.unity-agent/log-rules.json` 第一版只支持 `ignore`：

```json
{
  "ignore": [
    {
      "type": "Error",
      "messageContains": "Expected test error"
    }
  ]
}
```

## 文件结构

新增文件：

- `src/unityctl/unityctl/session.py`  
  创建 session id、session 目录和 `session.json`。
- `src/unityctl/unityctl/summary.py`  
  读取 `unity-console.jsonl` 和 `.unity-agent/log-rules.json`，生成 `summary.json`。
- `src/unityctl/tests/test_session.py`  
  Python session 创建测试。
- `src/unityctl/tests/test_summary.py`  
  Python summary 和 ignore rule 测试。
- `packages/com.elex.unity-agent-bridge/Editor/SessionController.cs`  
  Bridge 内部当前 session 状态、路径校验、start/end/status。
- `packages/com.elex.unity-agent-bridge/Editor/SessionLogWriter.cs`  
  捕获 Unity logs 并写入 `unity-console.jsonl`。
- `packages/com.elex.unity-agent-bridge/Tests/Editor/SessionControllerTests.cs`  
  Unity EditMode path validation tests。

修改文件：

- `src/unityctl/unityctl/client.py`  
  增加 session HTTP methods。
- `src/unityctl/unityctl/cli.py`  
  增加 `play --session`、`stop` summary 生成、`logs/errors/summary` 查询。
- `src/unityctl/tests/test_client.py`  
  增加 session client tests。
- `src/unityctl/tests/test_cli.py`  
  增加 session CLI tests。
- `packages/com.elex.unity-agent-bridge/Editor/BridgeResponse.cs`  
  增加 session request/response DTO。
- `packages/com.elex.unity-agent-bridge/Editor/BridgeServer.cs`  
  增加 `/session/start`、`/session/end`、`/session/status` routes。
- `packages/com.elex.unity-agent-bridge/Editor/EditorStateProvider.cs`  
  在 `/status` 中返回当前 session 信息。
- `README.md`  
  增加运行观测说明。

## Task 1: 添加 Python Session 创建能力

**Files:**
- Create: `src/unityctl/unityctl/session.py`
- Create: `src/unityctl/tests/test_session.py`

- [ ] **Step 1: 编写失败的 session tests**

创建 `src/unityctl/tests/test_session.py`：

```python
import json
from datetime import datetime, timezone

from unityctl.session import create_session, make_session_id


def test_make_session_id_normalizes_name():
    created_at = datetime(2026, 6, 30, 18, 30, 12, tzinfo=timezone.utc)

    assert make_session_id("Login Flow!", created_at) == "2026-06-30_183012_login-flow"


def test_create_session_writes_session_json(tmp_path):
    project = tmp_path / "Game"
    project.mkdir()
    created_at = datetime(2026, 6, 30, 18, 30, 12, tzinfo=timezone.utc)

    session = create_session(
        project_path=project,
        name="login-flow",
        scene_path="Assets/Scenes/Login.unity",
        trigger="agent",
        task="verify login flow",
        created_at=created_at,
    )

    assert session.session_id == "2026-06-30_183012_login-flow"
    assert session.session_path == project / ".unity-agent" / "sessions" / "2026-06-30_183012_login-flow"
    assert session.session_json_path.exists()

    payload = json.loads(session.session_json_path.read_text(encoding="utf-8"))
    assert payload == {
        "sessionId": "2026-06-30_183012_login-flow",
        "name": "login-flow",
        "projectPath": str(project),
        "scenePath": "Assets/Scenes/Login.unity",
        "createdAt": "2026-06-30T18:30:12Z",
        "startedAt": None,
        "endedAt": None,
        "status": "created",
        "trigger": "agent",
        "task": "verify login flow",
    }
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests/test_session.py -v
```

预期：测试失败，错误包含 `ModuleNotFoundError: No module named 'unityctl.session'`。

- [ ] **Step 3: 实现 session 创建**

创建 `src/unityctl/unityctl/session.py`：

```python
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SessionPaths:
    session_id: str
    session_path: Path
    session_json_path: Path
    console_log_path: Path
    summary_json_path: Path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_time(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc).replace(microsecond=0)
    return normalized.isoformat().replace("+00:00", "Z")


def make_session_id(name: str, created_at: datetime) -> str:
    stamp = created_at.astimezone(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        slug = "session"
    return f"{stamp}_{slug}"


def create_session(
    project_path: str | Path,
    name: str,
    scene_path: str | None,
    trigger: str,
    task: str,
    created_at: datetime | None = None,
) -> SessionPaths:
    created = created_at or utc_now()
    project = Path(project_path).expanduser().resolve()
    session_id = make_session_id(name, created)
    session_path = project / ".unity-agent" / "sessions" / session_id
    session_path.mkdir(parents=True, exist_ok=False)

    payload: dict[str, Any] = {
        "sessionId": session_id,
        "name": name,
        "projectPath": str(project),
        "scenePath": scene_path,
        "createdAt": format_time(created),
        "startedAt": None,
        "endedAt": None,
        "status": "created",
        "trigger": trigger,
        "task": task,
    }

    session_json_path = session_path / "session.json"
    session_json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return SessionPaths(
        session_id=session_id,
        session_path=session_path,
        session_json_path=session_json_path,
        console_log_path=session_path / "unity-console.jsonl",
        summary_json_path=session_path / "summary.json",
    )


def read_session_json(session_path: str | Path) -> dict[str, Any]:
    path = Path(session_path).expanduser().resolve() / "session.json"
    return json.loads(path.read_text(encoding="utf-8"))


def write_session_json(session_path: str | Path, payload: dict[str, Any]) -> None:
    path = Path(session_path).expanduser().resolve() / "session.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_session_status(
    session_path: str | Path,
    status: str,
    started_at: str | None = None,
    ended_at: str | None = None,
) -> dict[str, Any]:
    payload = read_session_json(session_path)
    payload["status"] = status
    if started_at is not None:
        payload["startedAt"] = started_at
    if ended_at is not None:
        payload["endedAt"] = ended_at
    write_session_json(session_path, payload)
    return payload
```

- [ ] **Step 4: 运行 session tests**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests/test_session.py -v
```

预期：`2 passed`。

- [ ] **Step 5: 提交**

Run:

```bash
git add src/unityctl/unityctl/session.py src/unityctl/tests/test_session.py
git commit -m "feat: add unity run sessions"
```

预期：commit 成功。

## Task 2: 添加 Summary 与 Ignore Rules

**Files:**
- Create: `src/unityctl/unityctl/summary.py`
- Create: `src/unityctl/tests/test_summary.py`

- [ ] **Step 1: 编写失败的 summary tests**

创建 `src/unityctl/tests/test_summary.py`：

```python
import json

from unityctl.summary import build_summary, load_log_rules


def write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_build_summary_marks_exception_as_failed(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    (session / "session.json").write_text(
        json.dumps(
            {
                "startedAt": "2026-06-30T18:30:12Z",
                "endedAt": "2026-06-30T18:31:02Z",
            }
        ),
        encoding="utf-8",
    )
    write_jsonl(
        session / "unity-console.jsonl",
        [
            {"sequence": 1, "type": "Log", "message": "ready", "playModeFrame": 1, "scenePath": "Assets/A.unity"},
            {"sequence": 2, "type": "Exception", "message": "NullReferenceException", "playModeFrame": 3, "scenePath": "Assets/A.unity"},
        ],
    )

    summary = build_summary(session, rules={"ignore": []})

    assert summary["status"] == "failed"
    assert summary["hasProblems"] is True
    assert summary["hasBlockingProblems"] is True
    assert summary["logCount"] == 2
    assert summary["exceptionCount"] == 1
    assert summary["blockingProblemCount"] == 1
    assert summary["lastProblem"]["message"] == "NullReferenceException"
    assert summary["durationMs"] == 50000


def test_error_without_blocking_rule_is_problem_detected(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    (session / "session.json").write_text(
        json.dumps({"startedAt": None, "endedAt": None}),
        encoding="utf-8",
    )
    write_jsonl(
        session / "unity-console.jsonl",
        [
            {"sequence": 1, "type": "Error", "message": "Expected test error", "playModeFrame": 5, "scenePath": "Assets/A.unity"}
        ],
    )

    summary = build_summary(session, rules={"ignore": []})

    assert summary["status"] == "problem_detected"
    assert summary["hasProblems"] is True
    assert summary["hasBlockingProblems"] is False
    assert summary["errorCount"] == 1
    assert summary["blockingProblemCount"] == 0


def test_ignore_rule_removes_expected_error_from_problem_count(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    (session / "session.json").write_text(
        json.dumps({"startedAt": None, "endedAt": None}),
        encoding="utf-8",
    )
    write_jsonl(
        session / "unity-console.jsonl",
        [
            {"sequence": 1, "type": "Error", "message": "Expected test error", "playModeFrame": 5, "scenePath": "Assets/A.unity"}
        ],
    )

    summary = build_summary(
        session,
        rules={"ignore": [{"type": "Error", "messageContains": "Expected test error"}]},
    )

    assert summary["status"] == "passed"
    assert summary["hasProblems"] is False
    assert summary["ignoredProblemCount"] == 1


def test_load_log_rules_returns_empty_ignore_when_file_missing(tmp_path):
    assert load_log_rules(tmp_path) == {"ignore": []}
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests/test_summary.py -v
```

预期：测试失败，错误包含 `ModuleNotFoundError: No module named 'unityctl.summary'`。

- [ ] **Step 3: 实现 summary 生成**

创建 `src/unityctl/unityctl/summary.py`：

```python
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROBLEM_TYPES = {"Error"}
BLOCKING_TYPES = {"Exception", "Assert"}


def load_log_rules(project_path: str | Path) -> dict[str, list[dict[str, str]]]:
    rules_path = Path(project_path).expanduser().resolve() / ".unity-agent" / "log-rules.json"
    if not rules_path.exists():
        return {"ignore": []}
    payload = json.loads(rules_path.read_text(encoding="utf-8"))
    ignore = payload.get("ignore", [])
    if not isinstance(ignore, list):
        return {"ignore": []}
    return {"ignore": [rule for rule in ignore if isinstance(rule, dict)]}


def build_summary(
    session_path: str | Path,
    rules: dict[str, list[dict[str, str]]] | None = None,
) -> dict[str, Any]:
    session = Path(session_path).expanduser().resolve()
    rule_payload = rules or {"ignore": []}
    logs = read_jsonl(session / "unity-console.jsonl")
    session_payload = read_json(session / "session.json")

    counts = {
        "Log": 0,
        "Warning": 0,
        "Error": 0,
        "Exception": 0,
        "Assert": 0,
    }
    ignored_problem_count = 0
    problem_count = 0
    blocking_problem_count = 0
    last_problem = None

    for row in logs:
        log_type = str(row.get("type", "Log"))
        if log_type in counts:
            counts[log_type] += 1

        severity = classify_log(row, rule_payload)
        if severity == "ignored_problem":
            ignored_problem_count += 1
            continue
        if severity == "problem":
            problem_count += 1
            last_problem = problem_payload(row, "problem")
        if severity == "blocking":
            problem_count += 1
            blocking_problem_count += 1
            last_problem = problem_payload(row, "blocking")

    if blocking_problem_count > 0:
        status = "failed"
    elif problem_count > 0:
        status = "problem_detected"
    else:
        status = "passed"

    started_at = session_payload.get("startedAt")
    ended_at = session_payload.get("endedAt")

    return {
        "status": status,
        "hasProblems": problem_count > 0,
        "hasBlockingProblems": blocking_problem_count > 0,
        "logCount": len(logs),
        "warningCount": counts["Warning"],
        "errorCount": counts["Error"],
        "exceptionCount": counts["Exception"],
        "assertCount": counts["Assert"],
        "ignoredProblemCount": ignored_problem_count,
        "blockingProblemCount": blocking_problem_count,
        "lastProblem": last_problem,
        "startedAt": started_at,
        "endedAt": ended_at,
        "durationMs": duration_ms(started_at, ended_at),
    }


def write_summary(session_path: str | Path, summary: dict[str, Any]) -> Path:
    path = Path(session_path).expanduser().resolve() / "summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def classify_log(row: dict[str, Any], rules: dict[str, list[dict[str, str]]]) -> str:
    log_type = str(row.get("type", "Log"))
    if log_type not in PROBLEM_TYPES and log_type not in BLOCKING_TYPES:
        return "normal"
    if matches_ignore(row, rules.get("ignore", [])):
        return "ignored_problem"
    if log_type in BLOCKING_TYPES:
        return "blocking"
    return "problem"


def matches_ignore(row: dict[str, Any], ignore_rules: list[dict[str, str]]) -> bool:
    log_type = str(row.get("type", ""))
    message = str(row.get("message", ""))
    for rule in ignore_rules:
        expected_type = rule.get("type")
        message_contains = rule.get("messageContains")
        if expected_type and expected_type != log_type:
            continue
        if message_contains and message_contains not in message:
            continue
        return True
    return False


def problem_payload(row: dict[str, Any], severity: str) -> dict[str, Any]:
    return {
        "type": row.get("type"),
        "message": row.get("message"),
        "severity": severity,
        "sequence": row.get("sequence"),
        "playModeFrame": row.get("playModeFrame"),
        "scenePath": row.get("scenePath"),
    }


def duration_ms(started_at: str | None, ended_at: str | None) -> int | None:
    if not started_at or not ended_at:
        return None
    start = parse_time(started_at)
    end = parse_time(ended_at)
    return int((end - start).total_seconds() * 1000)


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
```

- [ ] **Step 4: 运行 summary tests**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests/test_summary.py -v
```

预期：`4 passed`。

- [ ] **Step 5: 提交**

Run:

```bash
git add src/unityctl/unityctl/summary.py src/unityctl/tests/test_summary.py
git commit -m "feat: summarize unity session logs"
```

预期：commit 成功。

## Task 3: 扩展 Python Client 与 CLI Session Commands

**Files:**
- Modify: `src/unityctl/unityctl/client.py`
- Modify: `src/unityctl/unityctl/cli.py`
- Modify: `src/unityctl/tests/test_client.py`
- Modify: `src/unityctl/tests/test_cli.py`

- [ ] **Step 1: 添加失败的 client session tests**

在 `src/unityctl/tests/test_client.py` 末尾追加：

```python

def test_start_session_posts_session_payload(monkeypatch):
    captured_body = []

    def fake_urlopen(request, timeout):
        captured_body.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(200, {"ok": True, "sessionId": "s1"})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890")
    result = client.start_session("s1", "/tmp/project/.unity-agent/sessions/s1")

    assert result == {"ok": True, "sessionId": "s1"}
    assert captured_body == [
        {"sessionId": "s1", "sessionPath": "/tmp/project/.unity-agent/sessions/s1"}
    ]


def test_end_session_posts_empty_payload(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, request.get_method(), request.data))
        return FakeResponse(200, {"ok": True, "message": "session ended"})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890")
    result = client.end_session()

    assert result == {"ok": True, "message": "session ended"}
    assert calls == [("http://127.0.0.1:17890/session/end", "POST", b"{}")]
```

- [ ] **Step 2: 运行 client tests 并确认失败**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests/test_client.py -v
```

预期：新增 tests 失败，原因是 `BridgeClient` 没有 `start_session` 和 `end_session`。

- [ ] **Step 3: 修改 client**

在 `src/unityctl/unityctl/client.py` 的 `BridgeClient` class 内添加：

```python
    def start_session(self, session_id: str, session_path: str) -> dict[str, Any]:
        return self.post(
            "session/start",
            {
                "sessionId": session_id,
                "sessionPath": session_path,
            },
        )

    def end_session(self) -> dict[str, Any]:
        return self.post("session/end")

    def get_session_status(self) -> dict[str, Any]:
        return self.get("session/status")
```

- [ ] **Step 4: 运行 client tests**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests/test_client.py -v
```

预期：`6 passed`。

- [ ] **Step 5: 添加失败的 CLI session tests**

在 `src/unityctl/tests/test_cli.py` 末尾追加：

```python

def test_play_with_session_creates_session_and_starts_bridge(monkeypatch, tmp_path, capsys):
    clients = []

    def fake_client(base_url):
        client = FakeClient(base_url)
        client.start_session = lambda session_id, session_path: client.calls.append(("session/start", {"sessionId": session_id, "sessionPath": session_path})) or {"ok": True}
        clients.append(client)
        return client

    monkeypatch.setattr(cli, "BridgeClient", fake_client)
    monkeypatch.setattr(cli, "utc_now", lambda: cli.datetime.fromisoformat("2026-06-30T18:30:12+00:00"))

    project = tmp_path / "Game"
    project.mkdir()

    exit_code = cli.main([
        "play",
        "--project",
        str(project),
        "--session",
        "login-flow",
        "--scene",
        "Assets/Scenes/Login.unity",
        "--task",
        "verify login flow",
    ])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["sessionId"] == "2026-06-30_183012_login-flow"
    assert (project / ".unity-agent" / "sessions" / "2026-06-30_183012_login-flow" / "session.json").exists()
    assert clients[0].calls[0][0] == "session/start"
    assert clients[0].calls[1] == ("play", None)


def test_summary_command_prints_summary_file(tmp_path, capsys):
    session = tmp_path / "s1"
    session.mkdir()
    (session / "summary.json").write_text('{"status":"passed"}', encoding="utf-8")

    exit_code = cli.main(["summary", "--session-path", str(session)])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"status": "passed"}
```

- [ ] **Step 6: 运行 CLI tests 并确认失败**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests/test_cli.py -v
```

预期：新增 tests 失败，原因是 CLI 还不支持 `play --session` 和 `summary`。

- [ ] **Step 7: 修改 CLI imports**

在 `src/unityctl/unityctl/cli.py` 顶部 imports 调整为：

```python
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from unityctl.client import BridgeClient, BridgeClientError
from unityctl.editor import start_editor
from unityctl.session import create_session, format_time, update_session_status, utc_now
from unityctl.summary import build_summary, load_log_rules, read_jsonl, write_summary
```

- [ ] **Step 8: 修改 CLI parser**

在 `build_parser()` 中替换原来的 `play` 和 `stop` parser 定义，并增加查询命令：

```python
    play = subparsers.add_parser("play")
    play.add_argument("--project", dest="project_path")
    play.add_argument("--session", dest="session_name")
    play.add_argument("--scene", dest="scene_path")
    play.add_argument("--task", default="")
    play.add_argument("--trigger", default="agent")

    stop = subparsers.add_parser("stop")
    stop.add_argument("--session-path")
    stop.add_argument("--project")

    logs = subparsers.add_parser("logs")
    logs.add_argument("--session-path", required=True)
    logs.add_argument("--limit", type=int, default=100)

    errors = subparsers.add_parser("errors")
    errors.add_argument("--session-path", required=True)

    summary = subparsers.add_parser("summary")
    summary.add_argument("--session-path", required=True)
```

- [ ] **Step 9: 修改 CLI command handling**

在 `main()` 中替换 `play`、`stop` 分支，并增加 `logs/errors/summary` 分支：

```python
        if args.command == "play":
            client = BridgeClient(args.base_url)
            if args.session_name:
                if not args.project_path:
                    raise ValueError("--project is required when --session is used")
                session = create_session(
                    project_path=args.project_path,
                    name=args.session_name,
                    scene_path=args.scene_path,
                    trigger=args.trigger,
                    task=args.task,
                    created_at=utc_now(),
                )
                started_at = format_time(utc_now())
                update_session_status(session.session_path, "running", started_at=started_at)
                client.start_session(session.session_id, str(session.session_path))
                play_response = client.post("play")
                print_json(
                    {
                        "ok": bool(play_response.get("ok", False)),
                        "sessionId": session.session_id,
                        "sessionPath": str(session.session_path),
                        "play": play_response,
                    }
                )
                return 0
            print_json(client.post("play"))
            return 0

        if args.command == "stop":
            client = BridgeClient(args.base_url)
            stop_response = client.post("stop")
            end_response = client.end_session()
            payload = {"ok": bool(stop_response.get("ok", False)), "stop": stop_response, "sessionEnd": end_response}
            if args.session_path:
                ended_at = format_time(utc_now())
                update_session_status(args.session_path, "stopped", ended_at=ended_at)
                project_for_rules = args.project or Path(args.session_path).parents[2]
                summary_payload = build_summary(args.session_path, load_log_rules(project_for_rules))
                write_summary(args.session_path, summary_payload)
                payload["summary"] = summary_payload
            print_json(payload)
            return 0

        if args.command == "logs":
            rows = read_jsonl(Path(args.session_path) / "unity-console.jsonl")
            print_json({"ok": True, "logs": rows[-args.limit :]})
            return 0

        if args.command == "errors":
            rows = read_jsonl(Path(args.session_path) / "unity-console.jsonl")
            problems = [row for row in rows if row.get("type") in {"Error", "Exception", "Assert"}]
            print_json({"ok": True, "errors": problems})
            return 0

        if args.command == "summary":
            summary_path = Path(args.session_path) / "summary.json"
            print(summary_path.read_text(encoding="utf-8"), end="")
            return 0
```

- [ ] **Step 10: 运行 CLI tests**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests/test_cli.py -v
```

预期：所有 CLI tests 通过。

- [ ] **Step 11: 运行全部 Python tests**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests -v
```

预期：全部 Python tests 通过。

- [ ] **Step 12: 提交**

Run:

```bash
git add src/unityctl/unityctl/client.py src/unityctl/unityctl/cli.py src/unityctl/tests/test_client.py src/unityctl/tests/test_cli.py
git commit -m "feat: add session cli commands"
```

预期：commit 成功。

## Task 4: 添加 Unity Session Controller 与 Log Writer

**Files:**
- Create: `packages/com.elex.unity-agent-bridge/Editor/SessionController.cs`
- Create: `packages/com.elex.unity-agent-bridge/Editor/SessionLogWriter.cs`
- Create: `packages/com.elex.unity-agent-bridge/Tests/Editor/SessionControllerTests.cs`
- Modify: `packages/com.elex.unity-agent-bridge/Editor/BridgeResponse.cs`

- [ ] **Step 1: 编写失败的 SessionController tests**

创建 `packages/com.elex.unity-agent-bridge/Tests/Editor/SessionControllerTests.cs`：

```csharp
using NUnit.Framework;

namespace Elex.UnityAgentBridge.Editor.Tests
{
    public sealed class SessionControllerTests
    {
        [Test]
        public void IsAllowedSessionPath_AcceptsProjectUnityAgentSessionPath()
        {
            string projectPath = "/tmp/Game";
            string sessionPath = "/tmp/Game/.unity-agent/sessions/session-1";

            Assert.IsTrue(SessionController.IsAllowedSessionPath(projectPath, sessionPath));
        }

        [Test]
        public void IsAllowedSessionPath_RejectsPathOutsideProject()
        {
            string projectPath = "/tmp/Game";
            string sessionPath = "/tmp/Other/.unity-agent/sessions/session-1";

            Assert.IsFalse(SessionController.IsAllowedSessionPath(projectPath, sessionPath));
        }
    }
}
```

- [ ] **Step 2: 运行 Unity EditMode tests 并确认失败**

在已引用 `packages/com.elex.unity-agent-bridge` 的 Unity project 中运行：

```bash
"${UNITY_BIN:?set UNITY_BIN}" -batchmode -projectPath "${UNITY_PROJECT:?set UNITY_PROJECT}" -runTests -testPlatform EditMode -testResults "/tmp/unity-agent-bridge-editmode.xml" -quit
```

预期：测试编译失败，原因是 `SessionController` 未定义。

- [ ] **Step 3: 扩展 Bridge DTO**

在 `packages/com.elex.unity-agent-bridge/Editor/BridgeResponse.cs` 中，把下面的 DTO 插入到 `namespace Elex.UnityAgentBridge.Editor` 内部，位置放在 `OpenSceneRequest` 后、namespace 结束的 `}` 前：

```csharp

    [Serializable]
    public sealed class SessionStartRequest
    {
        public string sessionId;
        public string sessionPath;
    }

    [Serializable]
    public sealed class SessionStartResponse : BridgeResponse
    {
        public string sessionId;
        public string sessionPath;
        public string logPath;
    }

    [Serializable]
    public sealed class SessionStatusResponse : BridgeResponse
    {
        public bool hasActiveSession;
        public string sessionId;
        public string sessionPath;
        public string logPath;
    }
```

- [ ] **Step 4: 创建 SessionLogWriter**

创建 `packages/com.elex.unity-agent-bridge/Editor/SessionLogWriter.cs`：

```csharp
using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Elex.UnityAgentBridge.Editor
{
    internal sealed class SessionLogWriter : IDisposable
    {
        private readonly StreamWriter writer;
        private int sequence;

        public string LogPath { get; }

        public SessionLogWriter(string logPath)
        {
            LogPath = logPath;
            Directory.CreateDirectory(Path.GetDirectoryName(logPath));
            writer = new StreamWriter(new FileStream(logPath, FileMode.Append, FileAccess.Write, FileShare.ReadWrite));
            writer.AutoFlush = true;
        }

        public void Write(string condition, string stackTrace, LogType type)
        {
            sequence += 1;
            SessionLogEntry entry = new SessionLogEntry
            {
                time = DateTime.UtcNow.ToString("o"),
                sequence = sequence,
                type = type.ToString(),
                message = condition ?? string.Empty,
                stackTrace = stackTrace ?? string.Empty,
                isPlayMode = EditorApplication.isPlaying,
                playModeFrame = EditorApplication.isPlaying ? Time.frameCount : -1,
                scenePath = EditorSceneManager.GetActiveScene().path ?? string.Empty
            };
            writer.WriteLine(JsonUtility.ToJson(entry));
        }

        public void Dispose()
        {
            writer.Flush();
            writer.Dispose();
        }

        [Serializable]
        private sealed class SessionLogEntry
        {
            public string time;
            public int sequence;
            public string type;
            public string message;
            public string stackTrace;
            public bool isPlayMode;
            public int playModeFrame;
            public string scenePath;
        }
    }
}
```

说明：Unity `JsonUtility` 不支持 nullable int。第一版用 `playModeFrame = -1` 表示非 PlayMode，CLI 或下游读取时可以把 `-1` 解释为 `null`。

- [ ] **Step 5: 创建 SessionController**

创建 `packages/com.elex.unity-agent-bridge/Editor/SessionController.cs`：

```csharp
using System;
using System.IO;
using UnityEngine;

namespace Elex.UnityAgentBridge.Editor
{
    internal static class SessionController
    {
        private static string currentSessionId = string.Empty;
        private static string currentSessionPath = string.Empty;
        private static SessionLogWriter logWriter;

        public static bool HasActiveSession => logWriter != null;
        public static string CurrentSessionId => currentSessionId;
        public static string CurrentSessionPath => currentSessionPath;
        public static string CurrentLogPath => logWriter == null ? string.Empty : logWriter.LogPath;

        public static BridgeResponse StartSession(string sessionId, string sessionPath)
        {
            if (string.IsNullOrWhiteSpace(sessionId))
            {
                return BridgeResponse.Failure("sessionId is required");
            }

            string projectRoot = GetProjectRoot();
            if (!IsAllowedSessionPath(projectRoot, sessionPath))
            {
                return BridgeResponse.Failure("sessionPath must be under <ProjectRoot>/.unity-agent/sessions");
            }

            EndSession();

            currentSessionId = sessionId;
            currentSessionPath = Path.GetFullPath(sessionPath);
            string logPath = Path.Combine(currentSessionPath, "unity-console.jsonl");
            logWriter = new SessionLogWriter(logPath);
            Application.logMessageReceived += OnLogMessageReceived;

            return new SessionStartResponse
            {
                ok = true,
                message = "session started",
                error = string.Empty,
                sessionId = currentSessionId,
                sessionPath = currentSessionPath,
                logPath = CurrentLogPath
            };
        }

        public static BridgeResponse EndSession()
        {
            if (logWriter == null)
            {
                currentSessionId = string.Empty;
                currentSessionPath = string.Empty;
                return BridgeResponse.Success("no active session");
            }

            Application.logMessageReceived -= OnLogMessageReceived;
            logWriter.Dispose();
            logWriter = null;
            currentSessionId = string.Empty;
            currentSessionPath = string.Empty;
            return BridgeResponse.Success("session ended");
        }

        public static SessionStatusResponse GetStatus()
        {
            return new SessionStatusResponse
            {
                ok = true,
                message = HasActiveSession ? "session active" : "no active session",
                error = string.Empty,
                hasActiveSession = HasActiveSession,
                sessionId = currentSessionId,
                sessionPath = currentSessionPath,
                logPath = CurrentLogPath
            };
        }

        public static bool IsAllowedSessionPath(string projectPath, string sessionPath)
        {
            if (string.IsNullOrWhiteSpace(projectPath) || string.IsNullOrWhiteSpace(sessionPath))
            {
                return false;
            }

            string projectFullPath = Normalize(Path.GetFullPath(projectPath));
            string sessionFullPath = Normalize(Path.GetFullPath(sessionPath));
            string allowedRoot = Normalize(Path.Combine(projectFullPath, ".unity-agent", "sessions"));
            return sessionFullPath.StartsWith(allowedRoot + "/", StringComparison.Ordinal);
        }

        private static void OnLogMessageReceived(string condition, string stackTrace, LogType type)
        {
            logWriter?.Write(condition, stackTrace, type);
        }

        private static string GetProjectRoot()
        {
            DirectoryInfo assetsDirectory = new DirectoryInfo(Application.dataPath);
            return assetsDirectory.Parent == null ? string.Empty : assetsDirectory.Parent.FullName;
        }

        private static string Normalize(string path)
        {
            return path.Replace('\\', '/').TrimEnd('/');
        }
    }
}
```

- [ ] **Step 6: 运行 Unity EditMode tests**

Run:

```bash
"${UNITY_BIN:?set UNITY_BIN}" -batchmode -projectPath "${UNITY_PROJECT:?set UNITY_PROJECT}" -runTests -testPlatform EditMode -testResults "/tmp/unity-agent-bridge-editmode.xml" -quit
```

预期：`SessionControllerTests` 通过。

- [ ] **Step 7: 提交**

Run:

```bash
git add packages/com.elex.unity-agent-bridge/Editor/BridgeResponse.cs packages/com.elex.unity-agent-bridge/Editor/SessionController.cs packages/com.elex.unity-agent-bridge/Editor/SessionLogWriter.cs packages/com.elex.unity-agent-bridge/Tests/Editor/SessionControllerTests.cs
git commit -m "feat: capture unity logs for sessions"
```

预期：commit 成功。

## Task 5: 增加 Bridge Session Routes

**Files:**
- Modify: `packages/com.elex.unity-agent-bridge/Editor/BridgeServer.cs`
- Modify: `packages/com.elex.unity-agent-bridge/Editor/EditorStateProvider.cs`

- [ ] **Step 1: 修改 BridgeServer routes**

在 `packages/com.elex.unity-agent-bridge/Editor/BridgeServer.cs` 的 `Route(HttpListenerRequest request)` 中，在 `/open-scene` 分支之后、unsupported route 之前加入：

```csharp
            if (method == "POST" && path == "session/start")
            {
                string body = ReadBody(request);
                SessionStartRequest sessionRequest = JsonUtility.FromJson<SessionStartRequest>(body);
                if (sessionRequest == null)
                {
                    return BridgeResponse.Failure("invalid session start request");
                }
                return SessionController.StartSession(sessionRequest.sessionId, sessionRequest.sessionPath);
            }

            if (method == "POST" && path == "session/end")
            {
                return SessionController.EndSession();
            }

            if (method == "GET" && path == "session/status")
            {
                return SessionController.GetStatus();
            }
```

- [ ] **Step 2: 扩展 Editor status**

在 `packages/com.elex.unity-agent-bridge/Editor/BridgeResponse.cs` 的 `BridgeStatusResponse` 中增加字段：

```csharp
        public bool hasActiveSession;
        public string sessionId;
        public string sessionPath;
        public string logPath;
```

在 `packages/com.elex.unity-agent-bridge/Editor/EditorStateProvider.cs` 的 `GetStatus()` 返回对象中增加：

```csharp
                hasActiveSession = SessionController.HasActiveSession,
                sessionId = SessionController.CurrentSessionId,
                sessionPath = SessionController.CurrentSessionPath,
                logPath = SessionController.CurrentLogPath
```

- [ ] **Step 3: 编译 Unity package**

Run:

```bash
"${UNITY_BIN:?set UNITY_BIN}" -batchmode -projectPath "${UNITY_PROJECT:?set UNITY_PROJECT}" -quit -logFile "/tmp/unity-agent-bridge-observability-compile.log"
```

预期：Unity 退出码为 `0`，并且 `/tmp/unity-agent-bridge-observability-compile.log` 中没有 `error CS`。

- [ ] **Step 4: 手动验证 session routes**

正常打开 Unity project，等待 Bridge 启动，然后运行：

```bash
SESSION_PATH="${UNITY_PROJECT:?set UNITY_PROJECT}/.unity-agent/sessions/manual-test"
mkdir -p "$SESSION_PATH"
curl -s -X POST http://127.0.0.1:17890/session/start \
  -H "Content-Type: application/json" \
  -d "{\"sessionId\":\"manual-test\",\"sessionPath\":\"$SESSION_PATH\"}"
curl -s http://127.0.0.1:17890/session/status
curl -s -X POST http://127.0.0.1:17890/play -d '{}'
curl -s -X POST http://127.0.0.1:17890/stop -d '{}'
curl -s -X POST http://127.0.0.1:17890/session/end -d '{}'
test -f "$SESSION_PATH/unity-console.jsonl"
```

预期：

- `/session/start` 返回包含 `"ok":true`。
- `/session/status` 返回包含 `"hasActiveSession":true`。
- 最后 `test -f` 退出码为 `0`。

- [ ] **Step 5: 提交**

Run:

```bash
git add packages/com.elex.unity-agent-bridge/Editor/BridgeServer.cs packages/com.elex.unity-agent-bridge/Editor/EditorStateProvider.cs packages/com.elex.unity-agent-bridge/Editor/BridgeResponse.cs
git commit -m "feat: add unity session bridge routes"
```

预期：commit 成功。

## Task 6: 添加 CLI 查询与端到端 Smoke Test

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 更新 README**

在 `README.md` 增加以下章节：

````markdown
## Session-based 运行观测

运行带 session 的 PlayMode：

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run unityctl play \
  --project "/path/to/unity/project" \
  --session login-flow \
  --scene Assets/Scenes/Login.unity \
  --task "verify login flow"
```

CLI 会创建：

```text
<ProjectRoot>/.unity-agent/sessions/<sessionId>/
  session.json
  unity-console.jsonl
```

停止并生成 summary：

```bash
uv run unityctl stop \
  --project "/path/to/unity/project" \
  --session-path "<ProjectRoot>/.unity-agent/sessions/<sessionId>"
```

查看日志：

```bash
uv run unityctl logs --session-path "<ProjectRoot>/.unity-agent/sessions/<sessionId>" --limit 100
uv run unityctl errors --session-path "<ProjectRoot>/.unity-agent/sessions/<sessionId>"
uv run unityctl summary --session-path "<ProjectRoot>/.unity-agent/sessions/<sessionId>"
```

可选 ignore rules：

```json
{
  "ignore": [
    {
      "type": "Error",
      "messageContains": "Expected test error"
    }
  ]
}
```
````

- [ ] **Step 2: 运行全部 Python tests**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests -v
```

预期：全部 Python tests 通过。

- [ ] **Step 3: 运行 Unity EditMode tests**

Run:

```bash
"${UNITY_BIN:?set UNITY_BIN}" -batchmode -projectPath "${UNITY_PROJECT:?set UNITY_PROJECT}" -runTests -testPlatform EditMode -testResults "/tmp/unity-agent-bridge-editmode.xml" -quit
```

预期：全部 Unity EditMode tests 通过。

- [ ] **Step 4: 运行端到端 smoke test**

正常打开 Unity project，确保 Bridge 已启动，然后运行：

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv sync
SESSION_OUTPUT="$(uv run unityctl play --project "$UNITY_PROJECT" --session login-flow --scene Assets/Scenes/Login.unity --task "verify login flow")"
SESSION_PATH="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["sessionPath"])' <<< "$SESSION_OUTPUT")"
uv run unityctl stop --project "$UNITY_PROJECT" --session-path "$SESSION_PATH"
uv run unityctl logs --session-path "$SESSION_PATH" --limit 20
uv run unityctl errors --session-path "$SESSION_PATH"
uv run unityctl summary --session-path "$SESSION_PATH"
test -f "$SESSION_PATH/session.json"
test -f "$SESSION_PATH/unity-console.jsonl"
test -f "$SESSION_PATH/summary.json"
```

预期：

- `unityctl play` 输出包含 `sessionId` 和 `sessionPath`。
- `unityctl stop` 生成 `summary.json`。
- `unityctl logs/errors/summary` 都退出码为 `0`。
- 三个 `test -f` 命令都退出码为 `0`。

- [ ] **Step 5: 提交**

Run:

```bash
git add README.md
git commit -m "docs: add unity runtime observability usage"
```

预期：commit 成功。

## Self-Review

需求覆盖：

- CLI 创建 session 目录：Task 1 和 Task 3 覆盖。
- Bridge 只写指定路径：Task 4 和 Task 5 覆盖。
- `session.json`：Task 1 覆盖。
- `unity-console.jsonl`：Task 4 覆盖。
- `playModeFrame`：Task 4 覆盖，非 PlayMode 用 `-1` 表示。
- `summary.json`：Task 2 和 Task 3 覆盖。
- Warning 不影响状态：Task 2 默认规则覆盖。
- Error 不直接 failed：Task 2 默认规则覆盖。
- Exception/Assert blocking：Task 2 默认规则覆盖。
- `.unity-agent/log-rules.json` ignore：Task 2 覆盖。
- CLI 查询：Task 3 和 Task 6 覆盖。

占位符扫描：

- 文档没有未解决的占位符标记。
- 每个 task 都给出了明确文件、命令、预期结果和 commit message。

类型一致性：

- Python 命名一致：`create_session`、`SessionPaths`、`build_summary`、`load_log_rules`、`write_summary`、`read_jsonl`。
- C# 命名一致：`SessionController`、`SessionLogWriter`、`SessionStartRequest`、`SessionStatusResponse`。

## 执行交接

计划已保存到 `docs/superpowers/plans/2026-06-30-unity-runtime-observability.md`。有两种执行方式：

1. **Subagent-Driven（推荐）**：每个 task 派一个 fresh subagent，任务之间进行 review，迭代更快。
2. **Inline Execution**：在当前会话中使用 `superpowers:executing-plans` 执行，按 checkpoint 分批 review。

请选择执行方式。
