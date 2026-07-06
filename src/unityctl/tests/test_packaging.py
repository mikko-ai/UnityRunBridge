import json
import tomllib
from pathlib import Path


def test_python_package_name_is_specific_but_command_stays_unityctl():
    payload = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert payload["project"]["name"] == "unity-run-bridge"
    assert payload["project"]["scripts"] == {"unityctl": "unityctl.cli:main"}


def test_unity_package_requires_unity_2022_3_or_newer():
    repo_root = Path(__file__).resolve().parents[3]
    package_json = repo_root / "packages" / "com.mk.unity-agent-bridge" / "package.json"
    payload = json.loads(package_json.read_text(encoding="utf-8"))

    assert payload["unity"] == "2022.3"


def test_bundled_schemas_are_byte_identical_to_repo_root_schemas():
    repo_root = Path(__file__).resolve().parents[3]
    root_schemas_dir = repo_root / "schemas"
    bundled_schemas_dir = Path(__file__).resolve().parents[1] / "unityctl" / "schemas"

    root_filenames = {path.name for path in root_schemas_dir.glob("*.json")}
    bundled_filenames = {path.name for path in bundled_schemas_dir.glob("*.json")}
    assert root_filenames == bundled_filenames
    assert root_filenames, "expected at least one schema file"

    for filename in sorted(root_filenames):
        root_bytes = (root_schemas_dir / filename).read_bytes()
        bundled_bytes = (bundled_schemas_dir / filename).read_bytes()
        assert root_bytes == bundled_bytes, f"schema drifted from repo root: {filename}"
