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


def run_utf(base, unity, project=None):
    if project is None:
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


def verify_delivery_setup(project, unity, upm):
    package_id = "com.mk.unity-agent-bridge"
    manifest = project / "Packages/manifest.json"
    original = manifest.read_bytes()
    first = cli(project, "init", "--yes", "--unity", unity, "--unity-version", "2022.3.62f2",
                save="delivery-init-default.json")
    assert first["packageAction"] == "skipped" and not first["packageInstalled"], first
    assert manifest.read_bytes() == original
    assert "unityctl init --install-package" in first["nextSteps"][0], first
    no_bridge = cli(project, "status", expected="bridge_unreachable", save="delivery-before-editor.json")
    assert "unityctl start" in no_bridge["message"], no_bridge

    reference = f"file:{upm}"
    installed = cli(project, "init", "--yes", "--install-package", "--package-ref", reference,
                    save="delivery-init-install.json")
    assert installed["packageAction"] == "installed" and installed["packageRef"] == reference, installed
    assert json.loads(manifest.read_text())["dependencies"][package_id] == reference
    config = project / ".unity-agent/config.json"
    local = project / ".unity-agent/config.local.json"
    snapshots = [item.read_bytes() for item in (manifest, config, local)]
    repeat = cli(project, "init", "--yes", "--install-package", "--package-ref", "file:/unused.tgz",
                 save="delivery-init-repeat.json")
    assert repeat["packageAction"] == "already_installed", repeat
    assert [item.read_bytes() for item in (manifest, config, local)] == snapshots
    ignore = (project / ".unity-agent/.gitignore").read_text().splitlines()
    assert {"config.local.json", "bridge.json", "sessions/", "test-runs/", "visual-runs/"} <= set(ignore)
    cli(project, "config", "validate", save="delivery-config.json")
    cli(project, "skills", "init", save="delivery-skills.json")
    assert (project / ".agents/skills/unityctl/SKILL.md").is_file()


