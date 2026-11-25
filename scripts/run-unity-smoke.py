#!/usr/bin/env python3
"""Repeatable UTF and Game View smoke cases for Unity 2022.3.62f2."""

import argparse
import json
import math
import os
import shutil
import socket
import sqlite3
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
BASELINE_RESET = "UiLocateBaselineReset.Reset"


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


def cli(project, *args, expected="ok", timeout=30, save=None, metrics=None):
    started = time.perf_counter_ns()
    result = subprocess.run(
        [sys.executable, "-m", "unityctl.cli", "--project", str(project), *map(str, args)],
        capture_output=True, text=True, timeout=timeout,
    )
    if metrics is not None:
        metrics.append({
            "command": str(args[0]),
            "millis": (time.perf_counter_ns() - started) / 1_000_000,
            "responseBytes": len((result.stdout or result.stderr).encode("utf-8")),
            "exitCode": result.returncode,
        })
    if save:
        (project / save).write_text(result.stdout or result.stderr, encoding="utf-8")
    try:
        data = json.loads(result.stdout or result.stderr)
    except ValueError:
        raise RuntimeError(f"{args}: {result.stdout}\n{result.stderr}") from None
    accepted = (expected,) if isinstance(expected, str) else expected
    if result.returncode == 0:
        assert data.get("ok") is True and "ok" in accepted, (args, data)
    else:
        assert data.get("ok") is False and data.get("code") in accepted, (args, data)
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


def click(project, frame, x, y, *, expected="ok", adjust_width=0, metrics=None):
    reference = frame["referenceScreen"]
    return cli(project, "click-at", "--x", x, "--y", y, "--image-width", frame["width"],
               "--image-height", frame["height"], "--reference-width", reference["width"] + adjust_width,
               "--reference-height", reference["height"], expected=expected, metrics=metrics)


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


def run_visual(base, unity, width, height, *, watch=False, model=False, records=False, upm=None, locate_baseline=False):
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
    if locate_baseline:
        shutil.copyfile(FIXTURES / "UiLocateBaselineReset.cs", project / "Assets/UiLocateBaselineReset.cs")
        demo_settings["gameplay"]["whitelist"].append(BASELINE_RESET)
        # Do not compete with the user's open Unity Editor for the default Bridge port.
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            demo_settings["bridge"] = {"preferredPort": probe.getsockname()[1]}
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
        if locate_baseline:
            return run_locate_baseline(project, width, height)
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


