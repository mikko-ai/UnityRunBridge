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
    editor_pid: int | None = None,
    unity_version: str | None = None,
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
        "failedReason": None,
        "editorPid": editor_pid,
        "unityVersion": unity_version,
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
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


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


def mark_session_failed(
    session_path: str | Path,
    reason: str,
    ended_at: str | None = None,
) -> dict[str, Any]:
    payload = read_session_json(session_path)
    payload["status"] = "failed"
    payload["failedReason"] = reason
    payload["endedAt"] = ended_at or format_time(utc_now())
    write_session_json(session_path, payload)
    return payload
