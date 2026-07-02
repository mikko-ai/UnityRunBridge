import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from unityctl.convergence import (
    ConvergenceEditorExited,
    ConvergenceFailed,
    ConvergenceTimeout,
    poll_until,
)
from unityctl.discovery import BridgeInfo


def make_unity_project(path: Path) -> Path:
    (path / "Assets").mkdir(parents=True)
    (path / "Packages").mkdir()
    (path / "ProjectSettings").mkdir()
    return path


def write_bridge_info(project: Path, pid: int, port: int) -> None:
    bridge_path = project / ".unity-agent" / "bridge.json"
    bridge_path.parent.mkdir(parents=True, exist_ok=True)
    bridge_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "port": port,
                "pid": pid,
                "token": "abc123",
                "unityVersion": "2022.3.62f2",
                "projectPath": str(project),
                "startedAt": "2026-07-02T09:00:00Z",
            }
        ),
        encoding="utf-8",
    )


class ScriptedBridgeServer:
    """一个最小假 Bridge：按脚本化的状态序列依次响应 GET /status。"""

    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.index = 0
        self.lock = threading.Lock()

        statuses_ref = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != "/status":
                    self.send_response(404)
                    self.end_headers()
                    return

                with statuses_ref.lock:
                    if statuses_ref.index >= len(statuses_ref.statuses):
                        payload = statuses_ref.statuses[-1]
                    else:
                        payload = statuses_ref.statuses[statuses_ref.index]
                        statuses_ref.index += 1

                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                return

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def bridge_factory():
    servers = []

    def factory(statuses):
        server = ScriptedBridgeServer(statuses)
        server.start()
        servers.append(server)
        return server

    yield factory

    for server in servers:
        server.stop()


def test_poll_until_returns_once_predicate_matches(tmp_path, bridge_factory):
    project = make_unity_project(tmp_path / "Game")
    server = bridge_factory(
        [
            {"editorState": "enteringPlay"},
            {"editorState": "enteringPlay"},
            {"editorState": "playing"},
        ]
    )
    write_bridge_info(project, pid=os.getpid(), port=server.port)

    result = poll_until(
        project,
        predicate=lambda status: status["editorState"] == "playing",
        timeout_seconds=5,
        poll_interval=0.05,
    )

    assert result.status["editorState"] == "playing"


def test_poll_until_raises_timeout_when_deadline_passes(tmp_path, bridge_factory):
    project = make_unity_project(tmp_path / "Game")
    server = bridge_factory([{"editorState": "enteringPlay"}])
    write_bridge_info(project, pid=os.getpid(), port=server.port)

    with pytest.raises(ConvergenceTimeout) as exc:
        poll_until(
            project,
            predicate=lambda status: status["editorState"] == "playing",
            timeout_seconds=0.2,
            poll_interval=0.05,
        )

    assert exc.value.last_status["editorState"] == "enteringPlay"


def test_poll_until_propagates_convergence_failed_from_predicate(tmp_path, bridge_factory):
    project = make_unity_project(tmp_path / "Game")
    server = bridge_factory([{"editorState": "idle", "compilationSucceeded": False}])
    write_bridge_info(project, pid=os.getpid(), port=server.port)

    def predicate(status):
        if status["editorState"] == "idle" and not status["compilationSucceeded"]:
            raise ConvergenceFailed("compilation_failed", status=status)
        return False

    with pytest.raises(ConvergenceFailed) as exc:
        poll_until(project, predicate=predicate, timeout_seconds=5, poll_interval=0.05)

    assert exc.value.reason == "compilation_failed"


def test_poll_until_raises_editor_exited_when_pid_dead_after_connection_failure(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    write_bridge_info(project, pid=os.getpid(), port=1)

    dead_pid = 2**30
    info = BridgeInfo(
        port=1,
        pid=dead_pid,
        token="abc123",
        unity_version="2022.3.62f2",
        project_path=str(project),
        started_at="2026-07-02T09:00:00Z",
    )
    write_bridge_info(project, pid=dead_pid, port=1)

    with pytest.raises(ConvergenceEditorExited):
        poll_until(
            project,
            predicate=lambda status: False,
            timeout_seconds=1,
            poll_interval=0.05,
            initial_info=info,
        )