def run_visual(base, unity, width, height, *, watch=False, model=False, records=False, upm=None):
    dimensions = f"{width}x{height}"
    project = project_at(base, dimensions, {
        **({"com.mk.unity-agent-bridge": f"file:{BRIDGE}"} if upm is None else {}),
        "com.unity.ugui": "1.0.0",
        **({"com.unity.test-framework": "1.1.33"} if records else {}),
    })
    if upm is not None:
        verify_delivery_setup(project, unity, upm)
    (project / "Assets/Editor").mkdir()
    (project / "Assets/Scenes").mkdir()
    (project / "game-view-size.txt").write_text(dimensions)
    shutil.copyfile(FIXTURES / "PrepareGameView.cs", project / "Assets/Editor/PrepareGameView.cs")
    shutil.copyfile(ROOT / "examples/verification/ui/UiReviewDemo.cs", project / "Assets/UiReviewDemo.cs")
    config = project / ".unity-agent/config.json"
    demo_settings = {
        "gameplay": {"enabled": True, "whitelist": [FOCUS]},
        "capture": {"screenshot": {"enabled": True, "allowAgentRequest": True, "agentImageAccess": "allow"}},
    }
    if upm is None:
        write_json(config, demo_settings)
    editor = subprocess.Popen([str(unity), "-projectPath", str(project), "-logFile", str(project / "editor.log"), "-executeMethod", "PrepareGameView.Setup"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for_editor(project, editor, dimensions)
        if upm is not None:
            package = json.loads((project / "Packages/packages-lock.json").read_text())["dependencies"]["com.mk.unity-agent-bridge"]
            assert package["source"] == "local-tarball", package
            start = cli(project, "start", save="delivery-editor-reuse.json")
            assert start["pid"] == editor.pid and start["code"] == "already_running", start
            cli(project, "doctor", save="delivery-doctor.json")
            cli(project, "snapshot", expected="capture_requires_play_mode", save="delivery-capture-in-edit.json")
            cli(project, "play", "--session", "delivery-defaults")
            cli(project, "gameplay", "invoke", FOCUS, expected="gameplay_disabled", save="delivery-gameplay-default.json")
            cli(project, "stop", "--latest")
            current = json.loads(config.read_text())
            write_json(config, {**current, **demo_settings})
        if watch:
            verify_watch(project)
            return
        if model:
            verify_live_model(project)
            return
        if records:
            verify_watch(project)
            verify_agent_watch(project)
            verify_offline_record(project)
            return project
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


def verify_agent_watch(project):
    # CI uses the known center of the synthetic demo, not a vision model.
    command = [sys.executable, "-m", "unityctl.cli", "--project", str(project)]
    run = cli(project, "agent-run", "start", "--name", "agent-delivery")
    session_id = run["sessionId"]
    watcher = subprocess.Popen([*command, "watch", "--session-id", session_id],
                               stdout=subprocess.PIPE, text=True)
    try:
        url = json.loads(watcher.stdout.readline())["url"]

        def step(why, *command, options=(), expected="ok"):
            return cli(project, "agent-run", "step", "--session-id", session_id, "--why", why,
                       *options, "--", *command, expected=expected)

        step("进入合成弹窗场景", "play")
        shot = step("保留点击前画面", "snapshot", "--max-long-edge", "640")
        reference = shot["referenceScreen"]
        click_options = ("--frame", Path(shot["path"]).name)
        click_args = ("click-at", "--x", shot["width"] / 2, "--y", shot["height"] / 2,
                      "--image-width", shot["width"], "--image-height", shot["height"],
                      "--reference-width", reference["width"], "--reference-height", reference["height"])
        assert step("测试合成场景已知按钮落点", *click_args, options=click_options)["clicked"] == "ReviewCanvas/Open"
        step("旧帧不能用于重放", *click_args, options=click_options, expected="agent_run_unavailable")
        step("保留弹窗出现后的画面", "snapshot", "--max-long-edge", "640")
        check = step("核对焦点探针", "gameplay", "invoke", FOCUS, options=("--expect", 'result="confirm"'))
        assert check["verification"]["actual"] == "confirm" and check["verification"]["passed"]
        with urlopen(url + "state", timeout=5) as response:
            live = json.load(response)
        assert live["sessionId"] == session_id and live["status"] == "running", live
        assert live["editor"]["state"] == "playing", live
        click_event = next(row for row in live["events"] if row.get("marker"))
        assert click_event["why"] == "测试合成场景已知按钮落点", click_event
        assert click_event["command"].startswith("unityctl click-at "), click_event
        assert click_event["marker"] == {"x": .5, "y": .5}, click_event
        assert any(row.get("verification", {}).get("passed") for row in live["events"]), live
        with urlopen(url + f"frame/{quote(session_id)}/{quote(click_event['frame'])}", timeout=5) as response:
            assert response.read(8) == b"\x89PNG\r\n\x1a\n"
        write_json(project / "agent-watch-live-evidence.json", live)
        step("退出演示 Play Mode", "stop")
        assert cli(project, "agent-run", "finish", "--session-id", session_id)["status"] == "passed"
        record = cli(project, "runs", "show", f"agent:{session_id}", save="unified-agent.json")["record"]
        assert len(record["steps"]) == 6 and record["status"] == "passed", record
        assert any(row.get("verification", {}).get("actual") == "confirm" for row in record["steps"])
        assert any(row.get("marker") and Path(row["screenshot"]).is_file() for row in record["steps"])
        print("agent-delivery: live intent, actual command, click marker and verification; history preserved", flush=True)
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
    [item] = cli(project, "runs", "list", "--kind", "midscene")["runs"]
    record = cli(project, "runs", "show", item["key"])["record"]
    assert record["status"] == "passed" and any(item["kind"] == "html" for item in record["artifacts"]), record
    print("Midscene model: tap, positive assertion and expected negative verified", flush=True)


def verify_offline_record(project):
    cli(project, "play", "--session", "midscene-offline-record")
    node_script = ROOT / "examples/midscene-game-view/offline-record-fixture.mjs"
    try:
        subprocess.run(
            ["node", str(node_script), str(project), str(Path(sys.executable).with_name("unityctl"))],
            cwd=project, timeout=30, check=True,
        )
    finally:
        cli(project, "stop", "--latest", save="offline-stop.json")


def verify_run_index(work, unity, upm=None):
    project = run_visual(work / "records", unity, 1280, 720, records=True, upm=upm)
    run_utf(work, unity, project=project)
    listing = cli(project, "runs", "list", "--limit", 20, save="unified-list.json")
    assert {item["kind"] for item in listing["runs"]} == {"agent", "scenario", "utf", "midscene"}, listing
    expected = {
        "scenario": {"report", "log", "screenshot"},
        "utf": {"report", "log", "nunit"},
        "midscene": {"html", "log", "screenshot"},
    }
    for kind, artifacts in expected.items():
        item = next(row for row in listing["runs"] if row["kind"] == kind and row["status"] == "failed")
        record = cli(project, "runs", "show", item["key"], save=f"unified-{kind}.json")["record"]
        assert record["status"] == "failed" and record["failures"], record
        assert artifacts <= {entry["kind"] for entry in record["artifacts"]}, record
        if kind != "utf":
            assert Path(record["failures"][0]["screenshot"]).is_file(), record
    print("Combined run index: Agent, Scenario, UTF and Midscene local evidence", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", choices=("utf", "visual", "watch", "records", "delivery", "model", "all"))
    parser.add_argument("--allow-model-requests", action="store_true", help="仅用于 model，确认允许发送演示画面")
    parser.add_argument("--upm", type=Path, help="本地 UPM .tgz，delivery 专用")
    parser.add_argument("--unity", type=Path, default=os.environ.get("UNITY_BIN"))
    parser.add_argument("--output", type=Path, default=ROOT / ".tmp" / "unity-smoke")
    args = parser.parse_args()
    if not __debug__:
        parser.error("run this smoke test without Python optimization (assertions must be active)")
    if args.suite == "model" and (not args.allow_model_requests or not os.environ.get("MIDSCENE_MODEL_NAME")):
        parser.error("model requires --allow-model-requests and MIDSCENE_MODEL_NAME")
    if args.suite == "delivery" and (not args.upm or args.upm.suffix != ".tgz" or not args.upm.is_file()):
        parser.error("delivery requires --upm pointing to a local .tgz")
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
    if args.suite == "records":
        verify_run_index(work, unity.resolve())
    if args.suite == "delivery":
        verify_run_index(work, unity.resolve(), args.upm.resolve())
    if args.suite == "model":
        run_visual(work / "model", unity.resolve(), 1280, 720, model=True)


if __name__ == "__main__":
    main()
