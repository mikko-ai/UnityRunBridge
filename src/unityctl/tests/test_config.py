import json
from pathlib import Path

import pytest

from unityctl.config import (
    ConfigError,
    append_gitignore_entry,
    build_bridge_url,
    find_latest_session_path,
    find_unity_project_root,
    init_project_config,
    normalize_unity_executable_path,
    resolve_effective_config,
)


def make_unity_project(path: Path) -> Path:
    (path / "Assets").mkdir(parents=True)
    (path / "Packages").mkdir()
    (path / "ProjectSettings").mkdir()
    return path


def test_find_unity_project_root_walks_up_from_child(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    child = project / "Assets" / "Scripts"
    child.mkdir(parents=True)

    assert find_unity_project_root(child) == project


def test_find_unity_project_root_raises_when_missing(tmp_path):
    with pytest.raises(ConfigError) as exc:
        find_unity_project_root(tmp_path)

    assert "Unity project" in str(exc.value)


def test_init_project_config_writes_shared_and_local_config(tmp_path):
    project = make_unity_project(tmp_path / "Game")

    result = init_project_config(
        project_path=project,
        unity_path="/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app",
        unity_version="2022.3.62f2",
        host="127.0.0.1",
        port=17891,
        default_scene="Assets/Scenes/Login.unity",
    )

    shared = json.loads((project / ".unity-agent" / "config.json").read_text())
    local = json.loads((project / ".unity-agent" / "config.local.json").read_text())
    assert result.project_path == project
    assert shared == {
        "version": 1,
        "unityVersion": "2022.3.62f2",
        "bridge": {"host": "127.0.0.1", "port": 17891},
        "defaultScene": "Assets/Scenes/Login.unity",
        "sessionDirectory": ".unity-agent/sessions",
    }
    assert local == {
        "unityAppPath": "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app"
    }


def test_append_gitignore_entry_adds_missing_line_once(tmp_path):
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("Library/\n", encoding="utf-8")

    append_gitignore_entry(gitignore, ".unity-agent/config.local.json")
    append_gitignore_entry(gitignore, ".unity-agent/config.local.json")

    assert gitignore.read_text(encoding="utf-8").splitlines() == [
        "Library/",
        ".unity-agent/config.local.json",
    ]


def test_resolve_effective_config_merges_project_and_local_config(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    init_project_config(
        project_path=project,
        unity_path="/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app",
        unity_version="2022.3.62f2",
        host="127.0.0.1",
        port=17891,
        default_scene=None,
    )

    config = resolve_effective_config(project_path=project)

    assert config.project_path == project
    assert config.bridge_url == "http://127.0.0.1:17891"
    assert config.unity_version == "2022.3.62f2"
    assert config.unity_app_path == Path(
        "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app"
    )
    assert config.unity_executable_path == Path(
        "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity"
    )


def test_resolve_effective_config_allows_cli_overrides(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    init_project_config(
        project_path=project,
        unity_path="/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app",
        unity_version="2022.3.62f2",
        host="127.0.0.1",
        port=17891,
        default_scene=None,
    )

    config = resolve_effective_config(
        project_path=project,
        unity_path="/Applications/Unity/Hub/Editor/6000.0.0f1/Unity.app",
        base_url="http://127.0.0.1:19000",
    )

    assert config.bridge_url == "http://127.0.0.1:19000"
    assert config.unity_executable_path == Path(
        "/Applications/Unity/Hub/Editor/6000.0.0f1/Unity.app/Contents/MacOS/Unity"
    )


def test_normalize_unity_executable_path_accepts_app_bundle():
    assert normalize_unity_executable_path(
        "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app"
    ) == Path("/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity")


def test_build_bridge_url_uses_host_and_port():
    assert build_bridge_url("127.0.0.1", 17891) == "http://127.0.0.1:17891"


def test_find_latest_session_path_uses_session_directory_name(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    old_session = project / ".unity-agent" / "sessions" / "2026-07-01_100000_old"
    new_session = project / ".unity-agent" / "sessions" / "2026-07-02_100000_new"
    old_session.mkdir(parents=True)
    new_session.mkdir(parents=True)

    assert find_latest_session_path(project) == new_session
