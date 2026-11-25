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
    path = home / ".unity-agent-bridge/plugins/midscene.json"
    assert result["created"] is True and result["configPath"] == str(path)
    assert json.loads(path.read_text()) == {
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


def test_plugins_init_reports_path_collision_without_writing(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli.Path, "home", staticmethod(lambda: tmp_path))
    occupied = tmp_path / ".unity-agent-bridge/plugins/midscene.json"
    occupied.mkdir(parents=True)

    assert cli.main(["plugins", "init", "midscene"]) == 1
    assert json.loads(capsys.readouterr().err)["code"] == "plugin_config_unwritable"
    assert occupied.is_dir() and not list(occupied.iterdir())
