import json
import subprocess

import pytest

from unityctl.build import (
    BuildError,
    build_command,
    default_output_path,
    make_build_id,
    parse_log_fallback_errors,
    run_build,
)


def make_unity_project(path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "Assets").mkdir()
    (path / "Packages").mkdir()
    (path / "ProjectSettings").mkdir()
    return path


class FakeProcess:
    def __init__(self, exit_code=0, timeout=False):
        self.exit_code = exit_code
        self.timeout = timeout
        self.wait_calls = 0
        self.killed = False

    def wait(self, timeout=None):
        self.wait_calls += 1
        if self.timeout and self.wait_calls == 1:
            raise subprocess.TimeoutExpired(cmd="unity", timeout=timeout)
        return self.exit_code

    def kill(self):
        self.killed = True


def test_default_output_path_maps_known_targets(tmp_path):
    assert default_output_path(tmp_path, "StandaloneOSX").name == "Build.app"
    assert default_output_path(tmp_path, "StandaloneWindows64").name == "Build.exe"
    assert default_output_path(tmp_path, "Android").name == "Build.apk"
    assert default_output_path(tmp_path, None).name == "Build"
    assert default_output_path(tmp_path, "SomeUnknownTarget").name == "Build"


def test_make_build_id_includes_target_suffix():
    build_id = make_build_id("StandaloneOSX", now_fn=lambda: 0)
    assert build_id.endswith("-StandaloneOSX")
    assert build_id.startswith("19700101T000000Z")


def test_make_build_id_defaults_when_target_missing():
    build_id = make_build_id(None, now_fn=lambda: 0)
    assert build_id.endswith("-default")


def test_build_command_includes_build_target_when_provided():
    command = build_command(
        unity_executable="/Applications/Unity/Unity.app/Contents/MacOS/Unity",
        project_path="/game/project",
        target="StandaloneOSX",
        output_path="/game/project/.unity-agent/builds/x/Build/Build.app",
        report_path="/game/project/.unity-agent/builds/x/build-report.json",
        log_path="/game/project/.unity-agent/builds/x/build.log",
    )

    assert command == [
        "/Applications/Unity/Unity.app/Contents/MacOS/Unity",
        "-batchmode",
        "-quit",
        "-projectPath",
        "/game/project",
        "-buildTarget",
        "StandaloneOSX",
        "-executeMethod",
        "Mk.UnityAgentBridge.Editor.Build.BuildRunner.Build",
        "-logFile",
        "/game/project/.unity-agent/builds/x/build.log",
        "-agentBuildOutput",
        "/game/project/.unity-agent/builds/x/Build/Build.app",
        "-agentReportPath",
        "/game/project/.unity-agent/builds/x/build-report.json",
    ]


def test_build_command_omits_build_target_when_not_provided():
    command = build_command(
        unity_executable="/Unity",
        project_path="/game/project",
        target=None,
        output_path="/out",
        report_path="/report.json",
        log_path="/build.log",
    )

    assert "-buildTarget" not in command


def test_parse_log_fallback_errors_extracts_cs_error_lines():
    log_text = (
        "Some unrelated line\n"
        "Assets/Scripts/Foo.cs(12,34): error CS0103: The name 'Bar' does not exist\n"
        "Assets/Scripts/Baz.cs(5,1): warning CS0219: variable is never used\n"
        "Assets/Scripts/Qux.cs(99,2): error CS1002: ; expected\n"
    )

    errors = parse_log_fallback_errors(log_text)

    assert len(errors) == 2
    assert "CS0103" in errors[0]
    assert "CS1002" in errors[1]


def test_parse_log_fallback_errors_returns_empty_when_no_match():
    assert parse_log_fallback_errors("nothing interesting here") == []


def test_run_build_raises_editor_running_when_project_locked(tmp_path, monkeypatch):
    project = make_unity_project(tmp_path / "Game")
    monkeypatch.setattr("unityctl.build.is_unity_project_locked", lambda _path: True)

    with pytest.raises(BuildError) as exc:
        run_build(project, "/Unity", popen=lambda *a, **k: FakeProcess())

    assert exc.value.code == "editor_running"


