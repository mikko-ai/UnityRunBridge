import json
from pathlib import Path

import pytest

from unityctl import __version__
from unityctl import cli
from unityctl import skills as skills_module
from unityctl.skills import (
    SkillError,
    distributed_skill_names,
    read_skill_version,
    render_skill_tree,
)


def make_unity_project(path: Path) -> Path:
    (path / "Assets").mkdir(parents=True)
    (path / "Packages").mkdir()
    (path / "ProjectSettings").mkdir()
    return path


def make_fake_assets(root: Path) -> Path:
    """构造两个内置 skill 的假资源树，隔离测试分发机制本身。"""
    alpha = root / "alpha"
    (alpha / "references").mkdir(parents=True)
    (alpha / "SKILL.md").write_text(
        "---\nname: alpha\nx-unityctl-version: __UNITYCTL_VERSION__\n---\nalpha body\n",
        encoding="utf-8",
    )
    (alpha / "references" / "deep.md").write_text("deep content\n", encoding="utf-8")
    beta = root / "beta"
    beta.mkdir()
    (beta / "SKILL.md").write_text(
        "---\nname: beta\nx-unityctl-version: __UNITYCTL_VERSION__\n---\nbeta body\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture
def fake_assets(tmp_path, monkeypatch) -> Path:
    root = make_fake_assets(tmp_path / "fake_assets")
    monkeypatch.setattr(skills_module, "SKILL_ASSETS_ROOT", root)
    return root


def run_skills(project: Path, subcommand: str, capsys) -> dict:
    exit_code = cli.main(["--project", str(project), "skills", subcommand])
    assert exit_code == 0
    return json.loads(capsys.readouterr().out)


# ---------- 渲染与资源发现 ----------


def test_distributed_skill_names_sorted(fake_assets):
    assert distributed_skill_names() == ["alpha", "beta"]


def test_render_skill_tree_replaces_placeholder_only_in_main(fake_assets):
    tree = render_skill_tree("alpha", "9.9.9")
    assert set(tree) == {"SKILL.md", "references/deep.md"}
    assert "x-unityctl-version: 9.9.9" in tree["SKILL.md"]
    assert "__UNITYCTL_VERSION__" not in tree["SKILL.md"]
    assert tree["references/deep.md"] == "deep content\n"


def test_render_skill_tree_requires_placeholder(fake_assets):
    (fake_assets / "alpha" / "SKILL.md").write_text(
        "---\nname: alpha\n---\nno placeholder\n", encoding="utf-8"
    )
    with pytest.raises(SkillError):
        render_skill_tree("alpha", "9.9.9")


# ---------- init ----------


def test_skills_init_installs_all_skills(fake_assets, tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")

    output = run_skills(project, "init", capsys)

    assert output["ok"] is True
    assert output["code"] == "installed"
    assert output["version"] == __version__
    assert [s["name"] for s in output["skills"]] == ["alpha", "beta"]
    for entry in output["skills"]:
        skill_dir = Path(entry["skillPath"])
        assert entry["action"] == "installed"
        content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        assert f"x-unityctl-version: {__version__}" in content
    assert (project / ".agents" / "skills" / "alpha" / "references" / "deep.md").exists()


def test_skills_init_keeps_existing_dir(fake_assets, tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    alpha_dir = project / ".agents" / "skills" / "alpha"
    alpha_dir.mkdir(parents=True)
    (alpha_dir / "SKILL.md").write_text("user edited content", encoding="utf-8")

    output = run_skills(project, "init", capsys)

    # alpha 保持原样（旧单文件形态也算已安装），beta 正常安装
    assert output["code"] == "installed"  # 变更程度最高的 action
    actions = {s["name"]: s["action"] for s in output["skills"]}
    assert actions == {"alpha": "already_installed", "beta": "installed"}
    assert "skills update" in output["hint"]
    assert (alpha_dir / "SKILL.md").read_text(encoding="utf-8") == "user edited content"


# ---------- update ----------


def test_skills_update_overwrites_stale_tree_and_removes_leftovers(
    fake_assets, tmp_path, capsys
):
    project = make_unity_project(tmp_path / "Game")
    run_skills(project, "init", capsys)
    alpha_dir = project / ".agents" / "skills" / "alpha"
    # 模拟旧版本：改内容 + 塞一个已废弃的残留文件
    (alpha_dir / "SKILL.md").write_text(
        "---\nname: alpha\nx-unityctl-version: 0.0.1\n---\nold body\n",
        encoding="utf-8",
    )
    (alpha_dir / "references" / "stale.md").write_text("stale", encoding="utf-8")

    output = run_skills(project, "update", capsys)

    actions = {s["name"]: s["action"] for s in output["skills"]}
    assert actions["alpha"] == "updated"
    assert actions["beta"] == "up_to_date"
    assert output["code"] == "updated"
    alpha_entry = next(s for s in output["skills"] if s["name"] == "alpha")
    assert alpha_entry["previousVersion"] == "0.0.1"
    assert not (alpha_dir / "references" / "stale.md").exists()
    assert f"x-unityctl-version: {__version__}" in (alpha_dir / "SKILL.md").read_text(
        encoding="utf-8"
    )


def test_skills_update_upgrades_legacy_single_file_install(
    fake_assets, tmp_path, capsys
):
    # 旧版单文件安装（目录下只有 SKILL.md）经 update 升级为完整目录树
    project = make_unity_project(tmp_path / "Game")
    alpha_dir = project / ".agents" / "skills" / "alpha"
    alpha_dir.mkdir(parents=True)
    (alpha_dir / "SKILL.md").write_text(
        "---\nname: alpha\nx-unityctl-version: 0.0.1\n---\nlegacy\n", encoding="utf-8"
    )

    output = run_skills(project, "update", capsys)

    actions = {s["name"]: s["action"] for s in output["skills"]}
    assert actions["alpha"] == "updated"
    assert (alpha_dir / "references" / "deep.md").exists()


def test_skills_update_is_noop_when_up_to_date(fake_assets, tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    run_skills(project, "init", capsys)

    output = run_skills(project, "update", capsys)

    assert output["code"] == "up_to_date"
    assert all(s["action"] == "up_to_date" for s in output["skills"])


def test_skills_update_installs_when_missing(fake_assets, tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")

    output = run_skills(project, "update", capsys)

    assert output["code"] == "installed"


def test_skills_update_never_touches_user_skills(fake_assets, tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    run_skills(project, "init", capsys)
    user_dir = project / ".agents" / "skills" / "my-game-ui"
    user_dir.mkdir(parents=True)
    (user_dir / "SKILL.md").write_text("mine", encoding="utf-8")

    run_skills(project, "update", capsys)

    assert (user_dir / "SKILL.md").read_text(encoding="utf-8") == "mine"


# ---------- target 解析（沿用旧行为） ----------


def test_skills_init_with_relative_target(fake_assets, tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")

    exit_code = cli.main(
        ["--project", str(project), "skills", "init", "--target", ".cursor/skills"]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    alpha_entry = next(s for s in output["skills"] if s["name"] == "alpha")
    assert alpha_entry["skillPath"] == str(project / ".cursor" / "skills" / "alpha")


def test_skills_init_with_absolute_target_needs_no_project(
    fake_assets, tmp_path, capsys, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "global-skills"

    exit_code = cli.main(["skills", "init", "--target", str(target)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert (target / "alpha" / "SKILL.md").exists()
    assert output["code"] == "installed"


def test_skills_default_target_requires_project_root(fake_assets, tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)

    exit_code = cli.main(["skills", "init"])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().err)
    assert output["ok"] is False
    assert output["code"] == "invalid_request"


# ---------- 版本读取 ----------


def test_read_skill_version_reads_main_skill_md(tmp_path):
    skill_dir = tmp_path / "some-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: x\nx-unityctl-version: 1.2.3\n---\nbody\n", encoding="utf-8"
    )

    assert read_skill_version(skill_dir) == "1.2.3"
    assert read_skill_version(tmp_path / "missing") is None


# ---------- 真实内置资源冒烟 ----------


def test_real_assets_install(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")

    output = run_skills(project, "init", capsys)

    names = [s["name"] for s in output["skills"]]
    # Task 1 阶段内置资源只有 unityctl；完整双 skill 断言在 Task 3 补强，此处勿提前改严
    assert "unityctl" in names
    skill_md = project / ".agents" / "skills" / "unityctl" / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")
    assert f"x-unityctl-version: {__version__}" in content
    assert "__UNITYCTL_VERSION__" not in content
