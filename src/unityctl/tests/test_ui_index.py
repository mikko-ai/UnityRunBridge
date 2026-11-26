import json
import sqlite3
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from unityctl import cli, ui_index
from unityctl import client as bridge_client

ROOT = "Assets/Menu"
A, B = "a" * 32, "b" * 32
OLD, NEW = "1" * 32, "2" * 32
JOB = "job-20261125010203004-b00b"


@pytest.fixture
def project(tmp_path):
    for directory in ("Assets", "Packages", "ProjectSettings"):
        (tmp_path / directory).mkdir()
    return tmp_path


def control(guid=A, name="开始 / 游戏", sibling=0):
    return {
        "name": name, "componentType": "UnityEngine.UI.Button", "componentIndex": 2,
        "path": [{"name": name, "siblingIndex": sibling}], "sourceGuid": guid,
        "localFileId": "9007199254740993", "interactable": True, "enabled": True,
        "activeSelf": True, "pointerClickHandler": True,
        "persistentCallbacks": [{"method": "OpenPanel", "targetType": "GameObject"}],
    }


def asset(guid=A, path=f"{ROOT}/Play.prefab", fingerprint=OLD, controls=None, changed=True):
    value = {"guid": guid, "path": path, "fingerprint": fingerprint, "changed": changed}
    if changed:
        value["controls"] = [control(guid)] if controls is None else controls
    return value


def output(project, root, rows, known):
    path = project / "Library/UnityRunBridge/ui-index-results" / f"{JOB}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    entries = [c for row in rows for c in row.get("controls", [])]
    return {"schema": 1, "root": root, "artifactPath": str(path),
            "prefabs": len(rows), "scanned": sum(row["changed"] for row in rows),
            "unchanged": sum(not row["changed"] for row in rows), "controlsScanned": len(entries),
            "unidentifiedScanned": sum(c.get("localFileId") is None for c in entries),
            "deleted": len(known.keys() - {row["guid"] for row in rows}), "durationMs": 7, "skipped": 0}


def apply(project, rows, root=ROOT, *, full=False):
    rev, known = ui_index.snapshot(project, root)
    if full:
        known = {}
    result = output(project, root, rows, known)
    imported = ui_index.import_snapshot(project, root, rev, known, JOB, result)
    assert not (project / "Library/UnityRunBridge/ui-index-results" / f"{JOB}.jsonl").exists()
    return imported


def check_error(code, fn, *args, **kwargs):
    with pytest.raises(ui_index.UiIndexError) as exc:
        fn(*args, **kwargs)
    assert exc.value.code == code


def test_full_incremental_deletion_and_scope_separation(project):
    apply(project, [asset(), asset(B, f"{ROOT}/Other.prefab")])
    apply(project, [asset()], root="Assets")
    old_id = ui_index.find(project, ROOT, query="Play.prefab")["controls"][0]["id"]
    unchanged = apply(project, [asset(path=f"{ROOT}/Renamed.prefab", changed=False)])
    assert unchanged["scanned"] == 0 and unchanged["deleted"] == 1
    assert unchanged["unchanged"] == 1
    current, = ui_index.find(project, ROOT)["controls"]
    assert current["id"] == old_id
    assert current["assetPath"].endswith("/Renamed.prefab")
    assert ui_index.snapshot(project, "Assets")[1] == {A: OLD}
    full = apply(project, [], full=True)
    assert full["deleted"] == 1 and ui_index.find(project, ROOT)["controls"] == []
    assert ui_index.find(project, "Assets")["controls"]


