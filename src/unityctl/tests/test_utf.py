import json
import subprocess
from pathlib import Path

import pytest

from unityctl import cli, utf

PASS_XML = '<test-run result="Skipped:Ignored" total="2" passed="1" failed="0" skipped="1" inconclusive="0" />'
FAIL_XML = '''<test-run result="Failed(Child)" total="1" passed="0" failed="1" skipped="0" inconclusive="0">
<test-suite name="Fixture" site="Child"><failure><message>Child failed</message></failure>
<test-case fullname="Fixture.Fails"><failure><message>expected 2</message><stack-trace>Foo.cs:10</stack-trace></failure></test-case>
</test-suite></test-run>'''
EMPTY_XML = '<test-run result="Passed" total="0" passed="0" failed="0" skipped="0" inconclusive="0" />'


@pytest.fixture
def project(tmp_path, monkeypatch):
    for name in ("Assets", "Packages", "ProjectSettings"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(utf, "is_unity_project_locked", lambda _: False)
    return tmp_path


@pytest.mark.parametrize(("xml", "exitcode", "code"), [
    (PASS_XML, 0, "ok"),
    (PASS_XML, 1, "test_process_failed"),
    (FAIL_XML, 2, "tests_failed"),
    (EMPTY_XML, 0, "no_tests_passed"),
    (None, 0, "test_result_unavailable"),
    ("<test-run>", 0, "test_result_unavailable"),
])
def test_utf_reports_result_and_can_be_polled(monkeypatch, project, xml, exitcode, code):
    def fake_run(command, **kwargs):
        assert "-quit" not in command
        assert command[command.index("-testPlatform") + 1] == "PlayMode"
        assert command[command.index("-testFilter") + 1] == "Fixture.Fails"
        assert kwargs["timeout"] == 15
        pending = utf.read_test_job(project, "smoke")
        assert pending["status"] == "running"
        if xml is not None:
            Path(command[command.index("-testResults") + 1]).write_text(xml)
        return subprocess.CompletedProcess(command, exitcode)

    monkeypatch.setattr(utf, "is_pid_alive", lambda _: True)
    monkeypatch.setattr(utf.subprocess, "run", fake_run)
    result = utf.run_tests(project, Path("Unity"), mode="PlayMode", job_id="smoke",
                           test_filter="Fixture.Fails", timeout=15)
    assert result["code"] == code
    assert result == utf.read_test_job(project, "smoke")
    if code == "tests_failed":
        assert result["failures"] == [{"name": "Fixture.Fails", "kind": "test",
                                      "message": "expected 2", "stackTrace": "Foo.cs:10"}]


def test_utf_timeout_is_persisted(monkeypatch, project):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(utf.subprocess, "run", fake_run)
    result = utf.run_tests(project, Path("Unity"), mode="EditMode", job_id="timed", timeout=1)
    assert result["status"] == "timed_out"
    assert utf.read_test_job(project, "timed")["code"] == "test_timeout"


def test_utf_does_not_launch_in_locked_project(monkeypatch, project):
    monkeypatch.setattr(utf, "is_unity_project_locked", lambda _: True)
    with pytest.raises(utf.UtfError) as error:
        utf.run_tests(project, Path("Unity"), mode="EditMode")
    assert error.value.code == "editor_running"
    assert not (project / ".unity-agent").exists()


def test_cli_utf_job_id_is_validated(project, capsys):
    assert cli.main(["--project", str(project), "test", "status", "../other"]) == 1
    assert json.loads(capsys.readouterr().err)["code"] == "invalid_argument"


def test_utf_dead_runner_cannot_report_pass(monkeypatch, project):
    directory = project / ".unity-agent/test-runs/gone"
    directory.mkdir(parents=True)
    (directory / "test-report.json").write_text(
        '{"jobId":"gone","status":"running","runnerPid":123,"ok":true}'
    )
    monkeypatch.setattr(utf, "is_pid_alive", lambda _: False)
    report = utf.read_test_job(project, "gone")
    assert report["status"] == "interrupted" and not report["ok"]
