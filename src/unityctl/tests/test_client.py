import json
from urllib.error import HTTPError

import pytest

from unityctl.client import BridgeClient, BridgeClientError


class FakeResponse:
    def __init__(self, status: int, payload: dict):
        self.status = status
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_get_status_returns_json(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, request.get_method(), timeout))
        return FakeResponse(200, {"ok": True, "isPlaying": False})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", timeout_seconds=2.0)
    result = client.get_status()

    assert result == {"ok": True, "isPlaying": False}
    assert calls == [("http://127.0.0.1:17890/status", "GET", 2.0)]


def test_post_command_returns_json(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, request.get_method(), request.data))
        return FakeResponse(200, {"ok": True, "message": "entered play mode"})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890")
    result = client.post("play")

    assert result == {"ok": True, "message": "entered play mode"}
    assert calls == [("http://127.0.0.1:17890/play", "POST", b"{}")]


def test_open_scene_sends_scene_path(monkeypatch):
    captured_body = []

    def fake_urlopen(request, timeout):
        captured_body.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(200, {"ok": True, "scenePath": "Assets/Scenes/Login.unity"})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890")
    result = client.open_scene("Assets/Scenes/Login.unity")

    assert captured_body == [{"scenePath": "Assets/Scenes/Login.unity"}]
    assert result["ok"] is True


def test_http_error_becomes_bridge_client_error(monkeypatch):
    def fake_urlopen(request, timeout):
        raise HTTPError(
            url=request.full_url,
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890")

    with pytest.raises(BridgeClientError) as exc:
        client.post("play")

    assert "HTTP 500" in str(exc.value)


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