def test_search_reports_ambiguity_and_stale_annotations_separately(project):
    c = control()
    c["persistentCallbacks"][0]["argument"] = "must-not-be-copied"
    second = control(sibling=1)
    apply(project, [asset(controls=[c, second])])
    found = ui_index.find(project, ROOT, "开始", component_type="Button", limit=1)
    assert found["ambiguous"] and found["truncated"] and not found["liveVerified"]
    first, = found["controls"]
    assert first["localFileId"] == "9007199254740993"
    assert "argument" not in first["persistentCallbacks"][0]
    uid = first["id"]
    ui_index.annotate(project, ROOT, uid, "Play", "打开游戏预览", "user-confirmed", "F-001")
    note = ui_index.find(project, ROOT, alias="PLAY")["controls"][0]["annotation"]
    assert note == {"alias": "Play", "purpose": "打开游戏预览", "origin": "user-confirmed",
                    "evidence": "F-001", "stale": False}
    notes = ui_index.notes_path(project).read_bytes()
    apply(project, [asset(fingerprint=NEW, controls=[c, second])], full=True)
    assert ui_index.notes_path(project).read_bytes() == notes
    assert ui_index.find(project, ROOT, alias="Play")["controls"][0]["annotation"]["stale"]


@pytest.mark.parametrize("damage", ["duplicates", "wrong_count", "unknown_unchanged", "truncated", "outside"])
def test_invalid_scan_rolls_back_previous_snapshot(project, damage):
    apply(project, [asset()])
    rev, known = ui_index.snapshot(project, ROOT)
    updated = asset(fingerprint=NEW)
    rows = {"duplicates": [updated, updated],
            "unknown_unchanged": [updated, asset(B, f"{ROOT}/Y.prefab", changed=False)],
            "outside": [updated, asset(B, "Assets/Other/Y.prefab")]}.get(damage, [updated])
    result = output(project, ROOT, rows, known)
    if damage == "wrong_count":
        result["scanned"] += 1
    if damage == "truncated":
        with open(result["artifactPath"], "a") as stream:
            stream.write('{"guid"')
    check_error("ui_index_scan_invalid", ui_index.import_snapshot, project, ROOT, rev, known, JOB, result)
    assert ui_index.snapshot(project, ROOT) == (rev, known)
    assert ui_index.find(project, ROOT)["controls"][0]["fingerprint"] == OLD


def test_wrong_artifact_and_stale_transaction_are_rejected(project):
    apply(project, [asset()])
    rev, known = ui_index.snapshot(project, ROOT)
    result = output(project, ROOT, [asset(changed=False)], known)
    check_error("ui_index_scan_invalid", ui_index.import_snapshot, project, ROOT, rev, known, JOB,
                dict(result, artifactPath=str(project / "outside.json")))
    apply(project, [asset(fingerprint=NEW)])
    result = output(project, ROOT, [asset(changed=False)], known)
    check_error("ui_index_conflict", ui_index.import_snapshot, project, ROOT, rev, known, JOB, result)


def test_unversioned_or_corrupt_cache_requires_explicit_recovery(project):
    path = ui_index.cache_path(project)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not a database")
    check_error("ui_index_cache_invalid", ui_index.snapshot, project, ROOT)
    assert path.read_bytes() == b"not a database"
    path.unlink()
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version=19")
    check_error("ui_index_cache_invalid", ui_index.snapshot, project, ROOT)


def test_cli_sync_and_offline_find(project, monkeypatch, capsys):
    posted = []

    class Bridge:
        def get_capabilities(self):
            return {"capabilities": ["ui-index"], "routes": [{"method": "POST", "path": "ui-index/scan"}]}

        def post(self, route, body):
            posted.append((route, body))
            return {"ok": True, "jobId": JOB}

    def finished(_project, job, **kwargs):
        assert job == JOB and kwargs["poll_interval"] == 0.1
        moved = bool(posted[-1][1]["known"])
        rows = [asset(changed=not moved)]
        return {"status": "succeeded", "result": output(project, ROOT, rows, posted[-1][1]["known"])}

    monkeypatch.setattr(cli, "discover", lambda _: SimpleNamespace(base_url="unused", token="unused"))
    monkeypatch.setattr(cli, "BridgeClient", lambda *_: Bridge())
    monkeypatch.setattr(cli, "wait_for_job", finished)
    base = ["--project", str(project), "ui-index"]
    assert cli.main([*base, "sync", "--root", ROOT]) == 0
    assert json.loads(capsys.readouterr().out)["scanned"] == 1
    assert cli.main([*base, "sync", "--root", ROOT]) == 0
    assert json.loads(capsys.readouterr().out)["unchanged"] == 1
    assert posted[-1] == ("ui-index/scan", {"root": ROOT, "known": {A: OLD}})
    monkeypatch.setattr(cli, "discover", lambda _: pytest.fail("find must not connect to an Editor"))
    assert cli.main([*base, "find", "--root", ROOT, "开始", "--type", "Button"]) == 0
    assert len(json.loads(capsys.readouterr().out)["controls"]) == 1


