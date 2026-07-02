import tomllib
from pathlib import Path


def test_python_package_name_is_specific_but_command_stays_unityctl():
    payload = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert payload["project"]["name"] == "unity-run-bridge"
    assert payload["project"]["scripts"] == {"unityctl": "unityctl.cli:main"}
