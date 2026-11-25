import json
import os
import stat

from unityctl import cli


def test_plugins_init_creates_template_without_a_unity_project(monkeypatch, tmp_path, capsys):
    home = tmp_path / "home"
    cwd = tmp_path / "empty"
    home.mkdir()
    cwd.mkdir()
    monkeypatch.setattr(cli.Path, "home", staticmethod(lambda: home))
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("UNITY_BRIDGE_MIDSCENE_API_KEY", "sentinel-secret")

    assert cli.main(["plugins", "init", "midscene"]) == 0
    result = json.loads(capsys.readouterr().out)
    path = home / ".unity-agent-bridge/plugins/midscene.jsonc"
    assert result["created"] is True and result["configPath"] == str(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert sum(line.lstrip().startswith("//") for line in lines) == 5
    assert json.loads("\n".join(line for line in lines if not line.lstrip().startswith("//"))) == {
        "baseUrl": "", "modelName": "", "modelFamily": "", "protocol": "openai-chat",
        "apiKeyEnv": "UNITY_BRIDGE_MIDSCENE_API_KEY",
    }
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.parent.parent.stat().st_mode) == 0o700
    assert not list(cwd.iterdir())

    existing = '{"custom": "untouched"}\n'
    path.write_text(existing)
    assert cli.main(["plugins", "init", "midscene"]) == 0
    output = capsys.readouterr().out
    assert json.loads(output)["created"] is False
    assert "untouched" not in output
    assert path.read_text() == existing


def test_plugins_init_preserves_legacy_json_and_rejects_dual_configs(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli.Path, "home", staticmethod(lambda: tmp_path))
    legacy = tmp_path / ".unity-agent-bridge/plugins/midscene.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('{"old": true}\n')
    jsonc = legacy.with_suffix(".jsonc")

    assert cli.main(["plugins", "init", "midscene"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["created"] is False and result["configPath"] == str(legacy)
    assert not jsonc.exists()

    jsonc.write_text("// existing\n{}\n")
    assert cli.main(["plugins", "init", "midscene"]) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["code"] == "plugin_config_unwritable"
    assert "midscene.jsonc 与 midscene.json 同时存在" in error["message"]
    assert legacy.read_text() == '{"old": true}\n'
    assert jsonc.read_text() == "// existing\n{}\n"


def test_plugins_init_reports_path_collision_without_writing(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli.Path, "home", staticmethod(lambda: tmp_path))
    occupied = tmp_path / ".unity-agent-bridge/plugins/midscene.json"
    occupied.mkdir(parents=True)

    assert cli.main(["plugins", "init", "midscene"]) == 1
    assert json.loads(capsys.readouterr().err)["code"] == "plugin_config_unwritable"
    assert occupied.is_dir() and not list(occupied.iterdir())