def test_run_build_raises_invalid_request_when_executable_missing(tmp_path, monkeypatch):
    project = make_unity_project(tmp_path / "Game")
    monkeypatch.setattr("unityctl.build.is_unity_project_locked", lambda _path: False)

    with pytest.raises(BuildError) as exc:
        run_build(project, None, popen=lambda *a, **k: FakeProcess())

    assert exc.value.code == "invalid_request"


def test_run_build_reads_report_written_by_build_runner(tmp_path, monkeypatch):
    project = make_unity_project(tmp_path / "Game")
    monkeypatch.setattr("unityctl.build.is_unity_project_locked", lambda _path: False)

    captured_commands = []

    def fake_popen(command, **kwargs):
        captured_commands.append(command)
        report_path_str = command[command.index("-agentReportPath") + 1]
        from pathlib import Path

        Path(report_path_str).write_text(
            json.dumps(
                {
                    "result": "Succeeded",
                    "durationMs": 1234,
                    "outputPath": "/tmp/Build.app",
                    "sizeBytes": 999,
                    "errors": [],
                    "warnings": [],
                    "steps": [{"name": "Build", "durationMs": 1234}],
                }
            ),
            encoding="utf-8",
        )
        return FakeProcess(exit_code=0)

    result = run_build(
        project,
        "/Applications/Unity/Unity.app",
        target="StandaloneOSX",
        popen=fake_popen,
        now_fn=lambda: 0,
    )

    assert result.ok is True
    assert result.result == "Succeeded"
    assert result.report["reportSource"] == "build_report"
    assert result.exit_code == 0
    assert len(captured_commands) == 1
    assert result.report_path.exists()


def test_run_build_falls_back_to_log_when_report_missing(tmp_path, monkeypatch):
    project = make_unity_project(tmp_path / "Game")
    monkeypatch.setattr("unityctl.build.is_unity_project_locked", lambda _path: False)

    def fake_popen(command, **kwargs):
        log_path_str = command[command.index("-logFile") + 1]
        from pathlib import Path

        Path(log_path_str).write_text(
            "Compiling scripts...\n"
            "Assets/Scripts/Broken.cs(3,10): error CS1002: ; expected\n",
            encoding="utf-8",
        )
        return FakeProcess(exit_code=1)

    result = run_build(
        project,
        "/Applications/Unity/Unity.app",
        target="StandaloneOSX",
        popen=fake_popen,
        now_fn=lambda: 0,
    )

    assert result.ok is False
    assert result.result == "Failed"
    assert result.report["reportSource"] == "log_fallback"
    assert any("CS1002" in error for error in result.report["errors"])


def test_run_build_falls_back_with_generic_message_when_log_has_no_cs_errors(tmp_path, monkeypatch):
    project = make_unity_project(tmp_path / "Game")
    monkeypatch.setattr("unityctl.build.is_unity_project_locked", lambda _path: False)

    def fake_popen(command, **kwargs):
        return FakeProcess(exit_code=1)

    result = run_build(
        project,
        "/Applications/Unity/Unity.app",
        target="StandaloneOSX",
        popen=fake_popen,
        now_fn=lambda: 0,
    )

    assert result.ok is False
    assert "exit code 1" in result.report["errors"][0]


def test_run_build_kills_process_and_raises_on_timeout(tmp_path, monkeypatch):
    project = make_unity_project(tmp_path / "Game")
    monkeypatch.setattr("unityctl.build.is_unity_project_locked", lambda _path: False)

    fake_process = FakeProcess(timeout=True)

    def fake_popen(command, **kwargs):
        return fake_process

    with pytest.raises(BuildError) as exc:
        run_build(
            project,
            "/Applications/Unity/Unity.app",
            target="StandaloneOSX",
            timeout_seconds=1,
            popen=fake_popen,
            now_fn=lambda: 0,
        )

    assert exc.value.code == "build_timeout"
    assert fake_process.killed is True
