from pathlib import Path

import pytest

from unityctl.editor import build_editor_command, validate_project_path


def test_build_editor_command_uses_project_path_and_log_file():
    command = build_editor_command(
        unity_path="/Applications/Unity/Hub/Editor/6000.0.0f1/Unity.app/Contents/MacOS/Unity",
        project_path="/game/project",
        log_file="/tmp/unity-editor.log",
    )

    assert command == [
        "/Applications/Unity/Hub/Editor/6000.0.0f1/Unity.app/Contents/MacOS/Unity",
        "-projectPath",
        "/game/project",
        "-logFile",
        "/tmp/unity-editor.log",
    ]


def test_validate_project_path_accepts_directory_with_assets(tmp_path):
    project = tmp_path / "Game"
    (project / "Assets").mkdir(parents=True)
    (project / "Packages").mkdir()
    (project / "ProjectSettings").mkdir()

    assert validate_project_path(project) == project


def test_validate_project_path_rejects_non_unity_project(tmp_path):
    with pytest.raises(ValueError) as exc:
        validate_project_path(tmp_path)

    assert "does not look like a Unity project" in str(exc.value)