def test_first_failed_import_can_retry_without_manual_cache_recovery(project):
    result = output(project, ROOT, [asset()], {})
    result["controlsScanned"] += 1
    check_error("ui_index_scan_invalid", ui_index.import_snapshot, project, ROOT, 0, {}, JOB, result)
    assert ui_index.snapshot(project, ROOT) == (0, {})
    check_error("ui_index_missing", ui_index.find, project, ROOT)
    assert apply(project, [asset()])["scanned"] == 1


def test_old_bridge_preflight_never_posts_scan_or_creates_cache(project, monkeypatch, capsys):
    class OldBridge:
        def get_capabilities(self):
            return {"capabilities": ["interaction"]}

        def post(self, *_):
            pytest.fail("must not post UI index request to old Bridge")

    monkeypatch.setattr(cli, "discover", lambda _: SimpleNamespace(base_url="unused", token="unused"))
    monkeypatch.setattr(cli, "BridgeClient", lambda *_: OldBridge())
    assert cli.main(["--project", str(project), "ui-index", "sync", "--root", ROOT]) == 1
    assert json.loads(capsys.readouterr().err)["code"] == "bridge_capability_missing"
    assert not ui_index.cache_path(project).exists()


def test_asset_artifact_symlink_outside_project_is_refused(project):
    outside = project.parent / f"{JOB}.jsonl"
    outside.write_text("must not be consumed")
    result = output(project, ROOT, [], {})
    artifact = Path(result["artifactPath"])
    artifact.unlink()
    artifact.symlink_to(outside)
    check_error("ui_index_path_invalid", ui_index.import_snapshot, project, ROOT, 0, {}, JOB, result)
    assert outside.read_text() == "must not be consumed"


def test_runtime_prefab_click_sends_exact_identity_no_force_or_legacy_fallback(project, monkeypatch, capsys):
    apply(project, [asset(controls=[control(), control(sibling=1)])])
    selected = next(item for item in ui_index.find(project, ROOT)["controls"] if item["path"][0]["siblingIndex"] == 1)
    calls = []

    class Bridge:
        def get_capabilities(self):
            return {"capabilities": ["ui-index", "interaction"],
                    "routes": [{"method": "POST", "path": "ui-index/click"}]}

        def post(self, route, body):
            calls.append((route, body))
            return {"ok": False, "code": "occluded", "blockedBy": "Cover"}

    monkeypatch.setattr(cli, "discover", lambda _: SimpleNamespace(base_url="unused", token="unused"))
    monkeypatch.setattr(cli, "BridgeClient", lambda *_: Bridge())
    argv = ["--project", str(project), "ui-index", "click", selected["id"], "--root", ROOT,
            "--instance-root", "Canvas/Panel", "--scene", "Assets/Lab.unity"]
    assert cli.main(argv) == 1
    assert json.loads(capsys.readouterr().err)["blockedBy"] == "Cover"
    (route, body), = calls
    assert route == "ui-index/click"
    assert body == {"binding": "prefab", "scene": "Assets/Lab.unity", "instanceRoot": "Canvas/Panel",
                    "controlId": selected["id"], "relativePath": selected["path"], **{
                        key: selected[key] for key in (
                            "assetGuid", "assetPath", "sourceGuid", "localFileId",
                            "fingerprint", "componentIndex", "componentType",
                        )
                    }}


