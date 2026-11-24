import json

import pytest

from unityctl import cli
from unityctl.run_records import RunRecordError, list_runs, show_run


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def project(tmp_path):
    for name in ("Assets", "Packages", "ProjectSettings"):
        (tmp_path / name).mkdir()
    return tmp_path


def test_unified_index_returns_scoped_proof_for_three_kinds(project, capsys):
    state = project / ".unity-agent"
    scenario = state / "sessions/focus"
    screenshot = scenario / "artifacts/focus.png"
    write(scenario / "session.json", {
        "sessionId": "focus", "trigger": "scenario", "status": "stopped",
        "name": "焦点", "createdAt": "2026-11-24T10:00:00+08:00",
    })
    write(scenario / "artifacts/scenario-result.json", {"status": "failed", "steps": [
        {"id": "check-focus", "action": "assert", "status": "failed",
         "evidence": {"screenshotPath": str(screenshot), "expected": "a", "actual": "b"}},
    ]})
    screenshot.touch()
    (scenario / "unity-console.jsonl").touch()
    utf = state / "test-runs/test"
    write(utf / "test-report.json", {
        "jobId": "test", "schemaVersion": 1, "mode": "PlayMode", "status": "failed",
        "startedAt": "2026-11-24T03:00:00Z", "failures": [{"name": "Entry", "message": "mismatch"}],
    })
    (utf / "unity.log").touch()
    visual = state / "visual-runs/demo"
    write(visual / "run-record.json", {
        "id": "demo", "schemaVersion": 1, "name": "真实报告", "mode": "offline",
        "startedAt": "2026-11-24T04:00:00Z", "status": "failed", "report": "look.html",
        "steps": [{"id": "negative", "action": "assert", "status": "failed", "screenshot": "scene.png"}],
    })
    for item in ("look.html", "scene.png", "events.jsonl"):
        (visual / item).touch()
    args = ["--project", str(project), "runs"]
    assert cli.main([*args, "list"]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert [row["key"] for row in listing["runs"]] == ["midscene:demo", "utf:test", "scenario:focus"]
    assert cli.main([*args, "show", "scenario:focus"]) == 0
    record = json.loads(capsys.readouterr().out)["record"]
    assert record["failures"][0]["screenshot"] == str(screenshot)
    assert any(item["kind"] == "log" for item in record["artifacts"])
    assert show_run(project, "utf:test")["failures"][0]["message"] == "mismatch"
    assert {a["kind"] for a in show_run(project, "midscene:demo")["artifacts"]} == {
        "record", "html", "screenshot", "log",
    }


def test_index_rejects_traversal_symlinks_and_unrelated_sessions(project):
    state = project / ".unity-agent"
    external = project / "private.png"
    external.touch()
    run = state / "visual-runs/bad"
    write(run / "run-record.json", {"schemaVersion": 1, "id": "bad", "status": "failed",
                                  "steps": [{"id": "a", "screenshot": "linked.png"},
                                            {"id": "b", "screenshot": str(external)}]})
    (run / "linked.png").symlink_to(external)
    (run.parent / "redirect").symlink_to(run)
    show = show_run(project, "midscene:bad")
    assert all("screenshot" not in item or item["screenshot"] is None for item in show["steps"])
    assert all(a["kind"] != "screenshot" for a in show["artifacts"])
    with pytest.raises(RunRecordError):
        show_run(project, "midscene:../bad")
    with pytest.raises(RunRecordError):
        show_run(project, "midscene:redirect")
    write(state / "sessions/manual/session.json", {"sessionId": "manual", "trigger": "cli"})
    assert list_runs(project, "scenario", 20)["runs"] == []


def test_old_utf_runner_without_pid_cannot_claim_running(project):
    write(project / ".unity-agent/test-runs/live/test-report.json", {
        "jobId": "live", "schemaVersion": 1, "status": "running",
    })
    assert show_run(project, "utf:live")["status"] == "unknown"
