#!/usr/bin/env python3
"""Repeatable UTF and Game View smoke cases for Unity 2022.3.62f2."""

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "scripts" / "fixtures" / "smoke"
BRIDGE = ROOT / "packages" / "com.mk.unity-agent-bridge"
FOCUS = "UnityRunBridge.Examples.UiReviewDemo.FocusedControl"


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def project_at(base, name, dependencies):
    project = base / name
    for directory in ("Assets", "Packages", "ProjectSettings", ".unity-agent"):
        (project / directory).mkdir(parents=True)
    (project / "ProjectSettings/ProjectVersion.txt").write_text(
        "m_EditorVersion: 2022.3.62f2\nm_EditorVersionWithRevision: 2022.3.62f2 (7670c08855a9)\n"
    )
    write_json(project / "Packages/manifest.json", {"dependencies": dependencies})
    return project


def cli(project, *args, expected="ok", timeout=30, save=None):
    result = subprocess.run(
        [sys.executable, "-m", "unityctl.cli", "--project", str(project), *map(str, args)],
        capture_output=True, text=True, timeout=timeout,
    )
    if save:
        (project / save).write_text(result.stdout or result.stderr, encoding="utf-8")
    try:
        data = json.loads(result.stdout or result.stderr)
    except ValueError:
        raise RuntimeError(f"{args}: {result.stdout}\n{result.stderr}") from None
    if expected == "ok":
        assert result.returncode == 0 and data.get("ok") is True, (args, data)
    else:
        assert result.returncode != 0 and data.get("code") == expected, (args, data)
    return data


def run_utf(base, unity):
    project = project_at(base, "utf", {"com.unity.test-framework": "1.1.33"})
    for mode in ("Edit", "Play"):
        folder = project / "Assets" / mode
        folder.mkdir()
        definition = {"name": f"BridgeSmoke{mode}", "optionalUnityReferences": ["TestAssemblies"]}
        if mode == "Edit":
            definition["includePlatforms"] = ["Editor"]
        write_json(folder / f"{mode}.asmdef", definition)
        shutil.copyfile(FIXTURES / f"BridgeSmoke{mode}.cs", folder / f"BridgeSmoke{mode}.cs")

    for job, mode, pattern, expected in (
        ("edit-pass", "EditMode", "BridgeSmokeEdit.Passes", "ok"),
        ("play-pass", "PlayMode", "BridgeSmokePlay.RunsInPlayMode", "ok"),
        ("edit-fail", "EditMode", "BridgeSmokeEdit.Fails", "tests_failed"),
    ):
        report = cli(project, "test", "run", "--mode", mode, "--filter", pattern,
                     "--job-id", job, "--unity", unity, "--timeout", 240, timeout=260,
                     expected=expected, save=f"{job}.json")
        observed = cli(project, "test", "status", job, expected=expected)
        assert observed == report, (observed, report)
        assert Path(report["resultsPath"]).is_file() and Path(report["logPath"]).is_file()
        assert report["counts"]["total"] == 1, report
        if expected == "ok":
            assert report["status"] == "passed" and report["counts"]["passed"] == 1, report
        else:
            assert report["counts"]["failed"] == 1, report
            failure, = report["failures"]
            assert failure["name"] == pattern and "Intentional UTF smoke failure" in failure["message"], report
        print(f"{job}: {report['status']} ({report['reportPath']})", flush=True)


def wait_for_editor(project, process, dimensions):
    deadline = time.monotonic() + 120
    marker = project / "game-view-ready.txt"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Unity exited before handshake: {process.returncode}")
        if marker.is_file():
            message = marker.read_text()
            if message and message != "ready":
                raise RuntimeError(f"Game View {dimensions}: {message}")
            if message == "ready":
                try:
                    result = cli(project, "status", timeout=8)
                    if result["editorState"] == "idle":
                        return
                except (AssertionError, RuntimeError, subprocess.TimeoutExpired):
                    pass
        time.sleep(0.5)
    raise TimeoutError(f"Game View {dimensions} did not become ready")