def test_runtime_old_bridge_or_missing_specific_route_does_not_post(project, monkeypatch, capsys):
    class ReadOnlyIndexBridge:
        def get_capabilities(self):
            return {"capabilities": ["ui-index", "interaction"],
                    "routes": [{"method": "POST", "path": "ui-index/scan"}]}

        def post(self, *_):
            pytest.fail("no fallback allowed")

    monkeypatch.setattr(cli, "discover", lambda _: SimpleNamespace(base_url="unused", token="unused"))
    monkeypatch.setattr(cli, "BridgeClient", lambda *_: ReadOnlyIndexBridge())
    argv = ["--project", str(project), "ui-index", "click", "--runtime-token", "a" * 32,
            "--scene", "Assets/Lab.unity"]
    assert cli.main(argv) == 1
    assert json.loads(capsys.readouterr().err)["code"] == "bridge_capability_missing"


@pytest.mark.parametrize("scene", ["Assets/Lab.unity", "DontDestroyOnLoad"])
def test_runtime_dynamic_resolve_uses_fresh_hierarchy_evidence_without_cache(project, monkeypatch, capsys, scene):
    requests = []

    class Bridge:
        def get_capabilities(self):
            return {"capabilities": ["ui-index"],
                    "routes": [{"method": "POST", "path": "ui-index/resolve"}]}

        def post(self, route, body):
            requests.append((route, body))
            return {"ok": True, "runtimeToken": "e" * 32}

    monkeypatch.setattr(cli, "discover", lambda _: SimpleNamespace(base_url="unused", token="unused"))
    monkeypatch.setattr(cli, "BridgeClient", lambda *_: Bridge())
    argv = ["--project", str(project), "ui-index", "resolve", "--scene", scene,
            "--runtime-path", "Canvas/B", "--instance-id=-234"]
    assert cli.main(argv) == 0
    assert json.loads(capsys.readouterr().out)["runtimeToken"] == "e" * 32
    assert requests == [("ui-index/resolve", {"binding": "runtime", "scene": scene,
                                              "runtimePath": "Canvas/B", "instanceId": -234})]
    assert not ui_index.cache_path(project).exists()


@pytest.mark.parametrize("action", ["bind", "resolve", "click"])
def test_persistent_scope_does_not_accept_static_prefab_ids(project, action):
    args = SimpleNamespace(scene="DontDestroyOnLoad", control_id="a" * 64, ui_index_action=action)
    with pytest.raises(ui_index.UiIndexError, match="仅动态绑定"):
        ui_index.runtime_binding(project, ROOT, args)


def test_runtime_click_preserves_dispatched_events_on_http_conflict(project, monkeypatch, capsys):
    events = ["pointerEnter", "pointerDown", "pointerUp", "pointerExit"]
    body = {"ok": False, "code": "click_not_dispatched", "message": "changed",
            "events": events, "runtimeToken": "do-not-copy"}

    def conflict(request, timeout):
        assert request.full_url.endswith("/ui-index/click")
        raise HTTPError(request.full_url, 409, "Conflict", {}, BytesIO(json.dumps(body).encode()))

    monkeypatch.setattr(cli, "discover", lambda _: SimpleNamespace(base_url="http://127.0.0.1:1", token="unused"))
    monkeypatch.setattr(cli, "require_bridge_route", lambda *_: None)
    monkeypatch.setattr(bridge_client, "urlopen", conflict)
    code = cli.main(["--project", str(project), "ui-index", "click", "--scene", "DontDestroyOnLoad",
                     "--runtime-token", "a" * 32])
    assert code == 1
    assert json.loads(capsys.readouterr().err) == {
        "ok": False, "code": "click_not_dispatched", "message": "changed", "events": events,
    }
