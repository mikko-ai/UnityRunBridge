import json
from pathlib import Path

import pytest

from unityctl import __version__
from unityctl import cli
from unityctl.build import BuildError, BuildResult
from unityctl.client import BridgeClientError
from unityctl.convergence import ConvergenceResult
from unityctl.discovery import BridgeInfo, DiscoveryError


def make_unity_project(path: Path) -> Path:
    (path / "Assets").mkdir(parents=True)
    (path / "Packages").mkdir()
    (path / "ProjectSettings").mkdir()
    return path


def make_bridge_info(pid: int = 4321, port: int = 17890) -> BridgeInfo:
    return BridgeInfo(
        port=port,
        pid=pid,
        token="secret-token",
        unity_version="2022.3.62f2",
        project_path="",
        started_at="2026-07-02T09:00:00Z",
    )


def default_status() -> dict:
    return {
        "ok": True,
        "code": "ok",
        "editorState": "idle",
        "compilationSucceeded": True,
        "compilationErrors": [],
        "activeScenePath": "",
    }


class FakeClient:
    def __init__(self, base_url, token, status_response=None, post_responses=None):
        self.base_url = base_url
        self.token = token
        self.calls = []
        self.status_response = status_response if status_response is not None else default_status()
        self.post_responses: dict[str, dict] = post_responses if post_responses is not None else {}
        self.default_post_response = {"ok": True, "code": "accepted"}

    def get_status(self):
        self.calls.append(("status", None))
        return self.status_response

    def post(self, path, payload=None):
        self.calls.append((path, payload))
        return self.post_responses.get(path, self.default_post_response)

    def open_scene(self, scene_path):
        self.calls.append(("open-scene", {"scenePath": scene_path}))
        return {"ok": True, "code": "accepted", "scenePath": scene_path}

    def start_session(self, session_id, session_path):
        self.calls.append(
            ("session/start", {"sessionId": session_id, "sessionPath": session_path})
        )
        return {"ok": True, "code": "session_started"}

    def end_session(self):
        self.calls.append(("session/end", None))
        return {"ok": True, "code": "session_ended"}

    def refresh(self):
        self.calls.append(("refresh", None))
        return {"ok": True, "code": "accepted"}

    def get_capabilities(self):
        self.calls.append(("capabilities", None))
        return {
            "ok": True,
            "capabilities": [
                "core", "hierarchy", "capture", "interaction", "gameplay", "recording", "profiling",
            ],
        }

    def capture_screenshot(self, reason=None, max_long_edge=None, target_directory=None):
        self.calls.append(
            (
                "capture/screenshot",
                {"reason": reason, "maxLongEdge": max_long_edge, "targetDirectory": target_directory},
            )
        )
        return {"ok": True, "jobId": "job-fake-1"}

    def get_job(self, job_id):
        self.calls.append(("get_job", job_id))
        return {"job": {"id": job_id, "status": "succeeded", "result": {"path": "/tmp/fake-shot.png"}}}

    def hierarchy_roots(self):
        self.calls.append(("hierarchy/roots", None))
        return {"ok": True, "scenes": []}

    def hierarchy_tree(self, **params):
        self.calls.append(("hierarchy/tree", params))
        return {"ok": True, "nodes": []}

    def hierarchy_find(self, **params):
        self.calls.append(("hierarchy/find", params))
        return {"ok": True, "matchedCount": 0, "nodes": []}

    def hierarchy_ancestors(self, **params):
        self.calls.append(("hierarchy/ancestors", params))
        return {"ok": True, "ancestors": []}

    def hierarchy_inspect(self, **params):
        self.calls.append(("hierarchy/inspect", params))
        return {"ok": True, "node": {}}

    def interaction_click(self, path, force=False, scene=None):
        self.calls.append(("interaction/click", {"path": path, "force": force, "scene": scene}))
        return {"ok": True, "clicked": path, "raycastHit": path, "forced": force, "events": ["pointerDown", "pointerUp", "pointerClick"]}

    def interaction_input(self, path, text, submit=False, scene=None):
        self.calls.append(("interaction/input", {"path": path, "text": text, "submit": submit, "scene": scene}))
        return {"ok": True, "code": "ok", "message": "input applied"}

    def interaction_set_value(self, path, value, component=None, scene=None):
        self.calls.append(
            ("interaction/set-value", {"path": path, "value": value, "component": component, "scene": scene})
        )
        return {"ok": True, "component": component or "Slider"}

    def gameplay_list(self):
        self.calls.append(("gameplay/commands", None))
        return {"ok": True, "commands": []}

    def gameplay_invoke(self, command, args=None):
        self.calls.append(("gameplay/invoke", {"command": command, "args": args or {}}))
        return {"ok": True, "result": 101, "durationMs": 3}

    def recording_start(self, target_directory=None):
        self.calls.append(("recording/start", {"targetDirectory": target_directory}))
        return {"ok": True, "actionsPath": "/tmp/actions.jsonl", "metaPath": "/tmp/recording-meta.json"}

    def recording_stop(self):
        self.calls.append(("recording/stop", None))
        return {"ok": True, "actionsPath": "/tmp/actions.jsonl", "actionCount": 3, "interrupted": False}

    def recording_status(self):
        self.calls.append(("recording/status", None))
        return {"ok": True, "recording": True, "interrupted": False, "actionCount": 3, "actionsPath": "/tmp/actions.jsonl"}

    def profiling_start(self, target_directory=None):
        self.calls.append(("profiling/start", {"targetDirectory": target_directory}))
        return {"ok": True, "metricsPath": "/tmp/metrics.jsonl", "unavailableMetrics": []}

    def profiling_stop(self):
        self.calls.append(("profiling/stop", None))
        return {
            "ok": True,
            "metricsPath": "/tmp/metrics.jsonl",
            "frameCount": 120,
            "interrupted": False,
            "aggregates": {"frameTimeMs": {"avg": 16.2, "max": 41.0, "p95": 22.1}},
        }

    def profiling_status(self):
        self.calls.append(("profiling/status", None))
        return {"ok": True, "profiling": True, "interrupted": False, "frameCount": 42, "metricsPath": "/tmp/metrics.jsonl"}


def patch_bridge(monkeypatch, info: BridgeInfo | None = None):
    """所有通过 cli.BridgeClient 创建的假客户端共享同一个 status_response 字典，
    这样测试可以在两次 cli.main() 调用之间修改它来模拟状态变化（例如编译失败）。"""

    clients: list[FakeClient] = []
    bridge_info = info or make_bridge_info()
    shared_status = default_status()
    shared_post_responses: dict[str, dict] = {}

    def fake_discover(project_path):
        return bridge_info

    def fake_client_factory(base_url, token):
        client = FakeClient(
            base_url,
            token,
            status_response=shared_status,
            post_responses=shared_post_responses,
        )
        clients.append(client)
        return client

    monkeypatch.setattr(cli, "discover", fake_discover)
    monkeypatch.setattr(cli, "BridgeClient", fake_client_factory)
    return clients, bridge_info, shared_status, shared_post_responses


def patch_poll_until_success(monkeypatch, statuses):
    """按调用顺序依次返回给定的状态并断言 predicate 认可该状态。"""

    queue = list(statuses)

    def fake_poll_until(project_path, predicate, timeout_seconds, poll_interval=0.5, initial_info=None):
        status = queue.pop(0)
        accepted = predicate(status)
        assert accepted, f"predicate rejected status used in test fake: {status}"
        return ConvergenceResult(status=status, info=initial_info)

    monkeypatch.setattr(cli, "poll_until", fake_poll_until)


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"unityctl {__version__}"


