"""Read-only local view of a Scenario run and its recorded frames."""

import hmac
import json
import os
import re
import secrets
import stat
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import unquote

from unityctl.client import BridgeClient, BridgeClientError
from unityctl.config import ConfigError
from unityctl.discovery import DiscoveryError, is_pid_alive, read_bridge_info
from unityctl.run_events import EVENT_FILE

_ASSETS = {
    "": ("index.html", "text/html; charset=utf-8"),
    "watch.css": ("watch.css", "text/css; charset=utf-8"),
    "watch.js": ("watch.js", "text/javascript; charset=utf-8"),
}
_SESSION = re.compile(r"[\w.-]{1,160}")
_FRAME = re.compile(r"[\w.-]{1,160}\.png")
_EVENT_LIMIT = 2 * 1024 * 1024
_FRAME_LIMIT = 25 * 1024 * 1024


def _ordinary_file(path: Path, limit: int) -> bytes:
    # A watched project's contents are not authority to read other local files.
    if path.is_symlink():
        raise OSError("symlink")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as stream:
        mode = os.fstat(stream.fileno()).st_mode
        if not stat.S_ISREG(mode):
            raise OSError("not a regular file")
        result = stream.read(limit + 1)
    if len(result) > limit:
        raise OSError("file too large")
    return result


def select_session(project: Path, session_id: str | None = None) -> Path | None:
    if session_id is not None and (not _SESSION.fullmatch(session_id) or session_id in {".", ".."}):
        return None
    state_dir = project / ".unity-agent"
    sessions = state_dir / "sessions"
    if state_dir.is_symlink() or sessions.is_symlink() or not sessions.is_dir():
        return None
    candidates = [sessions / session_id] if session_id else sorted(sessions.iterdir(), reverse=True)
    for candidate in candidates:
        if candidate.name in {".", ".."} or not _SESSION.fullmatch(candidate.name):
            continue
        event_path = candidate / EVENT_FILE
        if not candidate.is_symlink() and candidate.is_dir() and not event_path.is_symlink() and event_path.is_file():
            return candidate
    return None


def read_events(session: Path) -> list[dict]:
    raw = _ordinary_file(session / EVENT_FILE, _EVENT_LIMIT)
    records = []
    # An open append may be visible before its newline; leave that row for the next poll.
    for line in raw.split(b"\n")[:-1]:
        row = json.loads(line)
        if isinstance(row, dict) and row.get("schemaVersion") == 1:
            records.append(row)
    return records


def _attach_editor(project: Path) -> dict:
    try:
        info = read_bridge_info(project)
        if info.pid > 0 and is_pid_alive(info.pid):
            response = BridgeClient(info.base_url, info.token, timeout_seconds=0.8).get_status()
            if response.get("ok") is True:
                return {"online": True, "state": response.get("editorState")}
    except (DiscoveryError, BridgeClientError, ConfigError, OSError):
        pass
    return {"online": False, "state": None}


def _run_status(events: list[dict]) -> str:
    if not events:
        return "waiting"
    if events[-1].get("type") == "run-finished":
        return events[-1].get("status", "unknown")
    if events[0].get("kind") == "agent":
        pending = events[-1]
        if pending.get("type") == "step-started":
            owner = pending.get("stepPid")
            if type(owner) is int and owner > 0 and not is_pid_alive(owner):
                return "interrupted"
        return "running"
    pid = events[0].get("runnerPid")
    if type(pid) is int and pid > 0:
        return "running" if is_pid_alive(pid) else "interrupted"
    return "unknown"


def _frame_for(project: Path, session_id: str, frame: str) -> bytes:
    session = select_session(project, session_id)
    if not session or not _FRAME.fullmatch(frame):
        raise OSError("not found")
    if not any(row.get("frame") == frame for row in read_events(session)):
        raise OSError("frame not indexed")
    artifacts = session / "artifacts"
    if artifacts.is_symlink() or not artifacts.is_dir():
        raise OSError("not a regular artifact directory")
    result = _ordinary_file(artifacts / frame, _FRAME_LIMIT)
    if not result.startswith(b"\x89PNG\r\n\x1a\n"):
        raise OSError("invalid PNG")
    return result


def create_watch_server(project: Path, port: int = 0, session_id: str | None = None):
    if session_id is not None and (not _SESSION.fullmatch(session_id) or session_id in {".", ".."}):
        raise ValueError("无效的会话 ID")
    key = secrets.token_urlsafe(24)
    resource = files("unityctl").joinpath("watch_assets")
    assets = {route: (resource.joinpath(filename).read_bytes(), media_type)
              for route, (filename, media_type) in _ASSETS.items()}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            # Do not log secret URL paths or project identities.
            pass

        def _reply(self, status, media_type, body):
            self.send_response(status)
            self.send_header("Content-Type", media_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; script-src 'self'; style-src 'self'; "
                             "img-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            expected_host = f"127.0.0.1:{self.server.server_port}"
            prefix, separator, route = self.path.removeprefix("/").partition("/")
            if (self.headers.get("Host") != expected_host or not separator
                    or not prefix.isascii() or not hmac.compare_digest(prefix, key)):
                return self._reply(404, "text/plain", b"Not found")
            if route in assets:
                body, media_type = assets[route]
                return self._reply(200, media_type, body)
            try:
                if route == "state":
                    session = select_session(project, session_id)
                    events = read_events(session) if session else []
                    result = {"sessionId": session.name if session else None, "status": _run_status(events),
                              "events": events, "editor": _attach_editor(project)}
                    return self._reply(200, "application/json", json.dumps(result, ensure_ascii=False).encode())
                parts = route.split("/")
                if len(parts) == 3 and parts[0] == "frame":
                    return self._reply(200, "image/png", _frame_for(project, unquote(parts[1], errors="strict"), unquote(parts[2], errors="strict")))
            except (OSError, ValueError):
                if route == "state":
                    return self._reply(503, "application/json", b'{"code":"observation_unavailable"}')
            return self._reply(404, "text/plain", b"Not found")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    return server, f"http://127.0.0.1:{server.server_port}/{key}/"
