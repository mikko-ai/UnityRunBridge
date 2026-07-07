import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from unityctl.discovery import BridgeInfo
from unityctl.jobs import JobEditorExited, JobFailed, JobTimeout, wait_for_job


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


class ScriptedJobServer:
    """按脚本化的 job 状态序列依次响应 GET /jobs/{id}。"""

    def __init__(self, jobs):
        self.jobs = list(jobs)
        self.index = 0
        self.lock = threading.Lock()

        jobs_ref = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if not self.path.startswith("/jobs/"):
                    self.send_response(404)
                    self.end_headers()
                    return

                with jobs_ref.lock:
                    if jobs_ref.index >= len(jobs_ref.jobs):
                        job = jobs_ref.jobs[-1]
                    else:
                        job = jobs_ref.jobs[jobs_ref.index]
                        jobs_ref.index += 1

                body = json.dumps({"ok": True, "job": job}).encode("utf-8")
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
def job_server_factory():
    servers = []

    def factory(jobs):
        server = ScriptedJobServer(jobs)
        server.start()
        servers.append(server)
        return server

    yield factory

    for server in servers:
        server.stop()


def test_wait_for_job_returns_succeeded_job(tmp_path, job_server_factory):
    project = make_unity_project(tmp_path / "Game")
    server = job_server_factory(
        [
            {"id": "job-1", "kind": "screenshot", "status": "running"},
            {"id": "job-1", "kind": "screenshot", "status": "running"},
            {"id": "job-1", "kind": "screenshot", "status": "succeeded", "result": {"path": "a.png"}},
        ]
    )
    write_bridge_info(project, pid=os.getpid(), port=server.port)

    job = wait_for_job(project, "job-1", timeout_seconds=5, poll_interval=0.05)

    assert job["status"] == "succeeded"
    assert job["result"]["path"] == "a.png"


def test_wait_for_job_raises_job_failed_by_default(tmp_path, job_server_factory):
    project = make_unity_project(tmp_path / "Game")
    server = job_server_factory(
        [{"id": "job-1", "kind": "screenshot", "status": "failed", "errorCode": "capture_failed", "errorMessage": "boom"}]
    )
    write_bridge_info(project, pid=os.getpid(), port=server.port)

    with pytest.raises(JobFailed) as exc:
        wait_for_job(project, "job-1", timeout_seconds=5, poll_interval=0.05)

    assert exc.value.job["errorCode"] == "capture_failed"


def test_wait_for_job_returns_failed_job_when_raise_on_failure_false(tmp_path, job_server_factory):
    project = make_unity_project(tmp_path / "Game")
    server = job_server_factory(
        [{"id": "job-1", "kind": "screenshot", "status": "failed", "errorCode": "capture_failed"}]
    )
    write_bridge_info(project, pid=os.getpid(), port=server.port)

    job = wait_for_job(project, "job-1", timeout_seconds=5, poll_interval=0.05, raise_on_failure=False)

    assert job["status"] == "failed"


def test_wait_for_job_raises_timeout_when_deadline_passes(tmp_path, job_server_factory):
    project = make_unity_project(tmp_path / "Game")
    server = job_server_factory([{"id": "job-1", "kind": "screenshot", "status": "running"}])
    write_bridge_info(project, pid=os.getpid(), port=server.port)

    with pytest.raises(JobTimeout):
        wait_for_job(project, "job-1", timeout_seconds=0.2, poll_interval=0.05)


def test_wait_for_job_raises_editor_exited_when_pid_dead_after_connection_failure(tmp_path):
    project = make_unity_project(tmp_path / "Game")
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

    with pytest.raises(JobEditorExited):
        wait_for_job(project, "job-1", timeout_seconds=1, poll_interval=0.05, initial_info=info)
