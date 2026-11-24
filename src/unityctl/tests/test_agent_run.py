import json
from pathlib import Path

from unityctl import cli
from unityctl.watch import _run_status, read_events


def test_agent_trace_links_live_intent_command_click_and_verified_result(tmp_path, capsys, monkeypatch):
    for name in ("Assets", "Packages", "ProjectSettings"):
        (tmp_path / name).mkdir()

    def invoke(*args):
        code = cli.main(["--project", str(tmp_path), "agent-run", *args])
        out = capsys.readouterr()
        return code, json.loads(out.out or out.err)

    code, opening = invoke("start", "--name", "preview")
    assert code == 0
    ident = opening["sessionId"]
    session = Path(opening["sessionPath"])
    assert _run_status(read_events(session)) == "running"
    base = ("step", "--session-id", ident, "--why", "核对弹窗行为")

    def snapshot(args):
        frame = Path(args.target_directory) / "screenshot-1.png"
        frame.write_bytes(b"png")
        assert read_events(session)[-1]["type"] == "step-started"
        return {"ok": True, "path": str(frame), "agentImageAccess": "allow", "width": 640, "height": 360,
                "referenceScreen": {"width": 1280, "height": 720}}

    monkeypatch.setattr(cli, "cmd_snapshot", snapshot)
    monkeypatch.setattr(cli, "cmd_click_at", lambda _: {"ok": True, "clicked": "ReviewCanvas/Open"})
    monkeypatch.setattr(cli, "cmd_gameplay", lambda _: {"ok": True, "result": "confirm"})

    assert invoke(*base, "--", "snapshot")[0] == 0
    args = ("--frame", "screenshot-1.png", "--", "click-at", "--x", "160", "--y", "90",
            "--image-width", "640", "--image-height", "360", "--reference-width", "1280", "--reference-height", "720")
    assert invoke(*base, *args)[0] == 0
    assert invoke(*base, *args)[0] == 1  # A click invalidates the old frame; never automatically replay it.
    assert invoke(*base, "--expect", 'result="confirm"', "--", "gameplay", "invoke", "Demo.Focus")[0] == 0
    assert invoke("finish", "--session-id", ident)[1]["status"] == "passed"
    assert cli.main(["--project", str(tmp_path), "runs", "list", "--kind", "agent"]) == 0
    assert json.loads(capsys.readouterr().out)["runs"][0]["key"] == f"agent:{ident}"
    assert cli.main(["--project", str(tmp_path), "runs", "show", f"agent:{ident}"]) == 0
    indexed = json.loads(capsys.readouterr().out)["record"]
    assert indexed["status"] == "passed"
    assert indexed["steps"][1]["marker"] == {"x": .25, "y": .25}
    assert indexed["steps"][1]["screenshot"] == str(session / "artifacts/screenshot-1.png")
    assert indexed["steps"][2]["verification"]["actual"] == "confirm"
    rows = read_events(session)
    assert rows[1]["why"] == "核对弹窗行为" and rows[1]["command"].startswith("unityctl snapshot")
    assert rows[4]["marker"] == {"x": .25, "y": .25}
    assert rows[4]["clicked"] == "ReviewCanvas/Open"
    assert rows[-2]["verification"] == {"field": "result", "actual": "confirm", "expected": "confirm",
                                          "found": True, "passed": True}


def test_agent_assertions_have_to_pass_and_private_frames_are_not_indexed(tmp_path, capsys, monkeypatch):
    for name in ("Assets", "Packages", "ProjectSettings"):
        (tmp_path / name).mkdir()

    def invoke(*args):
        code = cli.main(["--project", str(tmp_path), "agent-run", *args])
        out = capsys.readouterr()
        return code, json.loads(out.out or out.err)

    _, opening = invoke("start", "--name", "negative")
    ident = opening["sessionId"]
    base = ("step", "--session-id", ident, "--why", "检查拒绝路径")
    monkeypatch.setattr(cli, "cmd_snapshot", lambda _: {"ok": True, "agentImageAccess": "deny", "path": "/private.png"})
    _, denied = invoke(*base, "--", "snapshot")
    assert denied["code"] == "agent_image_denied" and "path" not in denied
    monkeypatch.setattr(cli, "cmd_gameplay", lambda _: {"ok": True, "result": "launcher"})
    code, result = invoke(*base, "--expect", 'result="confirm"', "--", "gameplay", "invoke", "Demo.Focus")
    assert code == 1 and result["verification"]["actual"] == "launcher"
    assert invoke("finish", "--session-id", ident)[1]["status"] == "failed"
