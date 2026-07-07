import json

import pytest

from unityctl.client import BridgeClientError
from unityctl.config import EffectiveConfig, Timeouts
from unityctl.convergence import ConvergenceEditorExited, ConvergenceTimeout
from unityctl.discovery import BridgeInfo, DiscoveryError
from unityctl.health import (
    ALL_CHECKS,
    HealthContext,
    HealthError,
    check_build_scenes,
    check_compilation,
    check_missing_scripts,
    check_packages,
    parse_editor_build_settings_scenes,
    parse_project_version,
    run_health,
)
from unityctl.jobs import JobFailed


def make_unity_project(path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "Assets").mkdir()
    (path / "Packages").mkdir()
    (path / "ProjectSettings").mkdir()
    return path


def make_effective_config(project_path, unity_version=None):
    return EffectiveConfig(
        project_path=project_path,
        project_config_path=project_path / ".unity-agent" / "config.json",
        local_config_path=project_path / ".unity-agent" / "config.local.json",
        preferred_port=17890,
        unity_version=unity_version,
        unity_executable_path=None,
        default_scene=None,
        timeouts=Timeouts(),
    )


def make_context(project_path, unity_version=None, timeout_seconds=5.0):
    return HealthContext(
        project_path=project_path,
        effective=make_effective_config(project_path, unity_version=unity_version),
        timeout_seconds=timeout_seconds,
    )


FAKE_INFO = BridgeInfo(
    port=17890,
    pid=4242,
    token="tok",
    unity_version="2022.3.62f2",
    project_path="/game/project",
    started_at="2024-01-01T00:00:00Z",
)


# ---------------------------------------------------------------------------
# parse_editor_build_settings_scenes / parse_project_version
# ---------------------------------------------------------------------------


def test_parse_editor_build_settings_scenes_extracts_enabled_and_path():
    text = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!1045 &1
EditorBuildSettings:
  m_ObjectHideFlags: 0
  serializedVersion: 2
  m_Scenes:
  - enabled: 1
    path: Assets/Scenes/Main.unity
    guid: 0123456789abcdef0123456789abcdef
  - enabled: 0
    path: Assets/Scenes/Debug.unity
    guid: abcdef0123456789abcdef0123456789
  m_configObjects: {}
