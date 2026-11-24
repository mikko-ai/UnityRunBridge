import json
import os

from unityctl.run_events import EVENT_FILE, RunEvents, frame_name


def test_events_are_visible_between_steps(tmp_path):
    events = RunEvents(tmp_path)
    events.emit("run-started", {"status": "running"})
    assert json.loads((tmp_path / EVENT_FILE).read_text())["runnerPid"] == os.getpid()
    events.emit("step-started", {"status": "running", "stepIndex": 0})
    events.emit("run-finished", {"status": "failed"})
    rows = [json.loads(line) for line in (tmp_path / EVENT_FILE).read_text().splitlines()]
    assert [row["sequence"] for row in rows] == [1, 2, 3]
    assert [row["type"] for row in rows] == ["run-started", "step-started", "run-finished"]
    assert rows[-1]["status"] == "failed"


def test_observation_frame_is_confined_to_session_artifacts(tmp_path):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    inside = artifacts / "screenshot-1.png"
    inside.touch()
    outside = tmp_path / "outside.png"
    outside.touch()
    symlink = artifacts / "linked.png"
    symlink.symlink_to(outside)
    assert frame_name(tmp_path, {"screenshotPath": str(inside)}) == inside.name
    assert frame_name(tmp_path, {"path": str(outside)}) is None
    assert frame_name(tmp_path, {"path": str(symlink)}) is None
    assert frame_name(tmp_path, {"path": inside.name}) is None


def test_click_marker_rejects_wrong_reference_and_converts_y():
    from unityctl.run_events import click_marker

    point = {"x": 320, "y": 540, "width": 1280, "height": 720}
    assert click_marker(point, {"width": 1280, "height": 720}) == {"x": .25, "y": .25}
    assert click_marker(point, {"width": 720, "height": 1280}) is None
    assert click_marker({**point, "x": float("nan")}, {"width": 1280, "height": 720}) is None
