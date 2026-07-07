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


def test_get_capabilities_returns_bridge_payload(monkeypatch):
    def fake_urlopen(request, timeout):
        return FakeResponse(
            200,
            {"ok": True, "bridgeVersion": "0.2.0", "capabilities": ["core", "hierarchy"], "routes": []},
        )

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")
    result = client.get_capabilities()

    assert result["capabilities"] == ["core", "hierarchy"]


def test_get_capabilities_falls_back_to_legacy_on_not_found(monkeypatch):
    error_body = json.dumps({"ok": False, "code": "not_found", "message": "unsupported route"}).encode("utf-8")

    def fake_urlopen(request, timeout):
        raise HTTPError(
            url=request.full_url,
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=__import__("io").BytesIO(error_body),
        )

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")
    result = client.get_capabilities()

    assert result == {"ok": True, "bridgeVersion": None, "capabilities": ["core"], "legacy": True}


def test_get_capabilities_reraises_other_errors(monkeypatch):
    error_body = json.dumps({"ok": False, "code": "internal_error", "message": "boom"}).encode("utf-8")

    def fake_urlopen(request, timeout):
        raise HTTPError(
            url=request.full_url,
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=__import__("io").BytesIO(error_body),
        )

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")

    with pytest.raises(BridgeClientError) as exc:
        client.get_capabilities()

    assert exc.value.code == "internal_error"


def test_get_job_requests_job_path(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        return FakeResponse(200, {"ok": True, "job": {"id": "job-1", "status": "succeeded"}})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")
    result = client.get_job("job-1")

    assert calls == ["http://127.0.0.1:17890/jobs/job-1"]
    assert result["job"]["status"] == "succeeded"


def test_hierarchy_roots_requests_roots_path(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        return FakeResponse(200, {"ok": True, "scenes": []})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")
    client.hierarchy_roots()

    assert calls == ["http://127.0.0.1:17890/hierarchy/roots"]


def test_hierarchy_tree_builds_query_string(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        return FakeResponse(200, {"ok": True, "nodes": []})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")
    client.hierarchy_tree(path="MainCanvas/Button", depth=2, pageSize=None, cursor=None, scene=None)

    assert calls == ["http://127.0.0.1:17890/hierarchy/tree?path=MainCanvas%2FButton&depth=2"]


def test_hierarchy_find_omits_none_and_false_values(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        return FakeResponse(200, {"ok": True, "matchedCount": 0, "nodes": []})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")
    client.hierarchy_find(component="Button", missingScript=False, countOnly=True, scene=None)

    assert calls == ["http://127.0.0.1:17890/hierarchy/find?component=Button&countOnly=true"]


def test_hierarchy_ancestors_and_inspect_build_query(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        return FakeResponse(200, {"ok": True})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")
    client.hierarchy_ancestors(path="A/B", component=None)
    client.hierarchy_inspect(path="A/B")

    assert calls == [
        "http://127.0.0.1:17890/hierarchy/ancestors?path=A%2FB",
        "http://127.0.0.1:17890/hierarchy/inspect?path=A%2FB",
    ]


def test_interaction_click_posts_path_and_force(monkeypatch):
    captured_body = []

    def fake_urlopen(request, timeout):
        captured_body.append((request.full_url, json.loads(request.data.decode("utf-8"))))
        return FakeResponse(200, {"ok": True, "clicked": "A/B", "raycastHit": "A/B", "forced": False, "events": []})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")
    result = client.interaction_click("A/B", force=False, scene="Main")

    assert captured_body == [
        ("http://127.0.0.1:17890/interaction/click", {"path": "A/B", "force": False, "scene": "Main"})
    ]
    assert result["ok"] is True


def test_interaction_click_omits_scene_when_not_given(monkeypatch):
    captured_body = []

    def fake_urlopen(request, timeout):
        captured_body.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(200, {"ok": True})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")
    client.interaction_click("A/B")

    assert captured_body == [{"path": "A/B", "force": False}]


def test_interaction_input_posts_text_and_submit(monkeypatch):
    captured_body = []

    def fake_urlopen(request, timeout):
        captured_body.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(200, {"ok": True, "code": "ok", "message": "input applied"})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")
    result = client.interaction_input("A/Field", text="Alice", submit=True)

    assert captured_body == [{"path": "A/Field", "text": "Alice", "submit": True}]
    assert result["ok"] is True


def test_interaction_set_value_posts_value_and_component(monkeypatch):
    captured_body = []

    def fake_urlopen(request, timeout):
        captured_body.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(200, {"ok": True, "component": "ScrollRect"})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")
    result = client.interaction_set_value("A/Scroll", value={"x": 0.5, "y": 0.2}, component="ScrollRect")

    assert captured_body == [
        {"path": "A/Scroll", "value": {"x": 0.5, "y": 0.2}, "component": "ScrollRect"}
    ]
    assert result["component"] == "ScrollRect"


def test_gameplay_list_requests_commands_path(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        return FakeResponse(200, {"ok": True, "commands": []})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")
    result = client.gameplay_list()

    assert calls == ["http://127.0.0.1:17890/gameplay/commands"]
    assert result["ok"] is True


def test_gameplay_invoke_posts_command_and_args(monkeypatch):
    captured_body = []

    def fake_urlopen(request, timeout):
        captured_body.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(200, {"ok": True, "result": 101, "durationMs": 3})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")
    result = client.gameplay_invoke("CheatManager.AddGold", {"amount": 100})

    assert captured_body == [{"command": "CheatManager.AddGold", "args": {"amount": 100}}]
    assert result["result"] == 101


def test_gameplay_invoke_defaults_args_to_empty_object(monkeypatch):
    captured_body = []

    def fake_urlopen(request, timeout):
        captured_body.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(200, {"ok": True, "result": None})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")
    client.gameplay_invoke("CheatManager.Reset")

    assert captured_body == [{"command": "CheatManager.Reset", "args": {}}]


def test_recording_start_posts_target_directory_when_given(monkeypatch):
    captured_body = []

    def fake_urlopen(request, timeout):
        captured_body.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(200, {"ok": True, "actionsPath": "/tmp/actions.jsonl", "metaPath": "/tmp/meta.json"})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")
    result = client.recording_start(target_directory="/tmp/artifacts")

    assert captured_body == [{"targetDirectory": "/tmp/artifacts"}]
    assert result["actionsPath"] == "/tmp/actions.jsonl"


def test_recording_start_omits_target_directory_when_not_given(monkeypatch):
    captured_body = []

    def fake_urlopen(request, timeout):
        captured_body.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(200, {"ok": True})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")
    client.recording_start()

    assert captured_body == [{}]


def test_recording_stop_posts_to_recording_stop_route(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, request.get_method()))
        return FakeResponse(200, {"ok": True, "actionCount": 3, "interrupted": False})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")
    result = client.recording_stop()

    assert calls == [("http://127.0.0.1:17890/recording/stop", "POST")]
    assert result["actionCount"] == 3


def test_recording_status_requests_recording_status_path(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        return FakeResponse(200, {"ok": True, "recording": True})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", token="secret-token")
    result = client.recording_status()

    assert calls == ["http://127.0.0.1:17890/recording/status"]
    assert result["recording"] is True


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