"""

    scenes = parse_editor_build_settings_scenes(text)

    assert scenes == [
        (True, "Assets/Scenes/Main.unity"),
        (False, "Assets/Scenes/Debug.unity"),
    ]


def test_parse_editor_build_settings_scenes_empty_when_no_scenes():
    assert parse_editor_build_settings_scenes("m_Scenes: []\n") == []


def test_parse_project_version_extracts_editor_version():
    text = "m_EditorVersion: 2022.3.62f2\nm_EditorVersionWithRevision: 2022.3.62f2 (abcdef123456)\n"

    assert parse_project_version(text) == "2022.3.62f2"


def test_parse_project_version_returns_none_when_missing():
    assert parse_project_version("nothing here") is None


# ---------------------------------------------------------------------------
# check_build_scenes
# ---------------------------------------------------------------------------


def test_check_build_scenes_passes_when_all_listed_scenes_exist_and_none_unlisted(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    scenes_dir = project / "Assets" / "Scenes"
    scenes_dir.mkdir(parents=True)
    (scenes_dir / "Main.unity").write_text("", encoding="utf-8")

    settings_path = project / "ProjectSettings" / "EditorBuildSettings.asset"
    settings_path.write_text(
        "EditorBuildSettings:\n  m_Scenes:\n  - enabled: 1\n    path: Assets/Scenes/Main.unity\n",
        encoding="utf-8",
    )

    result = check_build_scenes(make_context(project))

    assert result["status"] == "pass"
    assert result["details"] == []


def test_check_build_scenes_fails_when_listed_scene_file_missing(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    settings_path = project / "ProjectSettings" / "EditorBuildSettings.asset"
    settings_path.write_text(
        "EditorBuildSettings:\n  m_Scenes:\n  - enabled: 1\n    path: Assets/Scenes/Gone.unity\n",
        encoding="utf-8",
    )

    result = check_build_scenes(make_context(project))

    assert result["status"] == "fail"
    assert any("Gone.unity" in detail for detail in result["details"])


def test_check_build_scenes_warns_when_scene_file_not_listed(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    scenes_dir = project / "Assets" / "Scenes"
    scenes_dir.mkdir(parents=True)
    (scenes_dir / "Main.unity").write_text("", encoding="utf-8")
    (scenes_dir / "Orphan.unity").write_text("", encoding="utf-8")

    settings_path = project / "ProjectSettings" / "EditorBuildSettings.asset"
    settings_path.write_text(
        "EditorBuildSettings:\n  m_Scenes:\n  - enabled: 1\n    path: Assets/Scenes/Main.unity\n",
        encoding="utf-8",
    )

    result = check_build_scenes(make_context(project))

    assert result["status"] == "warn"
    assert any("Orphan.unity" in detail for detail in result["details"])


def test_check_build_scenes_warns_when_settings_file_missing(tmp_path):
    project = make_unity_project(tmp_path / "Game")

    result = check_build_scenes(make_context(project))

    assert result["status"] == "warn"


# ---------------------------------------------------------------------------
# check_packages
# ---------------------------------------------------------------------------


def test_check_packages_fails_when_manifest_missing(tmp_path):
    project = make_unity_project(tmp_path / "Game")

    result = check_packages(make_context(project))

    assert result["status"] == "fail"


def test_check_packages_passes_when_manifest_and_lock_consistent(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    (project / "Packages" / "manifest.json").write_text(
        json.dumps({"dependencies": {"com.unity.textmeshpro": "3.0.0"}}), encoding="utf-8"
    )
    (project / "Packages" / "packages-lock.json").write_text(
        json.dumps({"dependencies": {"com.unity.textmeshpro": {"version": "3.0.0"}}}),
        encoding="utf-8",
    )

    result = check_packages(make_context(project, unity_version=None))

    assert result["status"] == "pass"


def test_check_packages_warns_when_lock_file_missing(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    (project / "Packages" / "manifest.json").write_text(
        json.dumps({"dependencies": {}}), encoding="utf-8"
    )

    result = check_packages(make_context(project))

    assert result["status"] == "warn"
    assert any("packages-lock.json" in detail for detail in result["details"])


def test_check_packages_warns_when_lock_missing_declared_dependency(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    (project / "Packages" / "manifest.json").write_text(
        json.dumps({"dependencies": {"com.unity.new-package": "1.0.0"}}), encoding="utf-8"
    )
    (project / "Packages" / "packages-lock.json").write_text(
        json.dumps({"dependencies": {}}), encoding="utf-8"
    )

    result = check_packages(make_context(project))

    assert result["status"] == "warn"
    assert any("com.unity.new-package" in detail for detail in result["details"])


def test_check_packages_warns_on_unity_version_mismatch(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    (project / "Packages" / "manifest.json").write_text(
        json.dumps({"dependencies": {}}), encoding="utf-8"
    )
    (project / "Packages" / "packages-lock.json").write_text(
        json.dumps({"dependencies": {}}), encoding="utf-8"
    )
    (project / "ProjectSettings" / "ProjectVersion.txt").write_text(
        "m_EditorVersion: 2022.3.25f1\n", encoding="utf-8"
    )

    result = check_packages(make_context(project, unity_version="2022.3.62f2"))

    assert result["status"] == "warn"
    assert any("2022.3.25f1" in detail for detail in result["details"])


# ---------------------------------------------------------------------------
# check_compilation / check_missing_scripts (Bridge-backed, monkeypatched)
# ---------------------------------------------------------------------------


def test_check_compilation_skips_when_bridge_unreachable(tmp_path, monkeypatch):
    project = make_unity_project(tmp_path / "Game")

    def fake_discover(_path):
        raise DiscoveryError("not running")

    monkeypatch.setattr("unityctl.health.discover", fake_discover)

    result = check_compilation(make_context(project))

    assert result["status"] == "skipped"


def test_check_compilation_passes_when_compilation_succeeded(tmp_path, monkeypatch):
    project = make_unity_project(tmp_path / "Game")

    class FakeClient:
        def __init__(self, *_args):
            pass

        def get_status(self):
            return {}

        def refresh(self):
            return {"ok": True}

    monkeypatch.setattr("unityctl.health.discover", lambda _path: FAKE_INFO)
    monkeypatch.setattr("unityctl.health.BridgeClient", FakeClient)
    monkeypatch.setattr(
        "unityctl.health.poll_until",
        lambda *a, **k: type("R", (), {"status": {"compilationSucceeded": True}})(),
    )

    result = check_compilation(make_context(project))

    assert result["status"] == "pass"


def test_check_compilation_fails_with_error_details(tmp_path, monkeypatch):
    project = make_unity_project(tmp_path / "Game")

    class FakeClient:
        def __init__(self, *_args):
            pass

        def get_status(self):
            return {}

        def refresh(self):
            return {"ok": True}

    monkeypatch.setattr("unityctl.health.discover", lambda _path: FAKE_INFO)
    monkeypatch.setattr("unityctl.health.BridgeClient", FakeClient)
    monkeypatch.setattr(
        "unityctl.health.poll_until",
        lambda *a, **k: type(
            "R",
            (),
            {
                "status": {
                    "compilationSucceeded": False,
                    "compilationErrors": [{"file": "Foo.cs", "line": 3, "message": "boom"}],
                }
            },
        )(),
    )

    result = check_compilation(make_context(project))

    assert result["status"] == "fail"
    assert any("boom" in detail for detail in result["details"])


def test_check_compilation_fails_on_convergence_timeout(tmp_path, monkeypatch):
    project = make_unity_project(tmp_path / "Game")

    class FakeClient:
        def __init__(self, *_args):
            pass

        def get_status(self):
            return {}

        def refresh(self):
            return {"ok": True}

    def raise_timeout(*_a, **_k):
        raise ConvergenceTimeout("timed out")

    monkeypatch.setattr("unityctl.health.discover", lambda _path: FAKE_INFO)
    monkeypatch.setattr("unityctl.health.BridgeClient", FakeClient)
    monkeypatch.setattr("unityctl.health.poll_until", raise_timeout)

    result = check_compilation(make_context(project))

    assert result["status"] == "fail"


def test_check_compilation_skips_when_editor_exits_mid_wait(tmp_path, monkeypatch):
    project = make_unity_project(tmp_path / "Game")

    class FakeClient:
        def __init__(self, *_args):
            pass

        def get_status(self):
            return {}

        def refresh(self):
            return {"ok": True}

    def raise_exited(*_a, **_k):
        raise ConvergenceEditorExited("gone")

    monkeypatch.setattr("unityctl.health.discover", lambda _path: FAKE_INFO)
    monkeypatch.setattr("unityctl.health.BridgeClient", FakeClient)
    monkeypatch.setattr("unityctl.health.poll_until", raise_exited)

    result = check_compilation(make_context(project))

    assert result["status"] == "skipped"


def test_check_missing_scripts_skips_when_bridge_unreachable(tmp_path, monkeypatch):
    project = make_unity_project(tmp_path / "Game")

    def fake_discover(_path):
        raise DiscoveryError("not running")

    monkeypatch.setattr("unityctl.health.discover", fake_discover)

    result = check_missing_scripts(make_context(project))

    assert result["status"] == "skipped"


def test_check_missing_scripts_passes_when_nothing_found(tmp_path, monkeypatch):
    project = make_unity_project(tmp_path / "Game")

    class FakeClient:
        def __init__(self, *_args):
            pass

        def get_status(self):
            return {}

        def hierarchy_find(self, **_params):
            return {"nodes": []}

        def health_scan_prefabs(self):
            return {"ok": True, "jobId": "job-1"}

    monkeypatch.setattr("unityctl.health.discover", lambda _path: FAKE_INFO)
    monkeypatch.setattr("unityctl.health.BridgeClient", FakeClient)
    monkeypatch.setattr(
        "unityctl.health.wait_for_job",
        lambda *a, **k: {"result": {"assetsWithMissingScripts": []}},
    )

    result = check_missing_scripts(make_context(project))

    assert result["status"] == "pass"
    assert result["details"] == []


def test_check_missing_scripts_fails_when_loaded_scene_and_prefabs_have_hits(tmp_path, monkeypatch):
    project = make_unity_project(tmp_path / "Game")

    class FakeClient:
        def __init__(self, *_args):
            pass

        def get_status(self):
            return {}

        def hierarchy_find(self, **_params):
            return {"nodes": [{"path": "Canvas/Broken"}]}

        def health_scan_prefabs(self):
            return {"ok": True, "jobId": "job-1"}

    monkeypatch.setattr("unityctl.health.discover", lambda _path: FAKE_INFO)
    monkeypatch.setattr("unityctl.health.BridgeClient", FakeClient)
    monkeypatch.setattr(
        "unityctl.health.wait_for_job",
        lambda *a, **k: {"result": {"assetsWithMissingScripts": ["Assets/Prefabs/Broken.prefab"]}},
    )

    result = check_missing_scripts(make_context(project))

    assert result["status"] == "fail"
    assert any("Canvas/Broken" in detail for detail in result["details"])
    assert any("Broken.prefab" in detail for detail in result["details"])


def test_check_missing_scripts_warns_when_scan_job_fails_and_nothing_else_found(tmp_path, monkeypatch):
    project = make_unity_project(tmp_path / "Game")

    class FakeClient:
        def __init__(self, *_args):
            pass

        def get_status(self):
            return {}

        def hierarchy_find(self, **_params):
            return {"nodes": []}

        def health_scan_prefabs(self):
            return {"ok": True, "jobId": "job-1"}

    def raise_job_failed(*_a, **_k):
        raise JobFailed({"errorCode": "internal_error", "errorMessage": "boom"})

    monkeypatch.setattr("unityctl.health.discover", lambda _path: FAKE_INFO)
    monkeypatch.setattr("unityctl.health.BridgeClient", FakeClient)
    monkeypatch.setattr("unityctl.health.wait_for_job", raise_job_failed)

    result = check_missing_scripts(make_context(project))

    assert result["status"] == "warn"


def test_check_missing_scripts_skips_when_hierarchy_find_raises(tmp_path, monkeypatch):
    project = make_unity_project(tmp_path / "Game")

    class FakeClient:
        def __init__(self, *_args):
            pass

        def get_status(self):
            return {}

        def hierarchy_find(self, **_params):
            raise BridgeClientError("boom")

    monkeypatch.setattr("unityctl.health.discover", lambda _path: FAKE_INFO)
    monkeypatch.setattr("unityctl.health.BridgeClient", FakeClient)

    result = check_missing_scripts(make_context(project))

    assert result["status"] == "skipped"


# ---------------------------------------------------------------------------
# run_health
# ---------------------------------------------------------------------------


def test_run_health_rejects_unknown_check_name(tmp_path):
    project = make_unity_project(tmp_path / "Game")

    with pytest.raises(HealthError):
        run_health(project, make_effective_config(project), checks=["not_a_real_check"])


def test_run_health_runs_only_selected_checks(tmp_path, monkeypatch):
    project = make_unity_project(tmp_path / "Game")
    (project / "Packages" / "manifest.json").write_text(
        json.dumps({"dependencies": {}}), encoding="utf-8"
    )
    (project / "Packages" / "packages-lock.json").write_text(
        json.dumps({"dependencies": {}}), encoding="utf-8"
    )

    result = run_health(project, make_effective_config(project), checks=["packages"])

    assert [check["name"] for check in result["checks"]] == ["packages"]


def test_run_health_overall_status_is_worst_of_all_checks(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    # 缺 manifest.json -> packages check 会 fail；build_scenes 因 settings 文件缺失 -> warn。
    result = run_health(project, make_effective_config(project), checks=["packages", "build_scenes"])

    assert result["status"] == "fail"
    assert result["ok"] is False


def test_run_health_defaults_to_all_checks(tmp_path):
    project = make_unity_project(tmp_path / "Game")

    result = run_health(project, make_effective_config(project))

    assert [check["name"] for check in result["checks"]] == list(ALL_CHECKS)
    # compilation/missing_scripts 在没有 bridge.json 时应该被 skip，而不是抛异常。
    names_by_status = {check["name"]: check["status"] for check in result["checks"]}
    assert names_by_status["compilation"] == "skipped"
    assert names_by_status["missing_scripts"] == "skipped"
