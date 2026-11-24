import json
from unittest.mock import Mock

import pytest

from unityctl import cli


def args(x="20", y="30"):
    return [
        "click-at", "--x", x, "--y", y, "--image-width", "640",
        "--image-height", "360", "--reference-width", "1280", "--reference-height", "720",
    ]


def test_click_at_checks_route_and_sends_image_coordinates(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "Assets").mkdir()
    (tmp_path / "ProjectSettings").mkdir()
    bridge = Mock(base_url="http://localhost:17890", token="token")
    monkeypatch.setattr(cli, "discover", lambda _: bridge)
    client = Mock()
    client.get_capabilities.return_value = {
        "capabilities": ["interaction"],
        "routes": [{"method": "POST", "path": "interaction/click-at"}],
    }
    client.interaction_click_at.return_value = {"ok": True, "clicked": "Canvas/Button"}
    monkeypatch.setattr(cli, "BridgeClient", lambda *_: client)

    assert cli.main(args()) == 0
    client.interaction_click_at.assert_called_once_with(
        x=20, y=30, image_width=640, image_height=360,
        reference_width=1280, reference_height=720,
    )
    assert json.loads(capsys.readouterr().out)["clicked"] == "Canvas/Button"

    client.interaction_click_at.reset_mock()
    client.get_capabilities.return_value["routes"] = []
    assert cli.main(args()) != 0
    client.interaction_click_at.assert_not_called()
    assert json.loads(capsys.readouterr().err)["code"] == "bridge_capability_missing"


@pytest.mark.parametrize(("x", "y"), [("nan", "0"), ("20", "inf"), ("640", "30"), ("0", "-1")])
def test_click_at_rejects_invalid_pixel_before_discovery(monkeypatch, capsys, x, y):
    discover = Mock(side_effect=AssertionError("invalid input must not reach the Bridge"))
    monkeypatch.setattr(cli, "discover", discover)
    assert cli.main(args(x, y)) != 0
    discover.assert_not_called()
    assert json.loads(capsys.readouterr().err)["code"] == "invalid_argument"
