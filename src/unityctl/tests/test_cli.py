import json
from pathlib import Path

import pytest

from unityctl import __version__
from unityctl import cli
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


def test_init_command_requires_confirmation_when_not_yes(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")

    exit_code = cli.main(["--project", str(project), "init"])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().err)
    assert "需要确认" in output["error"]
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
