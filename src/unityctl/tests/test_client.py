import json
from urllib.error import HTTPError

import pytest

from unityctl.client import BridgeClient, BridgeClientError, BridgeUnreachableError


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


def test_get_status_sends_token_header(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, request.get_method(), request.headers, timeout))
        return FakeResponse(200, {"ok": True, "code": "ok", "isPlaying": False})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token", timeout_seconds=2.0)
    result = client.get_status()

    assert result == {"ok": True, "code": "ok", "isPlaying": False}
    url, method, headers, timeout = calls[0]
    assert url == "http://127.0.0.1:17890/status"
    assert method == "GET"
    assert headers["X-bridge-token"] == "secret-token"
    assert timeout == 2.0


def test_post_command_sends_token_header(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, request.get_method(), request.headers, request.data))
        return FakeResponse(200, {"ok": True, "code": "accepted", "message": "entered play mode"})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")
    result = client.post("play")

    assert result == {"ok": True, "code": "accepted", "message": "entered play mode"}
    url, method, headers, data = calls[0]
    assert url == "http://127.0.0.1:17890/play"
    assert method == "POST"
    assert headers["X-bridge-token"] == "secret-token"
    assert data == b"{}"


def test_open_scene_sends_scene_path(monkeypatch):
    captured_body = []

    def fake_urlopen(request, timeout):
        captured_body.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(200, {"ok": True, "code": "accepted", "scenePath": "Assets/Scenes/Login.unity"})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")
    result = client.open_scene("Assets/Scenes/Login.unity")

    assert captured_body == [{"scenePath": "Assets/Scenes/Login.unity"}]
    assert result["ok"] is True


def test_http_error_extracts_code_and_message_from_envelope(monkeypatch):
    error_body = json.dumps({"ok": False, "code": "busy", "message": "editor is compiling"}).encode("utf-8")

    def fake_urlopen(request, timeout):
        raise HTTPError(
            url=request.full_url,
            code=409,
            msg="Conflict",
            hdrs=None,
            fp=__import__("io").BytesIO(error_body),
        )

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")

    with pytest.raises(BridgeClientError) as exc:
        client.post("play")

    assert exc.value.code == "busy"
    assert "editor is compiling" in str(exc.value)


def test_http_error_without_envelope_falls_back_to_status_line(monkeypatch):
    def fake_urlopen(request, timeout):
        raise HTTPError(
            url=request.full_url,
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")

    with pytest.raises(BridgeClientError) as exc:
        client.post("play")

    assert exc.value.code == "internal_error"
    assert "HTTP 500" in str(exc.value)


def test_connection_error_becomes_bridge_unreachable_error(monkeypatch):
    from urllib.error import URLError

    def fake_urlopen(request, timeout):
        raise URLError("connection refused")

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")

    with pytest.raises(BridgeUnreachableError) as exc:
        client.get_status()

    assert exc.value.code == "bridge_unreachable"


def test_start_session_posts_session_payload(monkeypatch):
    captured_body = []

    def fake_urlopen(request, timeout):
        captured_body.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(200, {"ok": True, "code": "session_started", "sessionId": "s1"})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")
    result = client.start_session("s1", "/tmp/project/.unity-agent/sessions/s1")

    assert result == {"ok": True, "code": "session_started", "sessionId": "s1"}
    assert captured_body == [
        {"sessionId": "s1", "sessionPath": "/tmp/project/.unity-agent/sessions/s1"}
    ]


def test_end_session_posts_empty_payload(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, request.get_method(), request.data))
        return FakeResponse(200, {"ok": True, "code": "session_ended", "message": "session ended"})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")
    result = client.end_session()

    assert result == {"ok": True, "code": "session_ended", "message": "session ended"}
    assert calls == [("http://127.0.0.1:17890/session/end", "POST", b"{}")]


def test_refresh_posts_to_refresh_route(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, request.get_method()))
        return FakeResponse(200, {"ok": True, "code": "accepted"})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")
    result = client.refresh()

    assert result == {"ok": True, "code": "accepted"}
    assert calls == [("http://127.0.0.1:17890/refresh", "POST")]
