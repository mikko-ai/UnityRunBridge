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
