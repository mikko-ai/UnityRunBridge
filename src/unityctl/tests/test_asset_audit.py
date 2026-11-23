import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from unityctl.asset_audit import audit_assets


GUID = "1234567890abcdef" * 2


def put(root, name, content=""):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def project(tmp_path):
    for name in ("Assets", "Packages", "ProjectSettings"):
        (tmp_path / name).mkdir()
    put(tmp_path, "Packages/manifest.json", '{"dependencies": {}}')
    return tmp_path


def reference(root, guid=GUID):
    put(root, "Assets/Test.prefab", f"%YAML 1.1\n--- !u!114 &1\nMonoBehaviour:\n"
        f"  m_Script: {{fileID: 11500000, guid: {guid}, type: 3}}\n")
    put(root, "Assets/Test.prefab.meta", "guid: " + "a" * 32)


def issue_map(report):
    return {issue.code: issue.level for issue in report.issues}


def test_meta_diagnostics_distinguish_confirmed_from_heuristic(project):
    for name in ("A", "B"):
        put(project, f"Assets/{name}.cs")
        put(project, f"Assets/{name}.cs.meta", f"guid: {GUID if name == 'A' else GUID.upper()}")
    put(project, "Assets/Old.cs.meta", f"guid: {'e' * 32}")
    put(project, "Assets/New.cs")
    put(project, "Assets/Texture.png")
    put(project, "Assets/Texture.png.meta", "guid: bad")
    put(project, "Assets/.ignored.cs")
    assert issue_map(audit_assets(project)) == {
        "duplicate-guid": "error", "orphan-meta": "warning",
        "missing-meta": "warning", "malformed-meta": "error",
    }


def test_case_only_mismatch_does_not_look_like_missing_script(project):
    put(project, "Assets/player.cs")
    put(project, "Assets/Player.cs.meta", f"guid: {GUID}")
    reference(project)
    assert issue_map(audit_assets(project)) == {"meta-name-case": "warning"}


def test_missing_script_and_binary_coverage(project):
    reference(project)
    put(project, "Assets/Binary.asset", "not text serialized")
    put(project, "Assets/Binary.asset.meta", "guid: " + "b" * 32)
    report = audit_assets(project)
    assert issue_map(report) == {"missing-script": "error"}
    assert report.unchecked == {"non_yaml_assets": 1}
    assert report.issues[0].line == 4


def test_missing_package_and_stale_cache_do_not_claim_script_verified(project):
    reference(project)
    put(project, "Packages/manifest.json", '{"dependencies": {"com.demo.lib": "2.0.0"}}')
    put(project, "Library/PackageCache/com.demo.lib@1.0.0/Code.cs")
    put(project, "Library/PackageCache/com.demo.lib@1.0.0/Code.cs.meta", f"guid: {GUID}")
    report = audit_assets(project)
    assert issue_map(report) == {"missing-script": "warning"}
    assert report.unresolved_packages == ["com.demo.lib"]
    put(project, "Library/PackageCache/com.demo.lib@2.0.0/Code.cs")
    put(project, "Library/PackageCache/com.demo.lib@2.0.0/Code.cs.meta", f"guid: {GUID}")
    assert not audit_assets(project).issues


def test_resolves_local_package_without_checking_its_meta_hygiene(project):
    reference(project)
    put(project, "Packages/manifest.json", '{"dependencies":{"com.demo.lib":"file:../Local"}}')
    put(project, "Local/package.json", '{"name":"com.demo.lib"}')
    put(project, "Local/Code.cs")
    put(project, "Local/Code.cs.meta", f"guid: {GUID}")
    assert not audit_assets(project).issues


def test_streaming_assets_not_treated_as_unity_yaml(project):
    put(project, "Assets/StreamingAssets.meta", "guid: " + "b" * 32)
    put(project, "Assets/StreamingAssets/payload.asset", "binary")
    put(project, "Assets/StreamingAssets/payload.asset.meta", "guid: " + "c" * 32)
    assert not audit_assets(project).unchecked


def test_health_cli_runs_offline_and_returns_json_without_writing(project):
    reference(project)
    before = sorted(path.relative_to(project) for path in project.rglob("*"))
    run = subprocess.run(
        [sys.executable, "-m", "unityctl.cli", "--project", str(project), "health", "--check", "assets"],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
        text=True, capture_output=True, check=False,
    )
    assert run.returncode == 1
    result = json.loads(run.stdout)
    assert result["code"] == "health_check_failed"
    check, = result["checks"]
    assert check["name"] == "assets"
    assert check["issues"][0]["code"] == "missing-script"
    assert sorted(path.relative_to(project) for path in project.rglob("*")) == before


def test_stale_git_lock_cannot_supply_a_guid(project):
    reference(project)
    old = "https://example.invalid/pkg.git#old"
    new = "https://example.invalid/pkg.git#new"
    rev = "ab" * 20
    put(project, "Packages/manifest.json", json.dumps({"dependencies": {"com.demo.lib": new}}))
    put(project, "Packages/packages-lock.json", json.dumps({"dependencies": {
        "com.demo.lib": {"version": old, "source": "git", "hash": rev},
    }}))
    put(project, f"Library/PackageCache/com.demo.lib@{rev[:12]}/Code.cs")
    put(project, f"Library/PackageCache/com.demo.lib@{rev[:12]}/Code.cs.meta", f"guid: {GUID}")
    report = audit_assets(project)
    assert report.unresolved_packages == ["com.demo.lib"]
    assert issue_map(report) == {"missing-script": "warning"}


def test_symlink_is_not_traversed_and_unknown_guid_is_not_confirmed(project):
    reference(project)
    (project / "Assets/loop").symlink_to(project / "Assets", target_is_directory=True)
    report = audit_assets(project)
    assert report.unchecked == {"symlinks": 1}
    assert issue_map(report) == {"missing-script": "warning"}


def test_long_yaml_line_and_unsupported_refs_keep_correct_line_numbers(project):
    path = put(project, "Assets/Scriptable.asset", "%YAML 1.1\n--- !u!114 &1\nMonoBehaviour:\n"
        "  big: " + ("x" * 170_000) + f"\n  m_Script: {{ fileID: 11500000, guid: {GUID}, type: 3 }}\n"
        "--- !u!114 &2\nMonoBehaviour:\n  m_Script: {fileID: 0}\n")
    put(project, "Assets/Scriptable.asset.meta", f"guid: {'d' * 32}")
    report = audit_assets(project)
    issue, = report.issues
    assert (issue.code, issue.file, issue.line) == ("missing-script", f"Assets/{path.name}", 5)
    assert report.unchecked == {"unsupported_script_refs": 1}


def test_assets_health_warns_without_failing_for_partial_coverage(project):
    put(project, "Assets/Binary.asset", "binary")
    put(project, "Assets/Binary.asset.meta", f"guid: {GUID}")
    from unityctl.config import resolve_effective_config
    from unityctl.health import run_health

    result = run_health(project, resolve_effective_config(project_path=project), ["assets"])
    assert result["ok"] and result["status"] == "warn"
    check, = result["checks"]
    assert check["unchecked"] == {"non_yaml_assets": 1}