def run_locate_baseline(project, width, height):
    """Compare operation sequences on the same ready screen, not simulated model time."""
    opened = "ReviewCanvas/Open"
    refused = ("ok", "no_click_handler", "game_view_resized", "occluded", "not_interactable")
    play = []
    stop = []
    warmups = []
    samples = []
    strategies = ("image", "hierarchy", "known-path")

    def execute(strategy):
        metrics = []
        artifact_bytes = 0
        failure = None
        result = {}
        if strategy == "image":
            frame = cli(project, "snapshot", "--max-long-edge", 640, metrics=metrics)
            assert frame["referenceScreen"] == {"width": width, "height": height}, frame
            artifact_bytes = Path(frame["path"]).stat().st_size
            x, y = frame["width"] // 2, frame["height"] // 2
            hit = cli(project, "hit-test", "--x", x, "--y", y, "--image-width", frame["width"],
                      "--image-height", frame["height"], metrics=metrics)
            hits = hit["ugui"]["hits"]
            if not hits or not (hits[0]["path"] == opened or hits[0]["path"].startswith(opened + "/")):
                failure = {"stage": "hit-test", "code": "unexpected_hit", "top": hits[0] if hits else None}
            else:
                result = click(project, frame, x, y, metrics=metrics,
                               expected=refused)
                if not result["ok"]:
                    failure = {"stage": "click-at", "code": result["code"], "hit": hits[0]}
        elif strategy == "hierarchy":
            found = cli(project, "hierarchy", "find", "--name", "Open", "--under", "ReviewCanvas",
                        "--component", "Button", "--active-only", metrics=metrics)
            assert not found["truncated"] and found["matchedCount"] == 1, found
            path = found["nodes"][0]["path"]
            assert path == opened, found
            result = cli(project, "click", path, metrics=metrics, expected=refused)
        else:
            result = cli(project, "click", opened, metrics=metrics, expected=refused)
        if failure is None and not result["ok"]:
            failure = {"stage": "click", "code": result["code"]}
        # On a refusal the postcondition must prove no modal opened. Never retry
        # an issued click in the same sample. Positive samples explicitly reset.
        verification = []
        observed = cli(project, "gameplay", "invoke", FOCUS, metrics=verification)["result"]
        if failure is None:
            assert result["clicked"] == opened and observed == "confirm", (result, observed)
            assert cli(project, "gameplay", "invoke", BASELINE_RESET,
                       metrics=verification)["result"] == "launcher"
        else:
            assert observed == "launcher", (failure, observed)
        return {
            "strategy": strategy, "expectedTarget": opened, "actualTarget": result.get("clicked"),
            "failure": failure,
            "cliMillis": sum(entry["millis"] for entry in metrics),
            "responseBytes": sum(entry["responseBytes"] for entry in metrics),
            "artifactBytes": artifact_bytes, "calls": len(metrics), "commands": metrics, "verifyAndReset": verification,
        }

    cli(project, "play", "--session", "ui-locate-baseline", metrics=play)
    try:
        assert cli(project, "gameplay", "invoke", FOCUS)["result"] == "launcher"
        for strategy in strategies:
            warmups.append(execute(strategy))
        for index in range(20):
            order = strategies[index % len(strategies):] + strategies[:index % len(strategies)]
            samples.extend(execute(s) for s in order)
        for _ in range(20):
            unsettled = [strategy for strategy in strategies
                         if sum(s["strategy"] == strategy and s["failure"] is None for s in samples) < 20]
            if not unsettled:
                break
            samples.extend(execute(strategy) for strategy in unsettled)
    finally:
        cli(project, "stop", "--latest", metrics=stop)
    summary = {}
    for strategy in strategies:
        selected = [x for x in samples if x["strategy"] == strategy]
        successful = [row for row in selected if row["failure"] is None]
        times = sorted(row["cliMillis"] for row in successful)
        n = len(times)
        summary[strategy] = {
            "n": n, "attempts": len(selected), "failed": len(selected) - n,
            "p50Millis": (times[(n - 1) // 2] + times[n // 2]) / 2 if n else None,
            "p95Millis": times[math.ceil(.95 * n) - 1] if n else None,
            "callsPerSuccess": successful[0]["calls"] if n else None,
        }
    write_json(project / "ui-locate-baseline.json", {
        "layout": {"width": width, "height": height},
        "play": play, "stop": stop, "warmups": warmups, "samples": samples, "summary": summary,
    })
    print(f"{width}x{height} baseline: {json.dumps(summary)}", flush=True)
    return all(group["n"] >= 20 for group in summary.values())


def run_ui_index(base, unity, upm=None, expected_legacy=False):
    project = project_at(base, "ui-index", {
        "com.mk.unity-agent-bridge": f"file:{upm or BRIDGE}", "com.unity.ugui": "1.0.0",
    })
    config = project / ".unity-agent/config.json"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        write_json(config, {"version": 1, "bridge": {"preferredPort": probe.getsockname()[1]}})
    write_json(project / ".unity-agent/config.local.json", {"unityExecutablePath": str(unity)})
    folder = project / "Assets/Editor"
    folder.mkdir()
    shutil.copyfile(FIXTURES / "PrepareUiIndex.cs", folder / "PrepareUiIndex.cs")
    editor = subprocess.Popen([str(unity), "-batchmode", "-nographics", "-projectPath", str(project),
                               "-logFile", str(project / "editor.log"), "-executeMethod", "PrepareUiIndex.Setup"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for_editor(project, editor, "UI index fixture")
        if upm:
            lock = json.loads((project / "Packages/packages-lock.json").read_text())
            assert lock["dependencies"]["com.mk.unity-agent-bridge"]["source"] == "local-tarball"
        if expected_legacy:
            assert cli(project, "status")["bridgeVersion"].startswith("0.4.")
            cli(project, "ui-index", "sync", expected="bridge_capability_missing", save="legacy-index-sync.json")
            cli(project, "ui-index", "click", "--scene", "Assets/Scenes/Unused.unity",
                "--runtime-token", "0" * 32, expected="bridge_capability_missing", save="legacy-index-click.json")
            assert not (project / "Library/UnityRunBridge/ui-index.sqlite3").exists()
            print("Legacy Unity Bridge: scan/click refused without fallback", flush=True)
            return
        files = [project / name for name in (
            "Assets/Menu/Menu.prefab", "Assets/Menu/Menu.prefab.meta",
            "Packages/manifest.json", "Packages/packages-lock.json", "ProjectSettings/ProjectVersion.txt",
        )]
        before = [path.read_bytes() for path in files]
        cli(project, "skills", "init")
        doctor = cli(project, "doctor", "--require-route", "POST", "ui-index/scan", save="ui-index-doctor.json")
        assert doctor["versions"]["loadedBridgeVersion"] == "0.6.0", doctor
        cold = cli(project, "ui-index", "sync", "--root", "Assets/Menu", save="ui-index-cold.json")
        assert cold["scanned"] == cold["controlsScanned"] == 1, cold
        warm = cli(project, "ui-index", "sync", "--root", "Assets/Menu", save="ui-index-warm.json")
        assert warm["scanned"] == 0 and warm["unchanged"] == 1, warm
        item, = cli(project, "ui-index", "find", "--root", "Assets/Menu", "Open Test",
                    "--type", "Button", save="ui-index-found.json")["controls"]
        assert item["assetPath"] == "Assets/Menu/Menu.prefab" and int(item["localFileId"]) != 0, item
        cli(project, "ui-index", "annotate", "--root", "Assets/Menu", item["id"],
            "--alias", "open-demo", "--purpose", "测试夹具入口", "--origin", "source-inference",
            "--evidence", "PrepareUiIndex.Setup")
        notes = (project / ".unity-agent/ui-index-annotations.sqlite3").read_bytes()
        assert cli(project, "ui-index", "sync", "--root", "Assets/Menu", "--full")["scanned"] == 1
        assert (project / ".unity-agent/ui-index-annotations.sqlite3").read_bytes() == notes
        result_files = project / "Library/UnityRunBridge/ui-index-results"
        assert not list(result_files.glob("*.jsonl")), result_files
        assert [path.read_bytes() for path in files] == before
    finally:
        terminate(editor)

    found = cli(project, "ui-index", "find", "--root", "Assets/Menu", "--alias", "OPEN-DEMO",
                save="ui-index-offline.json")
    saved, = found["controls"]
    assert saved["id"] == item["id"] and not found["liveVerified"] and not saved["annotation"]["stale"], found
    print(f"UI index: cold/warm/full, offline alias and read-only asset files verified ({project})", flush=True)


def run_indexed_click(base, unity, upm=None):
    project = project_at(base, "ui-index-click", {
        "com.mk.unity-agent-bridge": f"file:{upm or BRIDGE}", "com.unity.ugui": "1.0.0",
    })
    (project / "Assets/Editor").mkdir()
    (project / "Assets/Scenes").mkdir()
    for name in ("PrepareGameView.cs", "PrepareUiIndexRuntime.cs"):
        shutil.copyfile(FIXTURES / name, project / "Assets/Editor" / name)
    shutil.copyfile(FIXTURES / "UiIndexFixtureProbe.cs", project / "Assets/UiIndexFixtureProbe.cs")
    shutil.copyfile(ROOT / "examples/verification/ui/UiReviewDemo.cs", project / "Assets/UiReviewDemo.cs")
    (project / "game-view-size.txt").write_text("640x360")
    probe_name = "UiIndexFixtureProbe.Control"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        write_json(project / ".unity-agent/config.json", {
            "version": 1, "bridge": {"preferredPort": probe.getsockname()[1]},
            "gameplay": {"enabled": True, "whitelist": [probe_name]},
        })
    editor = subprocess.Popen([str(unity), "-projectPath", str(project), "-logFile", str(project / "editor.log"),
                               "-executeMethod", "PrepareUiIndexRuntime.Setup"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    scene = "Assets/Scenes/Indexed.unity"
    try:
        wait_for_editor(project, editor, "indexed-click 640x360")
        checked = cli(project, "ui-index", "sync", "--root", "Assets/Menu")
        assert checked["prefabs"] == 1 and checked["controlsScanned"] == 2, checked
        both = cli(project, "ui-index", "find", "--root", "Assets/Menu", "Action")
        assert both["ambiguous"], both
        target, = [item for item in both["controls"] if item["path"][0]["siblingIndex"] == 0]
        target_args = (target["id"], "--root", "Assets/Menu")
        scope = ("--instance-root", "UiCanvas/Panel", "--scene", scene)
        write_json(project / "ui-index-click-target.json", target)

        bound = cli(project, "ui-index", "bind", *target_args, *scope, save="indexed-bound.json")
        assert bound["bound"] and not bound["liveVerified"], bound
        # The target is a real scene-linked prefab instance, not a name-only lookalike.
        started = cli(project, "play", "--scene", scene, "--session", "indexed-click")
        session = Path(started["sessionPath"])
        expected = []
        responses = []
        def probe(action):
            return cli(project, "gameplay", "invoke", probe_name,
                       "--args", json.dumps({"action": action}))["result"]
        def attempt(args, code="ok"):
            result = cli(project, "ui-index", "click", *args, expected=code)
            expected.append(code)
            responses.append(result)
            return result
        try:
            identified = cli(project, "ui-index", "resolve", *target_args, *scope)
            assert identified["resolvedPath"] == "UiCanvas/Panel/Action[0]", identified
            assert identified["liveVerified"] and not identified["clickabilityVerified"], identified
            assert probe("counts") == "0:0"
            actual = attempt((*target_args, *scope))
            assert actual["clicked"] == identified["resolvedPath"] and not actual["forced"], actual
            assert "pointerClick" in actual["events"] and actual["screenPoint"]["width"] > 0, actual
            assert probe("counts") == "1:0"

            for change, code in (
                ("clone", "ui_index_ambiguous"), ("rename", "ui_index_stale"),
                ("reorder", "ui_index_source_mismatch"), ("cover", "occluded"),
                ("disabled", "not_interactable"), ("inactive", "ui_index_handler_mismatch"),
            ):
                probe(change)
                attempt((*target_args, *scope), code)
                assert probe("counts") == "1:0", change
                probe("remove-clone" if change == "clone" else "restore")
            probe("replace-root")
            attempt((*target_args, *scope), "ui_index_source_mismatch")
            assert probe("counts") == "1:0"
            probe("restore-root")
            probe("no-source")
            attempt((*target_args, "--instance-root", "UiCanvas/RuntimeClone", "--scene", scene),
                    "ui_index_source_mismatch")
            assert probe("counts") == "1:0"
            probe("remove-clone")
            attempt((*target_args, "--instance-root", "UiCanvas/Panel", "--scene", "Assets/Scenes/Other.unity"),
                    "ui_index_scene_missing")
            with sqlite3.connect(project / "Library/UnityRunBridge/ui-index.sqlite3") as conn:
                conn.execute("UPDATE prefabs SET fingerprint=?", ("0" * 32,))
            attempt((*target_args, *scope), "ui_index_stale")
            assert probe("counts") == "1:0"

            found = cli(project, "hierarchy", "find", "--name", "Dynamic", "--active-only")
            dynamic, = found["nodes"]
            witness = cli(project, "ui-index", "resolve", "--scene", scene, "--runtime-path", dynamic["path"],
                          f"--instance-id={dynamic['instanceId']}")
            dynamic_args = ("--scene", scene, "--runtime-token", witness["runtimeToken"])
            assert attempt(dynamic_args)["clicked"] == "UiCanvas/Dynamic"
            attempt(dynamic_args, "ui_index_witness_expired")
            assert probe("counts") == "2:0"
            witness = cli(project, "ui-index", "resolve", "--scene", scene, "--runtime-path", dynamic["path"],
                          f"--instance-id={dynamic['instanceId']}")
            probe("rename-dynamic")
            attempt(("--scene", scene, "--runtime-token", witness["runtimeToken"]), "ui_index_stale")
            assert probe("counts") == "2:0"
            refound = cli(project, "hierarchy", "find", "--name", "DynamicChanged", "--active-only")
            new_node, = refound["nodes"]
            witness = cli(project, "ui-index", "resolve", "--scene", scene, "--runtime-path", new_node["path"],
                          f"--instance-id={new_node['instanceId']}")
            probe("switch-scene")
            assert cli(project, "status")["activeScenePath"] == "Assets/Scenes/Other.unity"
            attempt(("--scene", scene, "--runtime-token", witness["runtimeToken"]), "ui_index_scene_missing")
        finally:
            cli(project, "stop", "--latest")
        audits = [json.loads(line) for line in (session / "artifacts/interaction-actions.jsonl").read_text().splitlines()]
        audits = [entry for entry in audits if entry.get("action") == "ui-index-click"]
        assert [entry["code"] for entry in audits] == expected, audits
        assert all("runtimeToken" not in entry["request"] for entry in audits), audits
        assert sum(entry["ok"] for entry in audits) == 2
        write_json(project / "indexed-click-result.json", {"methods": expected, "responses": responses, "audits": audits,
                                                          "expectedCallbacks": 2, "unexpectedCallbacks": 0})
        print(f"Indexed click: {len(expected)} attempts; 2 intended callbacks, 0 unexpected ({project})", flush=True)
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
    parser.add_argument("suite", choices=("utf", "visual", "watch", "records", "delivery", "model", "locate-baseline", "ui-index", "indexed-click", "indexed-legacy", "all"))
    parser.add_argument("--allow-model-requests", action="store_true", help="仅用于 model，确认允许发送演示画面")
    parser.add_argument("--upm", type=Path, help="本地 UPM .tgz，供分发和索引实测使用")
    parser.add_argument("--unity", type=Path, default=os.environ.get("UNITY_BIN"))
    parser.add_argument("--output", type=Path, default=ROOT / ".tmp" / "unity-smoke")
    args = parser.parse_args()
    if not __debug__:
        parser.error("run this smoke test without Python optimization (assertions must be active)")
    if args.suite == "model":
        if not args.allow_model_requests:
            parser.error("model requires --allow-model-requests")
        try:
            config = subprocess.run(
                ["node", str(ROOT / "examples/midscene-game-view/model-check.mjs")],
                capture_output=True, text=True, timeout=10, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            parser.error("无法完成 Midscene 配置检查，请确认 Node.js 可用")
        if config.returncode:
            parser.error(config.stderr.strip() or "Midscene 配置检查失败")
    if args.suite == "delivery" and (not args.upm or args.upm.suffix != ".tgz" or not args.upm.is_file()):
        parser.error("delivery requires --upm pointing to a local .tgz")
    if args.suite == "indexed-legacy" and not args.upm:
        parser.error("indexed-legacy requires a local 0.4.x UPM tarball")
    if args.suite in {"ui-index", "indexed-click", "indexed-legacy"} and args.upm and (args.upm.suffix != ".tgz" or not args.upm.is_file()):
        parser.error("ui-index requires --upm pointing to a local .tgz")
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
    if args.suite == "locate-baseline":
        adequate_samples = [
            run_visual(work, unity.resolve(), width, height, locate_baseline=True)
            for width, height in ((640, 360), (360, 640))
        ]
        assert all(adequate_samples), "insufficient successful samples; see both layout reports"
    if args.suite in {"watch", "all"}:
        run_visual(work / "observe", unity.resolve(), 1280, 720, watch=True)
    if args.suite in {"ui-index", "indexed-legacy"}:
        run_ui_index(work, unity.resolve(), args.upm.resolve() if args.upm else None,
                     expected_legacy=args.suite == "indexed-legacy")
    if args.suite == "indexed-click":
        run_indexed_click(work, unity.resolve(), args.upm.resolve() if args.upm else None)
    if args.suite == "records":
        verify_run_index(work, unity.resolve())
    if args.suite == "delivery":
        verify_run_index(work, unity.resolve(), args.upm.resolve())
    if args.suite == "model":
        run_visual(work / "model", unity.resolve(), 1280, 720, model=True)


if __name__ == "__main__":
    main()
