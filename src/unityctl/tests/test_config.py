import json
from pathlib import Path

import pytest

from unityctl.config import (
    ConfigError,
    append_gitignore_entry,
    find_latest_session_path,
    find_unity_project_root,
    init_project_config,
    normalize_unity_executable_path,
    read_json,
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


def test_init_project_config_writes_plain_json_without_required_args(tmp_path):
    project = make_unity_project(tmp_path / "Game")

    result = init_project_config(project_path=project)

    config_path = project / ".unity-agent" / "config.json"
    local_config_path = project / ".unity-agent" / "config.local.json"
    shared = read_json(config_path)
    local = read_json(local_config_path)
    assert result.project_path == project
    assert result.created_paths == [config_path, local_config_path]
    assert result.kept_paths == []
    assert result.preferred_port == 17890
    assert shared == {
        "$schema": "schemas/config.schema.json",
        "version": 1,
        "unityVersion": None,
        "bridge": {"preferredPort": 17890},
        "defaultScene": None,
        "timeouts": {
            "playSeconds": 180,
            "stopSeconds": 60,
            "startEditorSeconds": 300,
        },
    }
    assert local == {
        "$schema": "schemas/config.local.schema.json",
        "unityExecutablePath": None,
    }


def test_init_project_config_copies_bundled_schemas(tmp_path):
    project = make_unity_project(tmp_path / "Game")

    init_project_config(project_path=project)

    schemas_dir = project / ".unity-agent" / "schemas"
    assert (schemas_dir / "config.schema.json").exists()
    assert (schemas_dir / "bridge.schema.json").exists()
    assert (schemas_dir / "session.schema.json").exists()


def test_init_project_config_keeps_existing_files_and_only_creates_missing(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    agent_dir = project / ".unity-agent"
    agent_dir.mkdir()
    config_path = agent_dir / "config.json"
    config_path.write_text(json.dumps({"version": 1}), encoding="utf-8")

    result = init_project_config(project_path=project)

    local_config_path = agent_dir / "config.local.json"
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"version": 1}
    assert local_config_path.exists()
    assert result.created_paths == [local_config_path]
    assert result.kept_paths == [config_path]


def test_init_project_config_updates_gitignore_for_all_local_artifacts(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    root_gitignore = project / ".gitignore"
    root_gitignore.write_text("Library/\n", encoding="utf-8")

    init_project_config(project_path=project)

    ignored = (project / ".unity-agent" / ".gitignore").read_text(encoding="utf-8")
    assert "config.local.json" in ignored
    assert "sessions/" in ignored
    assert "bridge.json" in ignored
    assert "scratch/" in ignored
    assert "builds/" in ignored
    assert root_gitignore.read_text(encoding="utf-8") == "Library/\n"


def test_append_gitignore_entry_adds_missing_line_once(tmp_path):
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("Library/\n", encoding="utf-8")

    append_gitignore_entry(gitignore, "config.local.json")
    append_gitignore_entry(gitignore, "config.local.json")

    assert gitignore.read_text(encoding="utf-8").splitlines() == [
        "Library/",
        "config.local.json",
    ]


def test_resolve_effective_config_merges_project_and_local_config(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    init_project_config(
        project_path=project,
        unity_version="2022.3.62f2",
        preferred_port=17891,
    )
    (project / ".unity-agent" / "config.local.json").write_text(
        json.dumps(
            {
                "unityExecutablePath": (
                    "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity"
                )
            }
        ),
        encoding="utf-8",
    )

    config = resolve_effective_config(project_path=project)

    assert config.project_path == project
    assert config.preferred_port == 17891
    assert config.unity_version == "2022.3.62f2"
    assert config.unity_executable_path == Path(
        "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity"
    )
    assert config.timeouts.play_seconds == 180
    assert config.timeouts.stop_seconds == 60
    assert config.timeouts.start_editor_seconds == 300


def test_resolve_effective_config_allows_unity_path_override(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    init_project_config(project_path=project, unity_version="2022.3.62f2")

    config = resolve_effective_config(
        project_path=project,
        unity_path="/Applications/Unity/Hub/Editor/6000.0.0f1/Unity.app",
    )

    assert config.unity_executable_path == Path(
        "/Applications/Unity/Hub/Editor/6000.0.0f1/Unity.app/Contents/MacOS/Unity"
    )


def test_resolve_effective_config_reads_custom_timeouts(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    init_project_config(project_path=project)
    config_path = project / ".unity-agent" / "config.json"
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["timeouts"] = {"playSeconds": 30, "stopSeconds": 10, "startEditorSeconds": 60}
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    config = resolve_effective_config(project_path=project)

    assert config.timeouts.play_seconds == 30
    assert config.timeouts.stop_seconds == 10
    assert config.timeouts.start_editor_seconds == 60


def test_normalize_unity_executable_path_accepts_app_bundle():
    assert normalize_unity_executable_path(
        "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app"
    ) == Path("/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity")


def test_validate_project_config_reports_missing_unity_executable(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    init_project_config(project_path=project)

    result = validate_project_config(project)

    assert result.ok is False
    assert result.errors[0].field == "config.local.unityExecutablePath"


def test_validate_project_config_reports_invalid_port(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    init_project_config(project_path=project)
    config_path = project / ".unity-agent" / "config.json"
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["bridge"]["preferredPort"] = 70000
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_project_config(project)

    assert result.ok is False
    assert any(issue.field == "config.bridge.preferredPort" for issue in result.errors)


def test_validate_project_config_warns_when_agent_gitignore_missing_local_config(
    tmp_path,
):
    project = make_unity_project(tmp_path / "Game")
    unity = tmp_path / "Unity"
    unity.write_text("", encoding="utf-8")
    init_project_config(project_path=project, unity_path=unity)
    (project / ".unity-agent" / ".gitignore").write_text("sessions/\n", encoding="utf-8")

    result = validate_project_config(project)

    assert result.ok is True
    assert any(
        issue.field == "gitignore" and "config.local.json" in issue.message
        for issue in result.warnings
    )


def test_validate_project_config_does_not_warn_when_agent_gitignore_has_local_config(
    tmp_path,
):
    project = make_unity_project(tmp_path / "Game")
    unity = tmp_path / "Unity"
    unity.write_text("", encoding="utf-8")
    init_project_config(project_path=project, unity_path=unity)

    result = validate_project_config(project)

    assert result.ok is True
    assert all(issue.field != "gitignore" for issue in result.warnings)


def test_find_latest_session_path_uses_session_directory_name(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    old_session = project / ".unity-agent" / "sessions" / "2026-07-01_100000_old"
    new_session = project / ".unity-agent" / "sessions" / "2026-07-02_100000_new"
    old_session.mkdir(parents=True)
    new_session.mkdir(parents=True)

    assert find_latest_session_path(project) == new_session
