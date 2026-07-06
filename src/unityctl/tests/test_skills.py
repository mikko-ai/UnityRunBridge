import json
from pathlib import Path

from unityctl import __version__
from unityctl import cli
from unityctl.skills import read_skill_version, render_skill_content


def make_unity_project(path: Path) -> Path:
    (path / "Assets").mkdir(parents=True)
    (path / "Packages").mkdir()
    (path / "ProjectSettings").mkdir()
    return path


def skill_path_in(project: Path) -> Path:
    return project / ".agents" / "skills" / "unityctl" / "SKILL.md"


def test_skills_init_installs_to_default_agents_dir(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")

    exit_code = cli.main(["--project", str(project), "skills", "init"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["code"] == "installed"
    skill_path = skill_path_in(project)
    assert output["skillPath"] == str(skill_path)
    content = skill_path.read_text(encoding="utf-8")
    # 版本占位符已替换为当前 CLI 版本
    assert f"x-unityctl-version: {__version__}" in content
    assert "__UNITYCTL_VERSION__" not in content


def test_skills_init_keeps_existing_skill(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    skill_path = skill_path_in(project)
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text("user edited content", encoding="utf-8")

    exit_code = cli.main(["--project", str(project), "skills", "init"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["code"] == "already_installed"
    assert "skills update" in output["hint"]
    assert skill_path.read_text(encoding="utf-8") == "user edited content"


def test_skills_update_overwrites_stale_skill(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    skill_path = skill_path_in(project)
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(
        "---\nname: unityctl\nx-unityctl-version: 0.0.1\n---\nold content\n",
        encoding="utf-8",
    )

    exit_code = cli.main(["--project", str(project), "skills", "update"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["code"] == "updated"
    assert output["version"] == __version__
    assert output["previousVersion"] == "0.0.1"
    assert skill_path.read_text(encoding="utf-8") == render_skill_content(__version__)


def test_skills_update_is_noop_when_up_to_date(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    cli.main(["--project", str(project), "skills", "init"])
    capsys.readouterr()

    exit_code = cli.main(["--project", str(project), "skills", "update"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["code"] == "up_to_date"


def test_skills_update_installs_when_missing(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")

    exit_code = cli.main(["--project", str(project), "skills", "update"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["code"] == "installed"
    assert skill_path_in(project).exists()


def test_skills_init_with_relative_target(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")

    exit_code = cli.main(
        ["--project", str(project), "skills", "init", "--target", ".cursor/skills"]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    skill_path = project / ".cursor" / "skills" / "unityctl" / "SKILL.md"
    assert output["skillPath"] == str(skill_path)
    assert skill_path.exists()


def test_skills_init_with_absolute_target_needs_no_project(tmp_path, capsys, monkeypatch):
    # 当前目录不是 Unity 项目，但 --target 是绝对路径时仍可安装
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "global-skills"

    exit_code = cli.main(["skills", "init", "--target", str(target)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    skill_path = target / "unityctl" / "SKILL.md"
    assert output["skillPath"] == str(skill_path)
    assert skill_path.exists()


def test_skills_default_target_requires_project_root(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)

    exit_code = cli.main(["skills", "init"])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().err)
    assert output["ok"] is False
    assert output["code"] == "invalid_request"


def test_read_skill_version_parses_frontmatter(tmp_path):
    skill_path = tmp_path / "SKILL.md"
    skill_path.write_text(
        "---\nname: unityctl\nx-unityctl-version: 1.2.3\n---\nbody\n", encoding="utf-8"
    )

    assert read_skill_version(skill_path) == "1.2.3"
    assert read_skill_version(tmp_path / "missing.md") is None