def test_status_command_prints_json(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(["--project", str(tmp_path), "status"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert clients[0].calls == [("status", None)]


def test_play_without_session_posts_play_and_waits_for_playing(monkeypatch, tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    clients, _, _, _ = patch_bridge(monkeypatch)
    patch_poll_until_success(monkeypatch, [{"editorState": "playing"}])

    exit_code = cli.main(["--project", str(project), "play"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert clients[0].calls[0] == ("status", None)
    assert ("play", None) in clients[0].calls


def test_play_no_wait_skips_convergence(monkeypatch, tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    clients, _, _, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(["--project", str(project), "play", "--no-wait"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert ("play", None) in clients[0].calls


def test_play_no_wait_still_opens_requested_scene(monkeypatch, tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    clients, _, _, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(
        [
            "--project",
            str(project),
            "play",
            "--scene",
            "Assets/Scenes/Login.unity",
            "--no-wait",
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert clients[0].calls == [
        ("status", None),
        ("open-scene", {"scenePath": "Assets/Scenes/Login.unity"}),
        ("play", None),
    ]


def test_play_without_scene_uses_default_scene_from_config(monkeypatch, tmp_path, capsys):
    from unityctl.config import init_project_config

    project = make_unity_project(tmp_path / "Game")
    init_project_config(
        project_path=project,
        default_scene="Assets/Scenes/Main.unity",
    )
    clients, _, _, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(["--project", str(project), "play", "--no-wait"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert clients[0].calls == [
        ("status", None),
        ("open-scene", {"scenePath": "Assets/Scenes/Main.unity"}),
        ("play", None),
    ]


def test_play_explicit_scene_overrides_default_scene(monkeypatch, tmp_path, capsys):
    from unityctl.config import init_project_config

    project = make_unity_project(tmp_path / "Game")
    init_project_config(
        project_path=project,
        default_scene="Assets/Scenes/Main.unity",
    )
    clients, _, _, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(
        [
            "--project",
            str(project),
            "play",
            "--scene",
            "Assets/Scenes/Login.unity",
            "--no-wait",
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert clients[0].calls == [
        ("status", None),
        ("open-scene", {"scenePath": "Assets/Scenes/Login.unity"}),
        ("play", None),
    ]


def test_play_with_session_records_resolved_default_scene(monkeypatch, tmp_path, capsys):
    from datetime import datetime

    from unityctl.config import init_project_config

    project = make_unity_project(tmp_path / "Game")
    init_project_config(
        project_path=project,
        default_scene="Assets/Scenes/Main.unity",
    )
    monkeypatch.setattr(
        cli, "utc_now", lambda: datetime.fromisoformat("2026-06-30T18:30:12+00:00")
    )
    patch_bridge(monkeypatch)

    exit_code = cli.main(
        [
            "--project",
            str(project),
            "play",
            "--session",
            "main-flow",
            "--no-wait",
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    session_json = json.loads(
        (
            project
            / ".unity-agent"
            / "sessions"
            / output["sessionId"]
            / "session.json"
        ).read_text(encoding="utf-8")
    )
    assert session_json["scenePath"] == "Assets/Scenes/Main.unity"


def test_play_no_wait_with_session_marks_session_running(monkeypatch, tmp_path, capsys):
    from datetime import datetime

    project = make_unity_project(tmp_path / "Game")
    monkeypatch.setattr(
        cli, "utc_now", lambda: datetime.fromisoformat("2026-06-30T18:30:12+00:00")
    )
    patch_bridge(monkeypatch)

    exit_code = cli.main(
        [
            "--project",
            str(project),
            "play",
            "--session",
            "login-flow",
            "--no-wait",
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    session_json = json.loads(
        (
            project
            / ".unity-agent"
            / "sessions"
            / output["sessionId"]
            / "session.json"
        ).read_text(encoding="utf-8")
    )
    assert session_json["status"] == "running"
    assert session_json["startedAt"] == "2026-06-30T18:30:12Z"


def test_play_fails_fast_when_compilation_already_failed(monkeypatch, tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    clients, _, shared_status, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(["--project", str(project), "play", "--no-wait"])
    assert exit_code == 0
    capsys.readouterr()

    shared_status["compilationSucceeded"] = False
    shared_status["compilationErrors"] = [
        {"file": "Assets/Foo.cs", "line": 1, "message": "boom"}
    ]

    exit_code = cli.main(["--project", str(project), "play"])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().err)
    assert output["ok"] is False
    assert output["code"] == "compilation_failed"
    assert output["compilationErrors"][0]["message"] == "boom"


def test_play_waits_out_compilation_before_checking_stale_failure(monkeypatch, tmp_path, capsys):
    """正在编译时，上一轮编译失败的陈旧状态不应导致快速失败：应等编译结束后按新结果判断。"""
    project = make_unity_project(tmp_path / "Game")
    clients, _, shared_status, _ = patch_bridge(monkeypatch)
    shared_status["editorState"] = "compiling"
    shared_status["compilationSucceeded"] = False
    patch_poll_until_success(
        monkeypatch,
        [
            {"editorState": "idle", "compilationSucceeded": True},
            {"editorState": "playing"},
        ],
    )

    exit_code = cli.main(["--project", str(project), "play"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True


def test_play_fails_after_wait_when_fresh_compilation_failed(monkeypatch, tmp_path, capsys):
    """编译等待结束后如果新一轮编译失败，应快速失败且不创建 session。"""
    project = make_unity_project(tmp_path / "Game")
    clients, _, shared_status, _ = patch_bridge(monkeypatch)
    shared_status["editorState"] = "compiling"
    patch_poll_until_success(
        monkeypatch,
        [
            {
                "editorState": "idle",
                "compilationSucceeded": False,
                "compilationErrors": [{"message": "fresh failure"}],
            }
        ],
    )

    exit_code = cli.main(
        ["--project", str(project), "play", "--session", "login-flow"]
    )

    assert exit_code == 1
    output = json.loads(capsys.readouterr().err)
    assert output["code"] == "compilation_failed"
    assert output["compilationErrors"][0]["message"] == "fresh failure"
    assert not (project / ".unity-agent" / "sessions").exists()
    assert not any(call[0] == "session/start" for call in clients[0].calls)


def test_play_failure_after_session_start_ends_bridge_session(monkeypatch, tmp_path, capsys):
    """session/start 之后 play 失败，应通知 Unity 侧结束 session 并写入本地 failed 记录。"""
    project = make_unity_project(tmp_path / "Game")
    clients, _, _, shared_post_responses = patch_bridge(monkeypatch)
    shared_post_responses["play"] = {"ok": False, "code": "busy", "message": "editor not idle"}

    exit_code = cli.main(
        ["--project", str(project), "play", "--session", "login-flow"]
    )

    assert exit_code == 1
    output = json.loads(capsys.readouterr().err)
    assert output["code"] == "busy"
    all_calls = [call for client in clients for call in client.calls]
    assert ("session/end", None) in all_calls

    sessions_dir = project / ".unity-agent" / "sessions"
    session_dirs = list(sessions_dir.iterdir())
    assert len(session_dirs) == 1
    session_json = json.loads((session_dirs[0] / "session.json").read_text(encoding="utf-8"))
    assert session_json["status"] == "failed"
    assert session_json["failedReason"] == "busy"
    assert (session_dirs[0] / "summary.json").exists()


def test_play_detects_compilation_failure_finished_in_same_second(monkeypatch, tmp_path, capsys):
    from datetime import datetime

    project = make_unity_project(tmp_path / "Game")
    patch_bridge(monkeypatch)
    monkeypatch.setattr(
        cli, "utc_now", lambda: datetime.fromisoformat("2026-06-30T18:30:12.900000+00:00")
    )

    def fake_poll_until(project_path, predicate, timeout_seconds, poll_interval=0.5, initial_info=None):
        predicate(
            {
                "editorState": "idle",
                "compilationSucceeded": False,
                "compilationFinishedAt": "2026-06-30T18:30:12Z",
                "compilationErrors": [{"message": "same-second failure"}],
            }
        )
        raise AssertionError("predicate should raise ConvergenceFailed")

    monkeypatch.setattr(cli, "poll_until", fake_poll_until)

    exit_code = cli.main(["--project", str(project), "play"])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().err)
    assert output["code"] == "compilation_failed"
    assert output["compilationErrors"][0]["message"] == "same-second failure"


def test_open_scene_command_sends_path(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(["--project", str(tmp_path), "open-scene", "Assets/Scenes/Login.unity"])

    assert exit_code == 0
    assert clients[0].calls == [
        ("open-scene", {"scenePath": "Assets/Scenes/Login.unity"})
    ]


def test_play_with_session_creates_session_and_starts_bridge(monkeypatch, tmp_path, capsys):
    from datetime import datetime

    clients, info, _, _ = patch_bridge(monkeypatch)
    patch_poll_until_success(
        monkeypatch,
        [
            {"activeScenePath": "Assets/Scenes/Login.unity"},
            {"editorState": "playing"},
        ],
    )
    monkeypatch.setattr(
        cli, "utc_now", lambda: datetime.fromisoformat("2026-06-30T18:30:12+00:00")
    )

    project = make_unity_project(tmp_path / "Game")

    exit_code = cli.main(
        [
            "play",
            "--project",
            str(project),
            "--session",
            "login-flow",
            "--scene",
            "Assets/Scenes/Login.unity",
            "--task",
            "verify login flow",
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["sessionId"].endswith("login-flow")
    assert (
        project
        / ".unity-agent"
        / "sessions"
        / output["sessionId"]
        / "session.json"
    ).exists()
    assert clients[0].calls[0] == ("status", None)
    assert clients[0].calls[1][0] == "session/start"
    assert ("play", None) in clients[0].calls


def make_console_log(session: Path, rows: list[dict]) -> None:
    session.mkdir(parents=True, exist_ok=True)
    (session / "unity-console.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )


def sample_log_rows() -> list[dict]:
    return [
        {"sequence": 1, "type": "Log", "message": "Boot start"},
        {"sequence": 2, "type": "Warning", "message": "shader fallback"},
        {"sequence": 3, "type": "Log", "message": "Login begin"},
        {"sequence": 4, "type": "Error", "message": "login failed: timeout"},
        {"sequence": 5, "type": "Log", "message": "Login retry"},
    ]


def test_logs_command_adds_line_numbers_and_counts(tmp_path, capsys):
    session = tmp_path / "s1"
    make_console_log(session, sample_log_rows())

    exit_code = cli.main(["logs", "--session-path", str(session)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["totalCount"] == 5
    assert output["matchedCount"] == 5
    assert [row["line"] for row in output["logs"]] == [1, 2, 3, 4, 5]


def test_logs_command_grep_is_case_insensitive_and_keeps_line(tmp_path, capsys):
    session = tmp_path / "s1"
    make_console_log(session, sample_log_rows())

    exit_code = cli.main(["logs", "--session-path", str(session), "--grep", "login"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["matchedCount"] == 3
    # line 是全量日志中的行号，过滤后不重排
    assert [row["line"] for row in output["logs"]] == [3, 4, 5]


def test_logs_command_filters_by_type(tmp_path, capsys):
    session = tmp_path / "s1"
    make_console_log(session, sample_log_rows())

    exit_code = cli.main(
        ["logs", "--session-path", str(session), "--type", "Error,Warning"]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert [row["sequence"] for row in output["logs"]] == [2, 4]


def test_logs_command_after_sequence_returns_increment_only(tmp_path, capsys):
    session = tmp_path / "s1"
    make_console_log(session, sample_log_rows())

    exit_code = cli.main(
        ["logs", "--session-path", str(session), "--after-sequence", "3"]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert [row["sequence"] for row in output["logs"]] == [4, 5]


def test_logs_command_limit_applies_after_filtering(tmp_path, capsys):
    session = tmp_path / "s1"
    make_console_log(session, sample_log_rows())

    exit_code = cli.main(
        ["logs", "--session-path", str(session), "--grep", "login", "--limit", "2"]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["matchedCount"] == 3
    # limit 取过滤结果中最近的 N 条
    assert [row["line"] for row in output["logs"]] == [4, 5]


def test_errors_command_includes_line_numbers(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    session = project / ".unity-agent" / "sessions" / "2026-07-06_100000_s1"
    make_console_log(session, sample_log_rows())

    exit_code = cli.main(["--project", str(project), "errors", "--latest"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert len(output["errors"]) == 1
    assert output["errors"][0]["line"] == 4
    assert output["errors"][0]["message"] == "login failed: timeout"


def test_summary_command_prints_summary_file(tmp_path, capsys):
    session = tmp_path / "s1"
    session.mkdir()
    (session / "summary.json").write_text('{"status":"passed"}', encoding="utf-8")

    exit_code = cli.main(["summary", "--session-path", str(session)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "passed"
    assert output["ok"] is True


def test_init_command_writes_project_and_local_config(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")

    exit_code = cli.main(
        [
            "--project",
            str(project),
            "init",
            "--yes",
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["projectPath"] == str(project)
    assert output["alreadyInitialized"] is False
    assert (project / ".unity-agent" / "config.json").exists()
    assert (project / ".unity-agent" / "config.local.json").exists()
    assert ".unity-agent/config.local.json" in (project / ".gitignore").read_text()


def test_init_yes_skips_package_install_without_flag(tmp_path, capsys):
    """--yes 非交互模式下不应擅自修改 manifest，只提示后续步骤。"""
    project = make_unity_project(tmp_path / "Game")
    manifest = project / "Packages" / "manifest.json"
    manifest.write_text('{"dependencies": {}}', encoding="utf-8")

    exit_code = cli.main(["--project", str(project), "init", "--yes"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["packageInstalled"] is False
    assert output["packageAction"] == "skipped"
    assert "com.mk.unity-agent-bridge" not in manifest.read_text(encoding="utf-8")
    assert any("manifest.json" in step for step in output["nextSteps"])


def test_init_install_package_writes_manifest_dependency(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    manifest = project / "Packages" / "manifest.json"
    manifest.write_text(
        json.dumps({"dependencies": {"com.unity.ugui": "1.0.0"}}), encoding="utf-8"
    )

    exit_code = cli.main(
        ["--project", str(project), "init", "--yes", "--install-package"]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["packageInstalled"] is True
    assert output["packageAction"] == "installed"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    # 已有依赖保留，新增 bridge 依赖指向与 CLI 版本一致的 upm tag
    assert payload["dependencies"]["com.unity.ugui"] == "1.0.0"
    assert (
        payload["dependencies"]["com.mk.unity-agent-bridge"]
        == f"https://github.com/mikko-ai/UnityRunBridge.git#upm/v{__version__}"
    )
    assert output["packageRef"] == payload["dependencies"]["com.mk.unity-agent-bridge"]


def test_init_install_package_respects_custom_ref(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    manifest = project / "Packages" / "manifest.json"
    manifest.write_text('{"dependencies": {}}', encoding="utf-8")

    exit_code = cli.main(
        [
            "--project",
            str(project),
            "init",
            "--yes",
            "--install-package",
            "--package-ref",
            "file:/tmp/com.mk.unity-agent-bridge-0.1.2.tgz",
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert (
        payload["dependencies"]["com.mk.unity-agent-bridge"]
        == "file:/tmp/com.mk.unity-agent-bridge-0.1.2.tgz"
    )
    assert output["packageAction"] == "installed"


def test_init_reports_already_installed_package(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    manifest = project / "Packages" / "manifest.json"
    manifest.write_text(
        json.dumps(
            {"dependencies": {"com.mk.unity-agent-bridge": "file:/existing/path"}}
        ),
        encoding="utf-8",
    )

    exit_code = cli.main(
        ["--project", str(project), "init", "--yes", "--install-package"]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["packageInstalled"] is True
    assert output["packageAction"] == "already_installed"
    # 已有引用不被覆盖
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["dependencies"]["com.mk.unity-agent-bridge"] == "file:/existing/path"


def test_init_no_install_package_skips_manifest(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    manifest = project / "Packages" / "manifest.json"
    manifest.write_text('{"dependencies": {}}', encoding="utf-8")

    exit_code = cli.main(
        ["--project", str(project), "init", "--yes", "--no-install-package"]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["packageAction"] == "skipped"
    assert "com.mk.unity-agent-bridge" not in manifest.read_text(encoding="utf-8")


def test_init_interactive_prompt_installs_on_consent(monkeypatch, tmp_path, capsys):
    """交互模式下缺依赖时询问用户，同意后写入 manifest。"""
    project = make_unity_project(tmp_path / "Game")
    manifest = project / "Packages" / "manifest.json"
    manifest.write_text('{"dependencies": {}}', encoding="utf-8")

    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    answers = iter(["y", "y"])  # 第一次确认 init，第二次确认写入 manifest
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    exit_code = cli.main(["--project", str(project), "init"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["packageAction"] == "installed"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert "com.mk.unity-agent-bridge" in payload["dependencies"]


def test_init_interactive_prompt_declined_leaves_manifest(monkeypatch, tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    manifest = project / "Packages" / "manifest.json"
    manifest.write_text('{"dependencies": {}}', encoding="utf-8")

    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    answers = iter(["y", "n"])  # 同意 init，拒绝写入 manifest
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    exit_code = cli.main(["--project", str(project), "init"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["packageAction"] == "declined"
    assert output["packageInstalled"] is False
    assert "com.mk.unity-agent-bridge" not in manifest.read_text(encoding="utf-8")


def test_init_command_requires_confirmation_when_not_yes(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")

    exit_code = cli.main(["--project", str(project), "init"])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().err)
    assert "需要确认" in output["message"]
    assert not (project / ".unity-agent").exists()


def test_config_show_prints_effective_config(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    cli.main(
        [
            "--project",
            str(project),
            "init",
            "--yes",
            "--unity",
            "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity",
            "--unity-version",
            "2022.3.62f2",
            "--port",
            "17891",
        ]
    )
    capsys.readouterr()

    exit_code = cli.main(["--project", str(project), "config", "show"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["preferredPort"] == 17891
    assert output["unityVersion"] == "2022.3.62f2"
    assert output["unityExecutablePath"].endswith("Unity.app/Contents/MacOS/Unity")


def test_config_set_local_updates_local_config(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    cli.main(["--project", str(project), "init", "--yes"])
    capsys.readouterr()

    exit_code = cli.main(
        [
            "--project",
            str(project),
            "config",
            "set-local",
            "unityExecutablePath",
            "/Applications/Unity/Hub/Editor/6000.0.0f1/Unity.app/Contents/MacOS/Unity",
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["unityExecutablePath"] == "/Applications/Unity/Hub/Editor/6000.0.0f1/Unity.app/Contents/MacOS/Unity"


def test_config_validate_reports_missing_local_unity_path(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    cli.main(["--project", str(project), "init", "--yes"])
    capsys.readouterr()

    exit_code = cli.main(["--project", str(project), "config", "validate"])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is False
    assert output["errors"][0]["field"] == "config.local.unityExecutablePath"


def test_summary_latest_reads_latest_session(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    old_session = project / ".unity-agent" / "sessions" / "2026-07-01_100000_old"
    new_session = project / ".unity-agent" / "sessions" / "2026-07-02_100000_new"
    old_session.mkdir(parents=True)
    new_session.mkdir(parents=True)
    (old_session / "summary.json").write_text('{"status":"failed"}', encoding="utf-8")
    (new_session / "summary.json").write_text('{"status":"passed"}', encoding="utf-8")

    exit_code = cli.main(["--project", str(project), "summary", "--latest"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "passed"


def test_start_command_uses_resolved_config(monkeypatch, tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    cli.main(
        [
            "--project",
            str(project),
            "init",
            "--yes",
            "--unity",
            "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity",
            "--unity-version",
            "2022.3.62f2",
        ]
    )
    capsys.readouterr()

    class FakeProcess:
        pid = 12345

    calls = []

    def fake_start_editor(unity_path, project_path, log_file):
        calls.append((unity_path, project_path, log_file))
        return FakeProcess()

    monkeypatch.setattr(cli, "start_editor", fake_start_editor)

    exit_code = cli.main(["--project", str(project), "start", "--no-wait"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["pid"] == 12345
    assert output["bridgeReady"] is False
    assert calls[0][0].endswith("Unity.app/Contents/MacOS/Unity")
    assert calls[0][1] == project


def test_start_command_waits_for_handshake_by_default(monkeypatch, tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    cli.main(
        [
            "--project",
            str(project),
            "init",
            "--yes",
            "--unity",
            "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity",
            "--unity-version",
            "2022.3.62f2",
            "--port",
            "17891",
        ]
    )
    capsys.readouterr()

    class FakeProcess:
        pid = 12345

    monkeypatch.setattr(cli, "start_editor", lambda *_args: FakeProcess())
    monkeypatch.setattr(
        cli,
        "wait_for_handshake",
        lambda project_path, expected_pid, timeout_seconds: make_bridge_info(pid=expected_pid, port=17891),
    )

    exit_code = cli.main(["--project", str(project), "start"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["bridgeReady"] is True
    assert output["bridgeUrl"] == "http://127.0.0.1:17891"


def test_start_command_returns_already_running_when_bridge_reachable(
    monkeypatch, tmp_path, capsys
):
    project = make_unity_project(tmp_path / "Game")
    bridge_info = make_bridge_info(pid=9999, port=17891)

    def fake_discover(project_path):
        return bridge_info

    class FakeBridgeClient:
        def __init__(self, base_url, token):
            self.base_url = base_url
            self.token = token

        def get_status(self):
            return default_status()

    def fake_start_editor(*args):
        raise AssertionError("start_editor should not be called")

    monkeypatch.setattr(cli, "discover", fake_discover)
    monkeypatch.setattr(cli, "BridgeClient", FakeBridgeClient)
    monkeypatch.setattr(cli, "start_editor", fake_start_editor)

    exit_code = cli.main(["--project", str(project), "start"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["code"] == "already_running"
    assert output["pid"] == 9999
    assert output["logFile"] is None
    assert output["bridgeReady"] is True
    assert output["bridgeUrl"] == "http://127.0.0.1:17891"
    assert output["unityVersion"] == "2022.3.62f2"


def test_start_command_falls_through_to_lock_check_when_bridge_unreachable(
    monkeypatch, tmp_path, capsys
):
    project = make_unity_project(tmp_path / "Game")
    cli.main(
        [
            "--project",
            str(project),
            "init",
            "--yes",
            "--unity",
            "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity",
        ]
    )
    capsys.readouterr()

    bridge_info = make_bridge_info(pid=9999, port=17891)
    start_calls = []

    class FakeBridgeClient:
        def __init__(self, base_url, token):
            pass

        def get_status(self):
            raise BridgeClientError("connection refused", "bridge_unreachable")

    class FakeProcess:
        pid = 12345

    monkeypatch.setattr(cli, "discover", lambda project_path: bridge_info)
    monkeypatch.setattr(cli, "BridgeClient", FakeBridgeClient)
    monkeypatch.setattr(cli, "is_unity_project_locked", lambda project_path: False)
    monkeypatch.setattr(cli, "start_editor", lambda *args: (start_calls.append(args) or FakeProcess()))

    exit_code = cli.main(["--project", str(project), "start", "--no-wait"])

    assert exit_code == 0
    assert len(start_calls) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["code"] == "ok"
    assert output["pid"] == 12345


def test_start_command_fails_fast_when_project_locked(monkeypatch, tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")

    def fake_discover(project_path):
        raise DiscoveryError("no bridge")

    def fake_start_editor(*args):
        raise AssertionError("start_editor should not be called")

    monkeypatch.setattr(cli, "discover", fake_discover)
    monkeypatch.setattr(cli, "is_unity_project_locked", lambda project_path: True)
    monkeypatch.setattr(cli, "start_editor", fake_start_editor)

    exit_code = cli.main(["--project", str(project), "start"])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().err)
    assert output["ok"] is False
    assert output["code"] == "editor_already_running"


def test_stop_latest_updates_latest_session_summary(monkeypatch, tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    cli.main(
        [
            "--project",
            str(project),
            "init",
            "--yes",
            "--unity-version",
            "2022.3.62f2",
        ]
    )
    capsys.readouterr()
    old_session = project / ".unity-agent" / "sessions" / "2026-07-01_100000_old"
    new_session = project / ".unity-agent" / "sessions" / "2026-07-02_100000_new"
    old_session.mkdir(parents=True)
    new_session.mkdir(parents=True)
    (new_session / "unity-console.jsonl").write_text("", encoding="utf-8")
    (new_session / "session.json").write_text(
        json.dumps(
            {
                "sessionId": "2026-07-02_100000_new",
                "name": "new",
                "projectPath": str(project),
                "scenePath": None,
                "createdAt": "2026-07-02T10:00:00Z",
                "startedAt": None,
                "endedAt": None,
                "status": "running",
                "trigger": "agent",
                "task": "",
                "failedReason": None,
                "editorPid": None,
                "unityVersion": None,
            }
        ),
        encoding="utf-8",
    )

    patch_bridge(monkeypatch)
    patch_poll_until_success(monkeypatch, [{"editorState": "idle"}])

    exit_code = cli.main(["--project", str(project), "stop", "--latest"])

    assert exit_code == 0
    assert (new_session / "summary.json").is_file()


def test_doctor_reports_all_checks(monkeypatch, tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    cli.main(
        [
            "--project",
            str(project),
            "init",
            "--yes",
            "--unity",
            "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity",
            "--unity-version",
            "2022.3.62f2",
        ]
    )
    capsys.readouterr()

    exit_code = cli.main(["--project", str(project), "doctor"])

    output = json.loads(capsys.readouterr().out)
    names = [check["name"] for check in output["checks"]]
    assert "project_root" in names
    assert "config_json" in names
    assert "project_lock" in names
    # 未启动 Unity Editor 时 bridge.json 不存在，doctor 命令本身应正常返回而不是抛异常
    assert exit_code in (0, 1)


def _make_build_result(**overrides) -> BuildResult:
    defaults = dict(
        ok=True,
        build_id="20260707T000000Z-StandaloneOSX",
        result="Succeeded",
        report={
            "result": "Succeeded",
            "durationMs": 1234,
            "outputPath": "/tmp/build/Build.app",
            "sizeBytes": 999,
            "errors": [],
            "warnings": [],
            "reportSource": "build_report",
        },
        report_path=Path("/tmp/build/build-report.json"),
        log_path=Path("/tmp/build/build.log"),
        output_path=Path("/tmp/build/Build.app"),
        exit_code=0,
        command=["/Unity", "-batchmode"],
    )
    defaults.update(overrides)
    return BuildResult(**defaults)


def test_build_dispatches_to_run_build_and_returns_success_payload(monkeypatch, tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    captured_kwargs = {}

    def fake_run_build(**kwargs):
        captured_kwargs.update(kwargs)
        return _make_build_result()

    monkeypatch.setattr(cli, "run_build", fake_run_build)

    exit_code = cli.main(
        ["--project", str(project), "build", "--target", "StandaloneOSX", "--timeout", "120"]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["ok"] is True
    assert output["code"] == "ok"
    assert output["result"] == "Succeeded"
    assert output["buildId"] == "20260707T000000Z-StandaloneOSX"
    assert captured_kwargs["target"] == "StandaloneOSX"
    assert captured_kwargs["timeout_seconds"] == 120


def test_build_reports_failure_without_raising(monkeypatch, tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")

    def fake_run_build(**kwargs):
        return _make_build_result(
            ok=False,
            result="Failed",
            report={
                "result": "Failed",
                "durationMs": 10,
                "outputPath": "",
                "sizeBytes": 0,
                "errors": ["Assets/Broken.cs(1,1): error CS1002: ; expected"],
                "warnings": [],
                "reportSource": "log_fallback",
            },
        )

    monkeypatch.setattr(cli, "run_build", fake_run_build)

    exit_code = cli.main(["--project", str(project), "build"])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert output["ok"] is False
    assert output["code"] == "build_failed"
    assert output["reportSource"] == "log_fallback"


def test_build_maps_build_error_to_cli_error(monkeypatch, tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")

    def fake_run_build(**kwargs):
        raise BuildError("项目被占用", code="editor_running")

    monkeypatch.setattr(cli, "run_build", fake_run_build)

    exit_code = cli.main(["--project", str(project), "build"])

    output = json.loads(capsys.readouterr().err)
    assert exit_code == 1
    assert output["code"] == "editor_running"


def test_health_runs_offline_checks_without_bridge(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    (project / "Packages" / "manifest.json").write_text(
        json.dumps({"dependencies": {}}), encoding="utf-8"
    )
    (project / "Packages" / "packages-lock.json").write_text(
        json.dumps({"dependencies": {}}), encoding="utf-8"
    )

    exit_code = cli.main(
        ["--project", str(project), "health", "--check", "packages,build_scenes"]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert [check["name"] for check in output["checks"]] == ["packages", "build_scenes"]


def test_health_defaults_skip_bridge_checks_when_unreachable(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")

    exit_code = cli.main(["--project", str(project), "health"])

    output = json.loads(capsys.readouterr().out)
    checks_by_name = {check["name"]: check for check in output["checks"]}
    assert checks_by_name["compilation"]["status"] == "skipped"
    assert checks_by_name["missing_scripts"]["status"] == "skipped"
    # skipped 不计入失败；这个临时项目里只有 build_scenes/packages 会因为文件缺失报 fail/warn。
    assert exit_code in (0, 1)


def test_health_rejects_unknown_check_name(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")

    exit_code = cli.main(["--project", str(project), "health", "--check", "not_a_real_check"])

    output = json.loads(capsys.readouterr().err)
    assert exit_code == 1
    assert output["ok"] is False


def test_hierarchy_roots_dispatches_to_client(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(["--project", str(tmp_path), "hierarchy", "roots"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert ("hierarchy/roots", None) in clients[0].calls


def test_hierarchy_tree_passes_path_and_options(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(
        ["--project", str(tmp_path), "hierarchy", "tree", "MainCanvas/Button", "--depth", "2", "--page-size", "10"]
    )

    assert exit_code == 0
    call_path, params = clients[0].calls[-1]
    assert call_path == "hierarchy/tree"
    assert params["path"] == "MainCanvas/Button"
    assert params["depth"] == 2
    assert params["pageSize"] == 10


def test_hierarchy_find_passes_all_filters(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(
        [
            "--project",
            str(tmp_path),
            "hierarchy",
            "find",
            "--component",
            "Button",
            "--active-only",
            "--sort-by",
            "Canvas.sortingOrder",
            "--desc",
            "--count",
        ]
    )

    assert exit_code == 0
    call_path, params = clients[0].calls[-1]
    assert call_path == "hierarchy/find"
    assert params["component"] == "Button"
    assert params["active"] == "only"
    assert params["sortBy"] == "Canvas.sortingOrder"
    assert params["order"] == "desc"
    assert params["countOnly"] is True


def test_hierarchy_ancestors_and_inspect_dispatch(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)

    cli.main(["--project", str(tmp_path), "hierarchy", "ancestors", "A/B", "--component", "Canvas"])
    cli.main(["--project", str(tmp_path), "hierarchy", "inspect", "A/B"])
    capsys.readouterr()

    assert ("hierarchy/ancestors", {"path": "A/B", "scene": None, "component": "Canvas"}) in clients[0].calls
    assert ("hierarchy/inspect", {"path": "A/B", "scene": None}) in clients[1].calls


def test_hierarchy_missing_capability_returns_error(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)

    def legacy_capabilities(self):
        return {"ok": True, "capabilities": ["core"]}

    monkeypatch.setattr(FakeClient, "get_capabilities", legacy_capabilities)

    exit_code = cli.main(["--project", str(tmp_path), "hierarchy", "roots"])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().err)
    assert output["ok"] is False
    assert output["code"] == "bridge_capability_missing"


class _FakeCapabilitiesClient:
    def __init__(self, capabilities):
        self._capabilities = capabilities

    def get_capabilities(self):
        return {"ok": True, "capabilities": self._capabilities}


def test_require_capability_passes_when_present():
    client = _FakeCapabilitiesClient(["core", "hierarchy"])
    cli._require_capability(client, "hierarchy")  # 不应抛异常


def test_require_capability_raises_when_missing():
    client = _FakeCapabilitiesClient(["core"])
    with pytest.raises(cli.CliError) as exc:
        cli._require_capability(client, "hierarchy")
    assert exc.value.code == "bridge_capability_missing"
    assert "hierarchy" in str(exc.value)


def test_snapshot_dispatches_and_waits_for_job(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)

    def fake_wait_for_job(project_path, job_id, timeout_seconds, poll_interval=0.5, initial_info=None, raise_on_failure=True):
        assert job_id == "job-fake-1"
        return {"id": job_id, "status": "succeeded", "result": {"path": "/tmp/shot.png", "width": 640, "height": 360}}

    monkeypatch.setattr(cli, "wait_for_job", fake_wait_for_job)

    exit_code = cli.main(["--project", str(tmp_path), "snapshot", "--reason", "assert_failure"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["path"] == "/tmp/shot.png"
    assert output["width"] == 640
    call_path, payload = clients[0].calls[-1]
    assert call_path == "capture/screenshot"
    assert payload["reason"] == "assert_failure"


def test_snapshot_missing_capability_returns_error(monkeypatch, tmp_path, capsys):
    patch_bridge(monkeypatch)

    def legacy_capabilities(self):
        return {"ok": True, "capabilities": ["core"]}

    monkeypatch.setattr(FakeClient, "get_capabilities", legacy_capabilities)

    exit_code = cli.main(["--project", str(tmp_path), "snapshot"])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().err)
    assert output["ok"] is False
    assert output["code"] == "bridge_capability_missing"


def test_snapshot_job_failure_surfaces_error_code(monkeypatch, tmp_path, capsys):
    patch_bridge(monkeypatch)

    def fake_wait_for_job(project_path, job_id, timeout_seconds, poll_interval=0.5, initial_info=None, raise_on_failure=True):
        raise cli.JobFailed({"errorCode": "capture_failed", "errorMessage": "boom"})

    monkeypatch.setattr(cli, "wait_for_job", fake_wait_for_job)

    exit_code = cli.main(["--project", str(tmp_path), "snapshot"])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().err)
    assert output["ok"] is False
    assert output["code"] == "capture_failed"
    assert output["message"] == "boom"


def test_snapshot_start_failure_raises_cli_error(monkeypatch, tmp_path, capsys):
    patch_bridge(monkeypatch)

    def denied_capture(self, reason=None, max_long_edge=None, target_directory=None):
        return {"ok": False, "code": "capture_disabled", "message": "disabled"}

    monkeypatch.setattr(FakeClient, "capture_screenshot", denied_capture)

    exit_code = cli.main(["--project", str(tmp_path), "snapshot"])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().err)
    assert output["ok"] is False
    assert output["code"] == "capture_disabled"


def test_click_dispatches_to_client(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(["--project", str(tmp_path), "click", "MainCanvas/StartButton", "--force"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["forced"] is True
    call_path, payload = clients[0].calls[-1]
    assert call_path == "interaction/click"
    assert payload == {"path": "MainCanvas/StartButton", "force": True, "scene": None}


def test_click_occluded_failure_surfaces_as_nonzero_exit(monkeypatch, tmp_path, capsys):
    patch_bridge(monkeypatch)

    def occluded(self, path, force=False, scene=None):
        return {"ok": False, "code": "occluded", "message": "点击被遮挡", "blockedBy": "MainCanvas/Overlay"}

    monkeypatch.setattr(FakeClient, "interaction_click", occluded)

    exit_code = cli.main(["--project", str(tmp_path), "click", "MainCanvas/StartButton"])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is False
    assert output["code"] == "occluded"
    assert output["blockedBy"] == "MainCanvas/Overlay"


def test_click_missing_capability_returns_error(monkeypatch, tmp_path, capsys):
    patch_bridge(monkeypatch)

    def legacy_capabilities(self):
        return {"ok": True, "capabilities": ["core"]}

    monkeypatch.setattr(FakeClient, "get_capabilities", legacy_capabilities)

    exit_code = cli.main(["--project", str(tmp_path), "click", "MainCanvas/StartButton"])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().err)
    assert output["ok"] is False
    assert output["code"] == "bridge_capability_missing"


def test_input_dispatches_text_and_submit(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(
        ["--project", str(tmp_path), "input", "MainCanvas/NameField", "--text", "Alice", "--submit"]
    )

    assert exit_code == 0
    call_path, payload = clients[0].calls[-1]
    assert call_path == "interaction/input"
    assert payload == {"path": "MainCanvas/NameField", "text": "Alice", "submit": True, "scene": None}


def test_set_value_parses_numeric_json_value(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(
        ["--project", str(tmp_path), "set-value", "MainCanvas/VolumeSlider", "--value", "0.5", "--component", "Slider"]
    )

    assert exit_code == 0
    call_path, payload = clients[0].calls[-1]
    assert call_path == "interaction/set-value"
    assert payload == {"path": "MainCanvas/VolumeSlider", "value": 0.5, "component": "Slider", "scene": None}


def test_set_value_parses_object_json_value(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(
        [
            "--project",
            str(tmp_path),
            "set-value",
            "MainCanvas/Scroll",
            "--value",
            '{"x": 0.5, "y": 0.2}',
            "--component",
            "ScrollRect",
        ]
    )

    assert exit_code == 0
    call_path, payload = clients[0].calls[-1]
    assert payload["value"] == {"x": 0.5, "y": 0.2}


def test_set_value_falls_back_to_raw_string_on_invalid_json(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(
        ["--project", str(tmp_path), "set-value", "MainCanvas/Field", "--value", "not-json", "--component", "Dropdown"]
    )

    assert exit_code == 0
    call_path, payload = clients[0].calls[-1]
    assert payload["value"] == "not-json"


def test_parse_value_arg_handles_bool_and_json_decode_error():
    assert cli._parse_value_arg("true") is True
    assert cli._parse_value_arg("not-json") == "not-json"


def test_gameplay_list_dispatches_to_client(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(["--project", str(tmp_path), "gameplay", "list"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert ("gameplay/commands", None) in clients[0].calls


def test_gameplay_invoke_parses_args_json(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(
        ["--project", str(tmp_path), "gameplay", "invoke", "CheatManager.AddGold", "--args", '{"amount": 100}']
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["result"] == 101
    call_path, payload = clients[0].calls[-1]
    assert call_path == "gameplay/invoke"
    assert payload == {"command": "CheatManager.AddGold", "args": {"amount": 100}}


def test_gameplay_invoke_without_args_defaults_to_empty_object(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(["--project", str(tmp_path), "gameplay", "invoke", "CheatManager.Reset"])

    assert exit_code == 0
    call_path, payload = clients[0].calls[-1]
    assert payload == {"command": "CheatManager.Reset", "args": {}}


def test_gameplay_invoke_invalid_json_args_raises_cli_error(monkeypatch, tmp_path, capsys):
    patch_bridge(monkeypatch)

    exit_code = cli.main(
        ["--project", str(tmp_path), "gameplay", "invoke", "CheatManager.AddGold", "--args", "not-json"]
    )

    assert exit_code == 1
    output = json.loads(capsys.readouterr().err)
    assert output["ok"] is False
    assert output["code"] == "invalid_argument"


def test_gameplay_invoke_non_object_args_raises_cli_error(monkeypatch, tmp_path, capsys):
    patch_bridge(monkeypatch)

    exit_code = cli.main(
        ["--project", str(tmp_path), "gameplay", "invoke", "CheatManager.AddGold", "--args", "[1, 2]"]
    )

    assert exit_code == 1
    output = json.loads(capsys.readouterr().err)
    assert output["ok"] is False
    assert output["code"] == "invalid_argument"


def test_gameplay_missing_capability_returns_error(monkeypatch, tmp_path, capsys):
    patch_bridge(monkeypatch)

    def legacy_capabilities(self):
        return {"ok": True, "capabilities": ["core"]}

    monkeypatch.setattr(FakeClient, "get_capabilities", legacy_capabilities)

    exit_code = cli.main(["--project", str(tmp_path), "gameplay", "list"])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().err)
    assert output["ok"] is False
    assert output["code"] == "bridge_capability_missing"


def test_gameplay_invoke_failure_surfaces_as_nonzero_exit(monkeypatch, tmp_path, capsys):
    patch_bridge(monkeypatch)

    def disabled(self, command, args=None):
        return {"ok": False, "code": "gameplay_disabled", "message": "disabled"}

    monkeypatch.setattr(FakeClient, "gameplay_invoke", disabled)

    exit_code = cli.main(["--project", str(tmp_path), "gameplay", "invoke", "Foo.Bar"])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is False
    assert output["code"] == "gameplay_disabled"


def test_record_start_dispatches_without_target_directory_by_default(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(["--project", str(tmp_path), "record", "start"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert ("recording/start", {"targetDirectory": None}) in clients[0].calls


def test_record_start_with_latest_resolves_session_artifacts_directory(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)
    project = make_unity_project(tmp_path)
    session = project / ".unity-agent" / "sessions" / "2026-07-06_100000_s1"
    session.mkdir(parents=True)

    exit_code = cli.main(["--project", str(project), "record", "start", "--latest"])

    assert exit_code == 0
    call_path, payload = clients[0].calls[-1]
    assert call_path == "recording/start"
    assert payload == {"targetDirectory": str(session / "artifacts")}


def test_record_start_with_session_path_resolves_artifacts_directory(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)
    session = tmp_path / "some-session"
    session.mkdir()

    exit_code = cli.main(
        ["--project", str(tmp_path), "record", "start", "--session-path", str(session)]
    )

    assert exit_code == 0
    call_path, payload = clients[0].calls[-1]
    assert call_path == "recording/start"
    assert payload == {"targetDirectory": str(session / "artifacts")}


def test_record_start_with_target_directory_and_latest_raises_invalid_argument(monkeypatch, tmp_path, capsys):
    patch_bridge(monkeypatch)
    project = make_unity_project(tmp_path)
    session = project / ".unity-agent" / "sessions" / "2026-07-06_100000_s1"
    session.mkdir(parents=True)

    exit_code = cli.main(
        ["--project", str(project), "record", "start", "--latest", "--target-directory", "/tmp/whatever"]
    )

    assert exit_code == 1
    output = json.loads(capsys.readouterr().err)
    assert output["ok"] is False
    assert output["code"] == "invalid_argument"


def test_record_stop_dispatches_to_client(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(["--project", str(tmp_path), "record", "stop"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["actionCount"] == 3
    assert ("recording/stop", None) in clients[0].calls


def test_record_status_dispatches_to_client(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(["--project", str(tmp_path), "record", "status"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["recording"] is True
    assert ("recording/status", None) in clients[0].calls


def test_record_missing_capability_returns_error(monkeypatch, tmp_path, capsys):
    patch_bridge(monkeypatch)

    def legacy_capabilities(self):
        return {"ok": True, "capabilities": ["core"]}

    monkeypatch.setattr(FakeClient, "get_capabilities", legacy_capabilities)

    exit_code = cli.main(["--project", str(tmp_path), "record", "status"])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().err)
    assert output["ok"] is False
    assert output["code"] == "bridge_capability_missing"


def test_record_start_failure_surfaces_as_nonzero_exit(monkeypatch, tmp_path, capsys):
    patch_bridge(monkeypatch)

    def already_recording(self, target_directory=None):
        return {"ok": False, "code": "already_recording", "message": "already recording"}

    monkeypatch.setattr(FakeClient, "recording_start", already_recording)

    exit_code = cli.main(["--project", str(tmp_path), "record", "start"])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is False
    assert output["code"] == "already_recording"


def test_profile_start_dispatches_without_target_directory_by_default(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(["--project", str(tmp_path), "profile", "start"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert ("profiling/start", {"targetDirectory": None}) in clients[0].calls


def test_profile_start_with_latest_resolves_session_artifacts_directory(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)
    project = make_unity_project(tmp_path)
    session = project / ".unity-agent" / "sessions" / "2026-07-06_100000_s1"
    session.mkdir(parents=True)

    exit_code = cli.main(["--project", str(project), "profile", "start", "--latest"])

    assert exit_code == 0
    call_path, payload = clients[0].calls[-1]
    assert call_path == "profiling/start"
    assert payload == {"targetDirectory": str(session / "artifacts")}


def test_profile_start_with_target_directory_and_latest_raises_invalid_argument(monkeypatch, tmp_path, capsys):
    patch_bridge(monkeypatch)
    project = make_unity_project(tmp_path)
    session = project / ".unity-agent" / "sessions" / "2026-07-06_100000_s1"
    session.mkdir(parents=True)

    exit_code = cli.main(
        ["--project", str(project), "profile", "start", "--latest", "--target-directory", "/tmp/whatever"]
    )

    assert exit_code == 1
    output = json.loads(capsys.readouterr().err)
    assert output["ok"] is False
    assert output["code"] == "invalid_argument"


def test_profile_stop_dispatches_to_client(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(["--project", str(tmp_path), "profile", "stop"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["frameCount"] == 120
    assert output["aggregates"]["frameTimeMs"]["avg"] == 16.2
    assert ("profiling/stop", None) in clients[0].calls


def test_profile_status_dispatches_to_client(monkeypatch, tmp_path, capsys):
    clients, _, _, _ = patch_bridge(monkeypatch)

    exit_code = cli.main(["--project", str(tmp_path), "profile", "status"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["profiling"] is True
    assert ("profiling/status", None) in clients[0].calls


def test_profile_missing_capability_returns_error(monkeypatch, tmp_path, capsys):
    patch_bridge(monkeypatch)

    def legacy_capabilities(self):
        return {"ok": True, "capabilities": ["core"]}

    monkeypatch.setattr(FakeClient, "get_capabilities", legacy_capabilities)

    exit_code = cli.main(["--project", str(tmp_path), "profile", "status"])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().err)
    assert output["ok"] is False
    assert output["code"] == "bridge_capability_missing"


def test_profile_start_failure_surfaces_as_nonzero_exit(monkeypatch, tmp_path, capsys):
    patch_bridge(monkeypatch)

    def already_profiling(self, target_directory=None):
        return {"ok": False, "code": "already_profiling", "message": "already profiling"}

    monkeypatch.setattr(FakeClient, "profiling_start", already_profiling)

    exit_code = cli.main(["--project", str(tmp_path), "profile", "start"])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is False
    assert output["code"] == "already_profiling"


def test_scenario_validate_reports_errors_for_invalid_file(tmp_path, capsys):
    scenario_file = tmp_path / "bad.json"
    scenario_file.write_text(json.dumps({"steps": []}), encoding="utf-8")

    exit_code = cli.main(["scenario", "validate", str(scenario_file)])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is False
    assert output["code"] == "invalid_scenario"
    assert len(output["errors"]) >= 1


def test_scenario_validate_passes_for_well_formed_scenario(tmp_path, capsys):
    scenario_file = tmp_path / "good.json"
    scenario_file.write_text(
        json.dumps({"name": "x", "steps": [{"action": "play"}, {"action": "stop"}]}), encoding="utf-8"
    )

    exit_code = cli.main(["scenario", "validate", str(scenario_file)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["errors"] == []


def test_scenario_from_recording_writes_draft_file(tmp_path, capsys):
    actions_file = tmp_path / "actions.jsonl"
    meta_file = tmp_path / "recording-meta.json"
    meta_file.write_text(json.dumps({"activeScene": "Main", "sessionId": "s1"}), encoding="utf-8")
    actions_file.write_text(
        json.dumps(
            {
                "time": 0.1,
                "frame": 1,
                "type": "click",
                "scene": "Main",
                "path": "A/B",
                "screenPos": {"x": 1, "y": 2},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output_file = tmp_path / "draft.json"

    exit_code = cli.main(["scenario", "from-recording", str(actions_file), "-o", str(output_file)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["outputPath"] == str(output_file)
    assert output_file.exists()
    written = json.loads(output_file.read_text(encoding="utf-8"))
    assert written["steps"][0] == {"action": "open-scene", "scene": "Main"}
    assert written["steps"][-1] == {"action": "stop"}


def test_scenario_from_recording_requires_meta_file(tmp_path, capsys):
    actions_file = tmp_path / "actions.jsonl"
    actions_file.write_text("", encoding="utf-8")

    exit_code = cli.main(["scenario", "from-recording", str(actions_file)])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().err)
    assert output["ok"] is False
    assert output["code"] == "invalid_scenario"


def _write_scenario_file(path, gold_expectation):
    path.write_text(
        json.dumps(
            {
                "name": "cli-integration",
                "steps": [
                    {"action": "click", "path": "A/Button"},
                    {
                        "action": "assert",
                        "id": "gold",
                        "gameplay": {"command": "Cheat.AddGold", "equals": gold_expectation},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def test_scenario_run_creates_session_and_writes_artifacts(monkeypatch, tmp_path, capsys):
    patch_bridge(monkeypatch)
    project = make_unity_project(tmp_path)
    scenario_file = project / "login-flow.json"
    # FakeClient.gameplay_invoke 固定返回 result=101。
    _write_scenario_file(scenario_file, gold_expectation=101)

    exit_code = cli.main(["--project", str(project), "scenario", "run", str(scenario_file)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["scenario"]["status"] == "passed"
    assert output["scenario"]["stepsFailed"] == 0
    assert output["summary"]["scenario"]["name"] == "cli-integration"
    assert output["summary"]["status"] == "passed"

    session_path = Path(output["sessionPath"])
    assert (session_path / "artifacts" / "scenario-result.json").exists()
    assert (session_path / "summary.json").exists()


def test_scenario_run_exit_code_1_when_assertion_fails(monkeypatch, tmp_path, capsys):
    patch_bridge(monkeypatch)
    project = make_unity_project(tmp_path)
    scenario_file = project / "login-flow.json"
    _write_scenario_file(scenario_file, gold_expectation=999)

    exit_code = cli.main(["--project", str(project), "scenario", "run", str(scenario_file)])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is False
    assert output["code"] == "scenario_failed"
    assert output["scenario"]["status"] == "failed"
    assert output["scenario"]["stepsFailed"] == 1
    assert output["summary"]["status"] == "failed"


def test_scenario_run_invalid_scenario_raises_before_creating_session(monkeypatch, tmp_path, capsys):
    patch_bridge(monkeypatch)
    project = make_unity_project(tmp_path)
    scenario_file = project / "bad.json"
    scenario_file.write_text(json.dumps({"name": "x", "steps": [{"action": "teleport"}]}), encoding="utf-8")

    exit_code = cli.main(["--project", str(project), "scenario", "run", str(scenario_file)])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().err)
    assert output["ok"] is False
    assert output["code"] == "invalid_scenario"
    assert not (project / ".unity-agent" / "sessions").exists()
