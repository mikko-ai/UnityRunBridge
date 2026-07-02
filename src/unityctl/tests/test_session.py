import json
from datetime import datetime, timezone

from unityctl.session import create_session, make_session_id, mark_session_failed


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
        editor_pid=4321,
        unity_version="2022.3.62f2",
    )

    assert session.session_id == "2026-06-30_183012_login-flow"
    assert session.session_path == (
        project / ".unity-agent" / "sessions" / "2026-06-30_183012_login-flow"
    )
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
        "failedReason": None,
        "editorPid": 4321,
        "unityVersion": "2022.3.62f2",
    }


def test_mark_session_failed_sets_status_and_reason(tmp_path):
    project = tmp_path / "Game"
    project.mkdir()
    created_at = datetime(2026, 6, 30, 18, 30, 12, tzinfo=timezone.utc)

    session = create_session(
        project_path=project,
        name="login-flow",
        scene_path=None,
        trigger="agent",
        task="",
        created_at=created_at,
    )

    payload = mark_session_failed(
        session.session_path, "compilation_failed", ended_at="2026-06-30T18:31:00Z"
    )

    assert payload["status"] == "failed"
    assert payload["failedReason"] == "compilation_failed"
    assert payload["endedAt"] == "2026-06-30T18:31:00Z"

    persisted = json.loads(session.session_json_path.read_text(encoding="utf-8"))
    assert persisted["status"] == "failed"
    assert persisted["failedReason"] == "compilation_failed"
