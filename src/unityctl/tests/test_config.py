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
    read_jsonc,
    resolve_effective_config,
    validate_project_config,
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


def test_init_project_config_writes_jsonc_templates_without_required_args(tmp_path):
    project = make_unity_project(tmp_path / "Game")

    result = init_project_config(project_path=project)

    config_path = project / ".unity-agent" / "config.jsonc"
    local_config_path = project / ".unity-agent" / "config.local.jsonc"
    shared_text = config_path.read_text(encoding="utf-8")
    local_text = local_config_path.read_text(encoding="utf-8")
    shared = read_jsonc(config_path)
    local = read_jsonc(local_config_path)
    assert result.project_path == project
    assert result.created_paths == [config_path, local_config_path]
    assert result.kept_paths == []
    assert "// 项目级配置" in shared_text
    assert "// 本机配置" in local_text
    assert shared == {
        "version": 1,
        "unityVersion": None,
        "bridge": {"host": "127.0.0.1", "port": 17890},
        "defaultScene": None,
        "sessionDirectory": ".unity-agent/sessions",
    }
    assert local == {"unityExecutablePath": None}


def test_init_project_config_keeps_existing_files_and_only_creates_missing(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    agent_dir = project / ".unity-agent"
    agent_dir.mkdir()
    config_path = agent_dir / "config.jsonc"
    config_path.write_text("// 手写配置\n{\"version\": 1}\n", encoding="utf-8")

    result = init_project_config(project_path=project)

    local_config_path = agent_dir / "config.local.jsonc"
    assert config_path.read_text(encoding="utf-8") == "// 手写配置\n{\"version\": 1}\n"
    assert local_config_path.exists()
    assert result.created_paths == [local_config_path]
    assert result.kept_paths == [config_path]


def test_append_gitignore_entry_adds_missing_line_once(tmp_path):
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("Library/\n", encoding="utf-8")

    append_gitignore_entry(gitignore, ".unity-agent/config.local.jsonc")
    append_gitignore_entry(gitignore, ".unity-agent/config.local.jsonc")

    assert gitignore.read_text(encoding="utf-8").splitlines() == [
        "Library/",
        ".unity-agent/config.local.jsonc",
    ]


def test_resolve_effective_config_merges_project_and_local_config(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    init_project_config(
        project_path=project,
        unity_version="2022.3.62f2",
        host="127.0.0.1",
        port=17891,
        default_scene=None,
    )
    (project / ".unity-agent" / "config.local.jsonc").write_text(
        '{\n  "unityExecutablePath": "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity"\n}\n',
        encoding="utf-8",
    )

    config = resolve_effective_config(project_path=project)

    assert config.project_path == project
    assert config.bridge_url == "http://127.0.0.1:17891"
    assert config.unity_version == "2022.3.62f2"
    assert config.unity_executable_path == Path(
        "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity"
    )


def test_resolve_effective_config_allows_cli_overrides(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    init_project_config(
        project_path=project,
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


def test_read_jsonc_allows_comments_and_trailing_commas(tmp_path):
    path = tmp_path / "config.jsonc"
    path.write_text(
        """
        // 中文注释
        {
          "version": 1,
          "bridge": {
            "host": "127.0.0.1",
            "port": 17891,
          },
        }
        """,
        encoding="utf-8",
    )

    assert read_jsonc(path)["bridge"]["port"] == 17891


def test_validate_project_config_reports_missing_unity_executable(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    init_project_config(project_path=project)

    result = validate_project_config(project)

    assert result.ok is False
    assert result.errors[0].field == "config.local.unityExecutablePath"


def test_find_latest_session_path_uses_session_directory_name(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    old_session = project / ".unity-agent" / "sessions" / "2026-07-01_100000_old"
    new_session = project / ".unity-agent" / "sessions" / "2026-07-02_100000_new"
    old_session.mkdir(parents=True)
    new_session.mkdir(parents=True)

    assert find_latest_session_path(project) == new_session