def capture(project, width, height, name):
    frame = cli(project, "snapshot", "--max-long-edge", "640", "--annotate", save=f"{name}.json")
    assert frame["referenceScreen"] == {"width": width, "height": height}, frame
    assert frame["coordinateSpace"] == "image-top-left", frame
    assert (frame["width"], frame["height"]) == (width // 2, height // 2), frame
    with Path(frame["path"]).open("rb") as stream:
        png = stream.read(24)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and png[12:16] == b"IHDR", frame
    assert struct.unpack(">II", png[16:24]) == (frame["width"], frame["height"]), frame
    return frame


def click(project, frame, x, y, *, expected="ok", adjust_width=0):
    reference = frame["referenceScreen"]
    return cli(project, "click-at", "--x", x, "--y", y, "--image-width", frame["width"],
               "--image-height", frame["height"], "--reference-width", reference["width"] + adjust_width,
               "--reference-height", reference["height"], expected=expected)


def run_visual(base, unity, width, height, *, watch=False, model=False):
    dimensions = f"{width}x{height}"
    project = project_at(base, dimensions, {
        "com.mk.unity-agent-bridge": f"file:{BRIDGE}", "com.unity.ugui": "1.0.0",
    })
    (project / "Assets/Editor").mkdir()
    (project / "Assets/Scenes").mkdir()
    (project / "game-view-size.txt").write_text(dimensions)
    shutil.copyfile(FIXTURES / "PrepareGameView.cs", project / "Assets/Editor/PrepareGameView.cs")
    shutil.copyfile(ROOT / "examples/verification/ui/UiReviewDemo.cs", project / "Assets/UiReviewDemo.cs")
    write_json(project / ".unity-agent/config.json", {
        "gameplay": {"enabled": True, "whitelist": [FOCUS]},
        "capture": {"screenshot": {"enabled": True, "allowAgentRequest": True}},
    })
    editor = subprocess.Popen([str(unity), "-projectPath", str(project), "-logFile", str(project / "editor.log"), "-executeMethod", "PrepareGameView.Setup"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for_editor(project, editor, dimensions)
        if watch:
            verify_watch(project)
            return
        if model:
            verify_live_model(project)
            return
        cli(project, "play", "--session", "coordinate-smoke")
        before = capture(project, width, height, "before")
        x, y = before["width"] / 2, before["height"] / 2
        click(project, before, x, y, adjust_width=1, expected="game_view_resized")
        assert cli(project, "gameplay", "invoke", FOCUS)["result"] == "launcher"
        assert click(project, before, x, y)["clicked"] == "ReviewCanvas/Open"
        opened = capture(project, width, height, "opened")
        click(project, opened, x, y, expected="no_click_handler")
        assert cli(project, "gameplay", "invoke", FOCUS)["result"] == "confirm"
        sidecar = json.loads(Path(opened["annotationsPath"]).read_text())
        cancel = next(item for item in sidecar["elements"] if item["path"] == "ReviewCanvas/Dialog/Card/Cancel")
        assert click(project, opened, cancel["screenX"], cancel["screenY"])["clicked"] == cancel["path"]
        assert cli(project, "gameplay", "invoke", FOCUS)["result"] == "launcher"
        capture(project, width, height, "closed")
        cli(project, "stop", "--latest", save="stop.json")
        print(f"{dimensions}: coordinate clicks, stale size and blocking overlay verified", flush=True)
    finally:
        terminate(editor)


def terminate(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def verify_watch(project):
    command = [sys.executable, "-m", "unityctl.cli", "--project", str(project)]
    watcher = subprocess.Popen([*command, "watch"], stdout=subprocess.PIPE, text=True)
    try:
        url = json.loads(watcher.stdout.readline())["url"]
        for expected in ("passed", "failed"):
            steps = [
                {"action": "open-scene", "scene": "Assets/Scenes/UiReview.unity"},
                {"action": "play"},
                {"action": "screenshot", "id": "before-click"},
                {"action": "click", "id": "open-dialog", "path": "ReviewCanvas/Open"},
                {"action": "assert", "id": "check-focus", "gameplay": {
                    "command": FOCUS, "equals": "confirm" if expected == "passed" else "impossible",
                }},
                {"action": "screenshot", "id": "after-click"},
                {"action": "stop"},
            ]
            scenario = project / f"watch-{expected}.json"
            write_json(scenario, {"name": f"watch-{expected}", "steps": steps})
            with (project / f"watch-{expected}-cli.json").open("w") as out:
                run = subprocess.Popen(
                    [*command, "scenario", "run", str(scenario), "--observe"],
                    stdout=out, stderr=subprocess.STDOUT,
                )
                try:
                    observed_live = False
                    observed_live_marker = False
                    deadline = time.monotonic() + 60
                    while time.monotonic() < deadline:
                        with urlopen(url + "state", timeout=4) as response:
                            state = json.load(response)
                        events = state["events"]
                        this_run = events and events[0].get("name") == f"watch-{expected}"
                        if this_run and state["status"] == "running" and run.poll() is None:
                            observed_live |= any(row["type"] == "step-started" for row in events)
                            observed_live_marker |= any(row.get("marker") for row in events)
                        if this_run and state["status"] in {"passed", "failed", "interrupted"}:
                            break
                        time.sleep(.08)
                    else:
                        raise TimeoutError(f"watch did not show a final status: {state}")
                    assert run.wait(timeout=15) == (0 if expected == "passed" else 1)
                    assert observed_live and observed_live_marker, events
                    assert state["status"] == expected, state
                    marker = next(row for row in events if row.get("marker"))
                    assert marker["id"] == "open-dialog", marker
                    assert all(abs(marker["marker"][axis] - .5) < .02 for axis in ("x", "y")), marker
                    frame = next(row for row in reversed(events) if row.get("frame"))
                    assert frame["id"] == ("after-click" if expected == "passed" else "check-focus"), frame
                    if expected == "failed":
                        assert frame["status"] == "failed", frame
                    frame_url = url + f"frame/{quote(state['sessionId'])}/{quote(frame['frame'])}"
                    with urlopen(frame_url, timeout=4) as response:
                        assert response.read(8) == b"\x89PNG\r\n\x1a\n"
                    write_json(project / f"watch-{expected}-evidence.json", {
                        "observedRunningBeforeExit": observed_live,
                        "observedClickMarkerBeforeExit": observed_live_marker,
                        "state": state,
                    })
                    print(f"watch-{expected}: live steps, click marker, final frame and replay verified", flush=True)
                finally:
                    terminate(run)
    finally:
        terminate(watcher)


def verify_live_model(project):
    cli(project, "play", "--session", "midscene-model")
    node_script = ROOT / "examples/midscene-game-view/model-acceptance.mjs"
    unityctl = Path(sys.executable).with_name("unityctl")
    # Keep reports and cache local to this synthetic run; never archive this suite in ordinary CI.
    environment = {**os.environ, "MIDSCENE_RUN_DIR": str(project / "midscene_run")}
    try:
        with (project / "model-acceptance.log").open("w", encoding="utf-8") as out:
            result = subprocess.run(
                ["node", str(node_script), str(project), str(unityctl), "--allow-model-requests"],
                cwd=project, env=environment, stdout=out, stderr=subprocess.STDOUT, timeout=180, check=False,
            )
    finally:
        cli(project, "stop", "--latest", save="model-stop.json")
    if result.returncode != 0:
        raise RuntimeError("Midscene 验收失败；请在本机查看 model-acceptance.log")
    if not list((project / "midscene_run" / "report").glob("*.html")):
        raise RuntimeError("Midscene 未生成 HTML 报告")
    print("Midscene model: tap, positive assertion and expected negative verified", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", choices=("utf", "visual", "watch", "model", "all"))
    parser.add_argument("--allow-model-requests", action="store_true", help="仅用于 model，确认允许发送演示画面")
    parser.add_argument("--unity", type=Path, default=os.environ.get("UNITY_BIN"))
    parser.add_argument("--output", type=Path, default=ROOT / ".tmp" / "unity-smoke")
    args = parser.parse_args()
    if not __debug__:
        parser.error("run this smoke test without Python optimization (assertions must be active)")
    if args.suite == "model" and (not args.allow_model_requests or not os.environ.get("MIDSCENE_MODEL_NAME")):
        parser.error("model requires --allow-model-requests and MIDSCENE_MODEL_NAME")
    unity = args.unity
    if unity and unity.suffix == ".app":
        unity /= "Contents/MacOS/Unity"
    if not unity or not os.access(unity, os.X_OK):
        parser.error("set UNITY_BIN or pass --unity")
    args.output.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="run-", dir=args.output.resolve()))
    print(f"Evidence directory: {work}", flush=True)
    if args.suite in {"utf", "all"}:
        run_utf(work, unity.resolve())
    if args.suite in {"visual", "all"}:
        for width, height in ((1280, 720), (720, 1280)):
            run_visual(work, unity.resolve(), width, height)
    if args.suite in {"watch", "all"}:
        run_visual(work / "observe", unity.resolve(), 1280, 720, watch=True)
    if args.suite == "model":
        run_visual(work / "model", unity.resolve(), 1280, 720, model=True)


if __name__ == "__main__":
    main()
