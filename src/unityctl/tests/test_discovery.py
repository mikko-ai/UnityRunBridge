import json
import os
from pathlib import Path

import pytest

from unityctl.discovery import BridgeInfo, DiscoveryError, discover, is_pid_alive, read_bridge_info


def make_unity_project(path: Path) -> Path:
    (path / "Assets").mkdir(parents=True)
    (path / "Packages").mkdir()
    (path / "ProjectSettings").mkdir()
    return path


def write_bridge_info(project: Path, pid: int, port: int = 17890) -> Path:
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
    return bridge_path


def test_read_bridge_info_raises_when_file_missing(tmp_path):
    project = make_unity_project(tmp_path / "Game")

    with pytest.raises(DiscoveryError) as exc:
        read_bridge_info(project)

    assert "unityctl start" in str(exc.value)
    assert exc.value.code == "bridge_unreachable"


def test_read_bridge_info_parses_fields(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    write_bridge_info(project, pid=os.getpid())

    info = read_bridge_info(project)

    assert info == BridgeInfo(
        port=17890,
        pid=os.getpid(),
        token="abc123",
        unity_version="2022.3.62f2",
        project_path=str(project),
        started_at="2026-07-02T09:00:00Z",
    )
    assert info.base_url == "http://127.0.0.1:17890"


def test_read_bridge_info_rejects_unsupported_schema_version(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    bridge_path = project / ".unity-agent" / "bridge.json"
    bridge_path.parent.mkdir(parents=True)
    bridge_path.write_text(
        json.dumps({"schemaVersion": 2, "port": 17890, "pid": 1, "token": "abc"}),
        encoding="utf-8",
    )

    with pytest.raises(DiscoveryError) as exc:
        read_bridge_info(project)

    assert "schemaVersion" in str(exc.value)


def test_read_bridge_info_rejects_out_of_range_port(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    bridge_path = project / ".unity-agent" / "bridge.json"
    bridge_path.parent.mkdir(parents=True)
    bridge_path.write_text(
        json.dumps({"schemaVersion": 1, "port": 70000, "pid": 1, "token": "abc"}),
        encoding="utf-8",
    )

    with pytest.raises(DiscoveryError) as exc:
        read_bridge_info(project)

    assert "端口非法" in str(exc.value)


def test_read_bridge_info_rejects_empty_token(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    bridge_path = project / ".unity-agent" / "bridge.json"
    bridge_path.parent.mkdir(parents=True)
    bridge_path.write_text(
        json.dumps({"schemaVersion": 1, "port": 17890, "pid": 1, "token": ""}),
        encoding="utf-8",
    )

    with pytest.raises(DiscoveryError) as exc:
        read_bridge_info(project)

    assert "token" in str(exc.value)


def test_is_pid_alive_returns_true_for_current_process():
    assert is_pid_alive(os.getpid()) is True


def test_is_pid_alive_returns_false_for_unlikely_pid():
    assert is_pid_alive(2**30) is False


def test_discover_returns_info_when_pid_alive(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    write_bridge_info(project, pid=os.getpid())

    info = discover(project)

    assert info.pid == os.getpid()


def test_discover_cleans_up_stale_file_when_pid_dead(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    bridge_path = write_bridge_info(project, pid=2**30)

    with pytest.raises(DiscoveryError) as exc:
        discover(project)

    assert "已不存在" in str(exc.value)
    assert exc.value.code == "editor_not_running"
    assert not bridge_path.exists()
