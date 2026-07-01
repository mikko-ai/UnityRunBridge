import json

from unityctl import cli


class FakeClient:
    def __init__(self, base_url):
        self.base_url = base_url
        self.calls = []

    def get_status(self):
        self.calls.append(("status", None))
        return {"ok": True, "isPlaying": False}

    def post(self, path, payload=None):
        self.calls.append((path, payload))
        return {"ok": True, "command": path}

    def open_scene(self, scene_path):
        self.calls.append(("open-scene", {"scenePath": scene_path}))
        return {"ok": True, "scenePath": scene_path}


def test_status_command_prints_json(monkeypatch, capsys):
    clients = []

    def fake_client(base_url):
        client = FakeClient(base_url)
        clients.append(client)
        return client

    monkeypatch.setattr(cli, "BridgeClient", fake_client)

    exit_code = cli.main(["status"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "isPlaying": False}
    assert clients[0].calls == [("status", None)]


def test_play_command_posts_play(monkeypatch):
    clients = []

    def fake_client(base_url):
        client = FakeClient(base_url)
        clients.append(client)
        return client

    monkeypatch.setattr(cli, "BridgeClient", fake_client)

    assert cli.main(["play"]) == 0
    assert clients[0].calls == [("play", None)]


def test_open_scene_command_sends_path(monkeypatch):
    clients = []

    def fake_client(base_url):
        client = FakeClient(base_url)
        clients.append(client)
        return client

    monkeypatch.setattr(cli, "BridgeClient", fake_client)

    assert cli.main(["open-scene", "Assets/Scenes/Login.unity"]) == 0
    assert clients[0].calls == [
        ("open-scene", {"scenePath": "Assets/Scenes/Login.unity"})
    ]


def test_play_with_session_creates_session_and_starts_bridge(
    monkeypatch, tmp_path, capsys
):
    clients = []

    def fake_client(base_url):
        client = FakeClient(base_url)
        client.start_session = (
            lambda session_id, session_path: client.calls.append(
                (
                    "session/start",
                    {"sessionId": session_id, "sessionPath": session_path},
                )
            )
            or {"ok": True}
        )
        clients.append(client)
        return client

    monkeypatch.setattr(cli, "BridgeClient", fake_client)
    monkeypatch.setattr(
        cli,
        "utc_now",
        lambda: cli.datetime.fromisoformat("2026-06-30T18:30:12+00:00"),
    )

    project = tmp_path / "Game"
    project.mkdir()

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
    assert output["sessionId"] == "2026-06-30_183012_login-flow"
    assert (
        project
        / ".unity-agent"
        / "sessions"
        / "2026-06-30_183012_login-flow"
        / "session.json"
    ).exists()
    assert clients[0].calls[0][0] == "session/start"
    assert clients[0].calls[1] == ("play", None)


def test_summary_command_prints_summary_file(tmp_path, capsys):
    session = tmp_path / "s1"
    session.mkdir()
    (session / "summary.json").write_text('{"status":"passed"}', encoding="utf-8")

    exit_code = cli.main(["summary", "--session-path", str(session)])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"status": "passed"}
