# Skill 体系与 Project Skill Creator 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把官方 unityctl skill 从单文件重构为目录形态（渐进式披露），`skills.py` 改为目录分发并新增聚合 CLI 契约，新增 `unityctl-project-skill-creator` skill（v1 含 ui-location flow）。

**Architecture:** 内置 skill 资源从 `skill_assets/SKILL.md` 单文件改为 `skill_assets/<skill 名>/` 子目录（自动发现，当前两个：`unityctl`、`unityctl-project-skill-creator`）。`skills.py` 渲染整棵目录树（仅主 `SKILL.md` 做版本占位符替换），`init` 补缺不覆盖、`update` 差异时先删整目录再写。`cmd_skills` 返回聚合结构。creator 与 flow 是纯 markdown 内容，无新 CLI 代码。

**Tech Stack:** Python 3.11+、pytest、setuptools（package-data 递归 glob）。

**Spec:** `docs/superpowers/specs/2026-07-09-skill-system-and-creator-design.md`（下称 spec）。

## Global Constraints

- 对话/注释/文档用中文，专业术语保留英文（AGENTS_RULE.md）。
- 官方分发 skill 固定两个目录名：`unityctl`、`unityctl-project-skill-creator`；用户自建目录永不触碰。
- 版本占位符 `__UNITYCTL_VERSION__` 只出现在各 skill 主 `SKILL.md`，`references/`、`flows/` 按原文分发。
- `update` 语义：渲染树与目标树逐文件比较（文件集合 + 内容全等），有差异则先 `rmtree` 整个目标 skill 目录再整树写入。
- CLI 聚合 `code` 优先级：`installed` > `updated` > `already_installed` > `up_to_date`；任一失败抛异常（`ok: false`、退出码 1）。
- 官方 `unityctl` 主 SKILL.md 收缩到约百行；拆分不允许静默删减内容（按 spec 第三节映射表搬运）。
- creator 生成物禁止复述 unityctl 命令用法；creator 为被动调用（`disable-model-invocation: true`）。
- 测试运行方式：`cd src/unityctl && uv run pytest tests/test_skills.py -v`。
- 提交信息风格参照 git log：`feat: ...` / `docs: ...` / `test: ...`。

---

### Task 1: `skills.py` 目录分发 + CLI 聚合契约 + 打包

**Files:**
- Modify: `src/unityctl/unityctl/skills.py`（整文件重写）
- Modify: `src/unityctl/unityctl/cli.py`（`cmd_skills` 与 import、`skills` 子命令 help 文案）
- Modify: `src/unityctl/pyproject.toml:25`（package-data glob）
- Move: `src/unityctl/unityctl/skill_assets/SKILL.md` → `src/unityctl/unityctl/skill_assets/unityctl/SKILL.md`
- Test: `src/unityctl/tests/test_skills.py`（整文件重写）

**Interfaces:**
- Consumes: 现有 `resolve_skills_dir(project_path, target)`（保持不变）、`__version__`。
- Produces（后续 Task 依赖）:
  - `distributed_skill_names() -> list[str]`：`skill_assets/` 下子目录名排序列表。
  - `render_skill_tree(skill_name: str, version: str) -> dict[str, str]`：`{相对路径: 内容}`。
  - `install_skill(skills_dir: Path, skill_name: str, version: str, overwrite: bool) -> SkillResult`。
  - `install_all_skills(skills_dir: Path, version: str, overwrite: bool) -> list[SkillResult]`。
  - `SkillResult(name, skill_path, action, version, previous_version)`，`skill_path` 是**目录**。
  - `read_skill_version(skill_dir: Path) -> str | None`（参数从文件改为目录）。
  - CLI 输出 schema：`{"ok", "code", "version", "skills": [{"name", "action", "skillPath", "previousVersion"?}], "hint"?}`。
  - 聚合 `code` 是四级全序（不是两组等价）：`installed` > `updated` > `already_installed` > `up_to_date`；`installed` 与 `updated` 并存时顶层为 `installed`。任一 skill 抛 `SkillError` 则整个命令失败（`ok: false`、退出码 1，已写入的不回滚）。

- [ ] **Step 1: 移动现有 skill 资源到子目录**

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge
mkdir -p src/unityctl/unityctl/skill_assets/unityctl
git mv src/unityctl/unityctl/skill_assets/SKILL.md src/unityctl/unityctl/skill_assets/unityctl/SKILL.md
```

- [ ] **Step 2: 重写测试为目录分发语义（先写失败测试）**

用以下内容整体替换 `src/unityctl/tests/test_skills.py`：

```python
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
```

- [ ] **Step 3: 运行测试确认失败**

```bash
cd src/unityctl && uv run pytest tests/test_skills.py -v
```

Expected: FAIL / ERROR（`ImportError: cannot import name 'distributed_skill_names'` 等）。

- [ ] **Step 4: 重写 `skills.py`**

用以下内容整体替换 `src/unityctl/unityctl/skills.py`：

```python
"""Agent skill 的安装与更新。

skill 内容作为 CLI 包内资源（skill_assets/<skill 名>/ 目录）随版本发布，
安装时把各 skill 主 SKILL.md 中的版本占位符替换为当前 CLI 版本后整目录写入。
语义与 init 对配置文件的处理保持一致：init 只补缺失、绝不覆盖；
update 有差异时先删除整个目标 skill 目录再整树写入（清除已废弃的旧文件）。
"""

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

SKILL_FILENAME = "SKILL.md"
DEFAULT_SKILLS_DIRNAME = ".agents/skills"

SKILL_ASSETS_ROOT = Path(__file__).parent / "skill_assets"
VERSION_PLACEHOLDER = "__UNITYCTL_VERSION__"
VERSION_FIELD_PATTERN = re.compile(r"^x-unityctl-version:\s*(\S+)\s*$", re.MULTILINE)


class SkillError(RuntimeError):
    pass


@dataclass(frozen=True)
class SkillResult:
    name: str
    # 安装后的 skill 目录（不是主 SKILL.md 文件）
    skill_path: Path
    # installed / already_installed / updated / up_to_date
    action: str
    version: str
    previous_version: str | None


def distributed_skill_names() -> list[str]:
    """内置分发清单：skill_assets/ 下的子目录名（排序）。"""
    if not SKILL_ASSETS_ROOT.is_dir():
        raise SkillError(f"内置 skill 资源目录不存在：{SKILL_ASSETS_ROOT}")
    names = sorted(p.name for p in SKILL_ASSETS_ROOT.iterdir() if p.is_dir())
    if not names:
        raise SkillError(f"内置 skill 资源目录为空：{SKILL_ASSETS_ROOT}")
    return names


def render_skill_tree(skill_name: str, version: str) -> dict[str, str]:
    """渲染单个 skill 的目录树：{相对路径: 文件内容}。

    仅主 SKILL.md 做版本占位符替换（必须包含占位符），其余文件按原文分发。
    """
    source_dir = SKILL_ASSETS_ROOT / skill_name
    if not source_dir.is_dir():
        raise SkillError(f"未知的内置 skill：{skill_name}")
    tree: dict[str, str] = {}
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(source_dir).as_posix()
        content = path.read_text(encoding="utf-8")
        if rel == SKILL_FILENAME:
            if VERSION_PLACEHOLDER not in content:
                raise SkillError(
                    f"skill {skill_name} 的主 {SKILL_FILENAME} 缺少版本占位符 {VERSION_PLACEHOLDER}"
                )
            content = content.replace(VERSION_PLACEHOLDER, version)
        tree[rel] = content
    if SKILL_FILENAME not in tree:
        raise SkillError(f"skill {skill_name} 缺少主 {SKILL_FILENAME}")
    return tree


def read_skill_version(skill_dir: Path) -> str | None:
    skill_md = skill_dir / SKILL_FILENAME
    if not skill_md.exists():
        return None
    match = VERSION_FIELD_PATTERN.search(skill_md.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def resolve_skills_dir(project_path: Path | None, target: str | None) -> Path:
    """解析 skills 根目录：--target 为绝对路径时直接使用；
    相对路径（含默认值）基于项目根目录解析。"""
    raw = Path(target).expanduser() if target else Path(DEFAULT_SKILLS_DIRNAME)
    if raw.is_absolute():
        return raw
    if project_path is None:
        raise SkillError("使用相对 --target 时需要能定位项目根目录")
    return project_path / raw


def _read_installed_tree(skill_dir: Path) -> dict[str, str]:
    tree: dict[str, str] = {}
    for path in sorted(skill_dir.rglob("*")):
        if path.is_file():
            tree[path.relative_to(skill_dir).as_posix()] = path.read_text(
                encoding="utf-8"
            )
    return tree


def _write_tree(skill_dir: Path, tree: dict[str, str]) -> None:
    for rel, content in tree.items():
        target = skill_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def install_skill(
    skills_dir: Path, skill_name: str, version: str, overwrite: bool
) -> SkillResult:
    """把内置 skill 目录写入 <skills_dir>/<skill_name>/。

    overwrite=False（init）：目录已存在（含旧版单文件形态）时保持原样。
    overwrite=True（update）：树有差异则先删整目录再写；未安装时直接安装。
    """
    skill_dir = skills_dir / skill_name
    tree = render_skill_tree(skill_name, version)

    if not skill_dir.exists():
        _write_tree(skill_dir, tree)
        return SkillResult(skill_name, skill_dir, "installed", version, None)

    previous_version = read_skill_version(skill_dir)
    if not overwrite:
        return SkillResult(
            skill_name, skill_dir, "already_installed", version, previous_version
        )

    if _read_installed_tree(skill_dir) == tree:
        return SkillResult(
            skill_name, skill_dir, "up_to_date", version, previous_version
        )

    shutil.rmtree(skill_dir)
    _write_tree(skill_dir, tree)
    return SkillResult(skill_name, skill_dir, "updated", version, previous_version)


def install_all_skills(
    skills_dir: Path, version: str, overwrite: bool
) -> list[SkillResult]:
    """依次安装全部内置 skill。

    任一失败（内置资源损坏、IO 错误）直接抛 SkillError 让整个命令失败，
    已写入的不回滚——失败源头都是环境级问题，部分成功语义没有价值。
    """
    return [
        install_skill(skills_dir, name, version, overwrite)
        for name in distributed_skill_names()
    ]
```

- [ ] **Step 5: 更新 `cli.py`**

5a. 修改 import（`src/unityctl/unityctl/cli.py` 第 59-64 行附近）：

```python
from unityctl.skills import (
    DEFAULT_SKILLS_DIRNAME,
    SkillError,
    install_all_skills,
    resolve_skills_dir,
)
```

5b. 更新 `skills` 子命令 help 文案（第 887 行附近的 `add_parser("skills", ...)`）：

```python
    skills = subparsers.add_parser(
        "skills",
        help="安装或更新内置 agent skills（目录形态）",
        description=(
            "把 CLI 内置的官方 skills（unityctl 参考手册、project skill creator）"
            f"安装到项目的 skills 目录，默认 {DEFAULT_SKILLS_DIRNAME}/。"
        ),
        formatter_class=_HelpFormatter,
    )
```

同时更新 `skills_init` / `skills_update` 两个子命令的 help（第 903-912 行附近），新语义是树比较而非"总是覆盖"：

```python
    skills_init = skills_subparsers.add_parser(
        "init",
        help="安装 skills（目录已存在时不覆盖）",
        formatter_class=_HelpFormatter,
    )
    skills_update = skills_subparsers.add_parser(
        "update",
        help="把 skills 刷新为当前 CLI 版本内置内容（有差异时整目录覆盖；无差异返回 up_to_date；未安装则直接安装）",
        formatter_class=_HelpFormatter,
    )
```

5c. 用以下内容整体替换 `cmd_skills` 函数（第 1945-1973 行）：

```python
# 聚合 code 取"变更程度最高"的 action（索引越小优先级越高）
_SKILL_ACTION_PRIORITY = ["installed", "updated", "already_installed", "up_to_date"]


def cmd_skills(args: argparse.Namespace) -> dict[str, Any]:
    # 绝对路径 --target 不依赖项目根目录，找不到项目也允许安装
    project_path: Path | None = None
    try:
        project_path = find_unity_project_root(args.project_path or Path.cwd())
    except ConfigError:
        pass

    try:
        skills_dir = resolve_skills_dir(project_path, args.target)
        results = install_all_skills(
            skills_dir,
            version=__version__,
            overwrite=args.skills_command == "update",
        )
    except SkillError as exc:
        raise CliError("invalid_request", str(exc)) from exc

    entries: list[dict[str, Any]] = []
    for result in results:
        entry: dict[str, Any] = {
            "name": result.name,
            "action": result.action,
            "skillPath": str(result.skill_path),
        }
        if result.previous_version is not None and result.previous_version != result.version:
            entry["previousVersion"] = result.previous_version
        entries.append(entry)

    payload: dict[str, Any] = {
        "ok": True,
        "code": min((r.action for r in results), key=_SKILL_ACTION_PRIORITY.index),
        "version": __version__,
        "skills": entries,
    }
    if any(r.action == "already_installed" for r in results):
        payload["hint"] = "已存在的 skill 未被覆盖；如需刷新为当前版本内容请运行 unityctl skills update"
    return payload
```

- [ ] **Step 6: 更新打包 glob**

修改 `src/unityctl/pyproject.toml` 第 25 行：

```toml
[tool.setuptools.package-data]
unityctl = ["schemas/*.json", "skill_assets/**/*.md"]
```

- [ ] **Step 7: 运行测试确认通过**

```bash
cd src/unityctl && uv run pytest tests/test_skills.py -v
```

Expected: 全部 PASS。再跑全量确认无回归：

```bash
cd src/unityctl && uv run pytest -q
```

- [ ] **Step 8: 验证 wheel 包含嵌套资源**

```bash
cd src/unityctl && rm -rf dist && uv build && unzip -l dist/unity_run_bridge-*.whl | grep skill_assets
```

Expected: `uv build` 成功，输出中含 `skill_assets/unityctl/SKILL.md`。验证后 `rm -rf dist`（不提交）。

- [ ] **Step 9: Commit**

```bash
git add -A src/unityctl && git commit -m "feat: distribute agent skills as directories with aggregated CLI contract"
```

---

### Task 2: 官方 unityctl skill 拆分为主文件 + references/

**Files:**
- Modify: `src/unityctl/unityctl/skill_assets/unityctl/SKILL.md`（收缩为主文件）
- Create: `src/unityctl/unityctl/skill_assets/unityctl/references/logs.md`
- Create: `src/unityctl/unityctl/skill_assets/unityctl/references/hierarchy.md`
- Create: `src/unityctl/unityctl/skill_assets/unityctl/references/interaction.md`
- Create: `src/unityctl/unityctl/skill_assets/unityctl/references/gameplay.md`
- Create: `src/unityctl/unityctl/skill_assets/unityctl/references/scenario.md`
- Create: `src/unityctl/unityctl/skill_assets/unityctl/references/profiling-build-health.md`
- Create: `src/unityctl/unityctl/skill_assets/unityctl/references/error-codes.md`

**Interfaces:**
- Consumes: Task 1 的目录分发机制（子目录文件自动进入分发树）。
- Produces: 无代码接口；Task 4 会在本任务产出的主 SKILL.md 索引表末尾加一行。

**内容搬运规则（不允许静默删减）：** 现有 `skill_assets/unityctl/SKILL.md` 的章节按下表**原样搬运**到 references 文件（含全部代码块与表格）；每个 reference 文件加统一头部（见 Step 1 模板）。唯一允许的改动是**修正跨文件指称**：原文中"见上文"/"见下文"若指向的内容拆到了别的文件，改为指向具体文件（已知两处：错误码表 `node_not_found` 行的"见上文"→"见 `hierarchy.md`"；录制节指向 Scenario 的"见下文"→"见 `scenario.md`"；搬运时再全文检查一遍是否还有其他处）。

| 现有章节标题 | 目标文件 |
|---|---|
| `## 日志与排错`（含 log-rules JSON 示例与 watch 说明） | `references/logs.md` |
| `## 查询场景 Hierarchy（只读）` | `references/hierarchy.md` |
| `## 截图（需 Play Mode）`、`## UI 操作（点击/输入/设值，需 Play Mode）`、`## 录制 UGUI 语义动作（需 Play Mode）` | `references/interaction.md`（按此顺序拼接） |
| `## Gameplay 命令（零侵入调用游戏代码，需 Play Mode，默认关闭）` | `references/gameplay.md` |
| `## Scenario：可复跑的自动化验证脚本` | `references/scenario.md` |
| `## 性能采样（ProfilerRecorder，需 Play Mode）`、`## 构建（独立进程，不经过 Bridge）`、`## 项目健康检查（unityctl health）` | `references/profiling-build-health.md`（按此顺序拼接） |
| `## 常见错误码`（完整表格） | `references/error-codes.md` |

- [ ] **Step 1: 创建 7 个 reference 文件**

每个文件的头部为（`<适用场景>` 按下表替换，其后紧跟按上表搬运的原文，原章节标题降为 `##` 保留）：

```markdown
# unityctl reference：<文件主题>

适用场景：<适用场景>。命令输出均为 JSON 信封（成功 `{"ok": true, ...}`，失败 stderr `{"ok": false, "code", "message"}`）。
```

| 文件 | 文件主题 | 适用场景 |
|---|---|---|
| logs.md | 日志与排错 | 查询/过滤 Unity Console 日志、排查错误、配置 log-rules（ignore 降噪 / watch 聚焦） |
| hierarchy.md | Hierarchy 查询 | 以只读方式查询场景 Hierarchy 结构（roots/tree/find/ancestors/inspect） |
| interaction.md | UI 操作 / 截图 / 录制 | 模拟 UI 操作（click/input/set-value）、截图（snapshot）、录制语义动作（record） |
| gameplay.md | Gameplay 命令桥 | 绕开 UI 直接调用游戏逻辑（gameplay list/invoke），默认关闭需配置开启 |
| scenario.md | Scenario 验证脚本 | 编写/校验/执行可复跑验证脚本（scenario validate/run/from-recording） |
| profiling-build-health.md | 性能 / 构建 / 健康检查 | 性能采样（profile）、Player 构建诊断（build）、项目健康检查（health） |
| error-codes.md | 完整错误码表 | 遇到主文件高频表之外的错误码时查询 |

- [ ] **Step 2: 重写主 SKILL.md**

保留现有的 frontmatter、开头介绍段、`## 核心工作流：改完代码后验证`（全部原文）、`## 环境准备`（全部原文）、`## 注意事项`（全部原文），删除已搬走的章节，并在「环境准备」之后插入以下两节：

```markdown
## 能力索引

执行下列能力前，**必须先读取对应的 reference 文件**（相对本文件的 `references/` 目录），不要凭记忆猜测参数：

| 能力 | 命令 | reference |
|---|---|---|
| 日志查询与排错、log-rules 降噪/聚焦 | `logs` / `errors` | `references/logs.md` |
| 场景 Hierarchy 结构化查询（只读） | `hierarchy` | `references/hierarchy.md` |
| UI 操作、截图、动作录制 | `click` / `input` / `set-value` / `snapshot` / `record` | `references/interaction.md` |
| 零侵入调用游戏逻辑 | `gameplay` | `references/gameplay.md` |
| 可复跑验证脚本 | `scenario` | `references/scenario.md` |
| 性能采样 / Player 构建 / 健康检查 | `profile` / `build` / `health` | `references/profiling-build-health.md` |

## 高频错误码

完整错误码表见 `references/error-codes.md`，以下是最常见的 5 个：

| code | 含义与处理 |
|------|-----------|
| `compilation_failed` | 编译错误，读取 `compilationErrors` 修复代码后重跑 `unityctl refresh` |
| `timeout` | 等待状态收敛超时，可用 `--timeout <秒>` 放宽后重试 |
| `editor_exited` | Unity Editor 进程退出，运行 `unityctl start` 重新启动 |
| `editor_already_running` | 项目被占用但 Bridge 未就绪，运行 `unityctl doctor` 检查 |
| `bridge_unreachable` | Bridge 不可达，通常 Editor 未启动，运行 `unityctl start` |
```

frontmatter 的 `description` 保持现状（它已只描述验证主链路，不罗列子能力），`x-unityctl-version: __UNITYCTL_VERSION__` 保留。

- [ ] **Step 3: 核对完整性与行数**

```bash
cd src/unityctl/unityctl/skill_assets/unityctl
wc -l SKILL.md references/*.md
grep -c "^##" SKILL.md
```

Expected: 主 SKILL.md ≤ 120 行；逐项核对搬运表——旧文件每个 `##` 章节都能在主文件或某个 reference 中找到（无静默删减）。

- [ ] **Step 4: 运行测试确认通过**

```bash
cd src/unityctl && uv run pytest tests/test_skills.py -v
```

Expected: 全部 PASS（`test_real_assets_install` 验证真实资源仍可安装且含 references）。

- [ ] **Step 5: Commit**

```bash
git add src/unityctl/unityctl/skill_assets && git commit -m "docs: split unityctl skill into lean main file with progressive references"
```

---

### Task 3: creator skill（入口 + ui-location flow）

**Files:**
- Create: `src/unityctl/unityctl/skill_assets/unityctl-project-skill-creator/SKILL.md`
- Create: `src/unityctl/unityctl/skill_assets/unityctl-project-skill-creator/flows/ui-location.md`
- Modify: `src/unityctl/tests/test_skills.py`（`test_real_assets_install` 增加断言）

**Interfaces:**
- Consumes: Task 1 的目录分发机制。
- Produces: 分发清单从 1 个 skill 变为 2 个（`distributed_skill_names()` 自动发现，无代码改动）。

- [ ] **Step 1: 创建 creator 入口 SKILL.md**

写入 `src/unityctl/unityctl/skill_assets/unityctl-project-skill-creator/SKILL.md`：

```markdown
---
name: unityctl-project-skill-creator
description: 为当前 Unity 项目生成项目专属的 agent skill（如 UI 定位方法论）。仅在用户显式要求生成或更新项目 skill 时使用，禁止在普通任务中自主触发。
disable-model-invocation: true
x-unityctl-version: __UNITYCTL_VERSION__
---

# unityctl Project Skill Creator

你是一次「知识蒸馏」流程的引导者：把只存在于当前项目里的约定，蒸馏成一份 agent 可加载的项目 skill，写入项目 `.agents/skills/` 下的新目录。本 skill 自身不承载任何项目知识。

## 共享原则（所有 flow 必须遵守）

1. **约定优先于路径**：产出以规则层（架构级约定）为主体，规则腐烂慢、能直接翻译成查询；不生成大而全的路径快照。
2. **验证优先于生成**：每条候选规则写入前必须翻译成 `unityctl hierarchy find` 查询当场跑一遍，结果与预期比对，通过才写入，并把验证过的查询作为示例写进生成物。
3. **诚实原则**：例外如实记录；覆盖率不足的规则标注「部分适用」及范围；完全无规律时诚实输出「该项目无统一约定」并把规则层降级为探测指引——这是合法产物，不算失败。禁止把未经验证的规则标注为已验证；用户口述、无法机械验证的信息可以写入，但必须标注 `用户口述，未验证`。
4. **生成物克制**：只写项目知识，禁止复述任何 unityctl 命令用法（用法以官方 unityctl skill 为准）；产物为单份 SKILL.md，不建多文件知识库。
5. **内置自愈**：生成物末尾必须包含「自愈指引」一节（模板见各 flow）。

## 知识域路由（封闭枚举）

根据用户诉求匹配下表。诉求不属于任何已知域时，明确回答「该类知识 creator 尚不支持，建议手写进你自己的项目 skill」，**禁止即兴发明新流程**。

| 知识域 | 判断特征 | flow 文件 |
|---|---|---|
| UI 定位方法论 | 用户想让 agent 更快找到界面、枚举有哪些界面、判断哪个界面在最上方 | `flows/ui-location.md` |

## 执行方式

1. 确定知识域后，读取对应 flow 文件并严格按其步骤执行，不跳步、不增步。
2. 访谈问题一次只问一个，总数不超过 flow 规定的上限。
3. 写入生成物前，把将要写入的内容概要给用户确认。
```

- [ ] **Step 2: 创建 flows/ui-location.md**

写入 `src/unityctl/unityctl/skill_assets/unityctl-project-skill-creator/flows/ui-location.md`：

```markdown
# Flow：UI 定位方法论

产出一份项目专属 skill，回答三个问题（**不做具体界面的知识**：不列界面清单、不记"某界面怎么打开"）：

1. 界面存在于哪几个树形根节点下（含 `DontDestroyOnLoad` 常驻层）。
2. 想枚举当前有哪些界面，用什么规则、什么查询。
3. 怎么判断哪个界面在最上方（本项目的置顶机制）。

## 阶段 A：环境检查

1. 运行 `unityctl doctor`。
2. Bridge 可达（或 `unityctl start` 能成功启动 Editor）→ 运行 `unityctl status` 确认 `editorState`，然后走探测路径（阶段 B-D）。
3. Editor 不可用且无法启动 → 询问用户：走「纯问答降级模式」（见文末），还是等环境就绪后再来。

## 阶段 B：探测（严格遵守上限）

若尚未在 Play Mode，先 `unityctl play`（进不了 Play Mode 时可在编辑态探测，生成物中如实注明探测时机）。

上限：`tree` 展开深度 ≤ 3；`inspect` 抽查节点 ≤ 10；`find` 只取首页（50 条）不翻页；`roots` 全量。

1. `unityctl hierarchy roots` —— 记录所有已加载场景与根节点。
2. 对疑似 UI 根（含 Canvas 的根、名字含 UI/Canvas/Root 的根）：`unityctl hierarchy tree <root> --depth 3`。
3. `unityctl hierarchy find --component Canvas --active-only` 采样整体分布。
4. 对 3-5 个疑似「界面」节点 `unityctl hierarchy inspect <path>`，记录组件构成的共性。

## 阶段 C：归纳候选规则（只限四类）

- 命名后缀规律（如多数界面以 `Panel` / `Window` 结尾）。
- 公共标记组件（如都挂某个 UI 基类组件）。
- UI 根结构（界面都在哪几棵子树下）。
- 置顶机制。常见形态提示（仅是提示，不是唯一答案）：
  - 同一 Canvas 下以 sibling 顺序决定（最后一个 active 的 sibling 在最上）。
  - 每界面独立 Canvas，以 `sortingOrder` 决定；查询：`hierarchy find --component Canvas --sort-by Canvas.sortingOrder --desc --page-size 1`。
  - UIManager 内部栈管理（hierarchy 看不出来）：诚实写明「以 sibling 顺序近似」或「需 gameplay 命令查询」。

## 阶段 D：验证与访谈（访谈 ≤ 5 个问题，一次只问一个）

标准问题（按需选用，不必全问）：

1. 探测到的 UI 根节点清单是否完整？
2. 请打开 1-2 个当前不在场景中的界面（懒加载），验证识别规则是否依然成立。
3. 请依次打开两个界面，我跑置顶查询比对实际置顶情况。
4. 有哪些已知不符合规则的界面（例外）？
5. 生成物 skill 名称确认（默认 `<游戏名>-ui`）。

每条候选规则翻译成 `find` 查询跑一遍：结果符合预期 → 写入规则层（附该查询）；覆盖率不足 → 标「部分适用」+ 适用范围；不符 → 进例外清单或丢弃。

四类候选规则全部验证失败（该项目无统一约定）时，不放弃生成：在「界面识别与枚举」节写明「该项目无统一约定」，并降级为**探测指引**——记录本次探测中实际有效的定位方式（例如"UI 集中在 `<某根节点>` 下，需逐层 `tree` 展开确认"），这是合法产物。

## 阶段 E：生成

- `<游戏名>` 默认取 `ProjectSettings/ProjectSettings.asset` 的 `productName`（读不到就问用户），转小写、空格与非法字符转 `-`。
- 目标路径 `.agents/skills/<游戏名>-ui/SKILL.md`；目录已存在时询问「全量重建覆盖，还是换个名字」——只支持全量重建，不做增量修改。
- 写入前把内容概要给用户确认。
- 按以下模板生成，六节缺一不可；查询示例只写「本项目专用的具体查询」，禁止出现任何 unityctl 命令教学内容：

~~~markdown
---
name: <游戏名>-ui
description: 在 <游戏名> 项目中定位、枚举、操作 UI 界面或判断界面层级时使用。
---

# <游戏名> UI 定位

## UI 根节点

（界面存在于哪几棵子树；每条注明来源：`探测验证` 或 `用户口述，未验证`）

## 界面识别与枚举

（识别规则；每条附验证过的具体查询与覆盖率说明。无统一约定时写「该项目无统一约定」+ 探测指引，见阶段 D）

## 最上方判断

（本项目的置顶机制 + 对应的具体查询）

## 例外清单

（不符合规则的已知界面；无例外时写「暂未发现」）

## 自愈指引

本文件中的查询失效（如 `node_not_found`）时：先用「界面识别与枚举」中的规则重新探测定位；定位成功后提示用户本文件已过时，建议重跑 unityctl-project-skill-creator 全量重建。
~~~

## 纯问答降级模式（Editor 不可用时）

- 跳过阶段 B / D 的探测与验证，规则全部来自用户访谈，一律标注 `用户口述，未验证`。
- 生成物结构不变（六节齐全），并在正文开头加声明：「本文件生成时未经探测验证，建议 Editor 可用时重跑 creator 校验。」
- 这是合法产物：硬门槛是"禁止把未验证的规则标成已验证"，不是"没有验证就不能生成"。
```

- [ ] **Step 3: 补强真实资源测试**

在 `src/unityctl/tests/test_skills.py` 的 `test_real_assets_install` 末尾追加断言：

```python
    assert names == ["unityctl", "unityctl-project-skill-creator"]
    creator_dir = project / ".agents" / "skills" / "unityctl-project-skill-creator"
    creator_md = (creator_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "disable-model-invocation: true" in creator_md
    assert (creator_dir / "flows" / "ui-location.md").exists()
    assert (
        project / ".agents" / "skills" / "unityctl" / "references" / "error-codes.md"
    ).exists()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd src/unityctl && uv run pytest tests/test_skills.py -v
```

Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add -A src/unityctl && git commit -m "feat: add unityctl-project-skill-creator skill with ui-location flow"
```

---

### Task 4: 用户扩展文档 + README 现状同步

**Files:**
- Modify: `README.md`（更新既有 Agent Skill 相关表述 + 新增自定义 skill 一节）
- Modify: `src/unityctl/unityctl/skill_assets/unityctl/SKILL.md`（能力索引表后加一行说明）

**Interfaces:**
- Consumes: Task 2 的主 SKILL.md、Task 3 的 creator。
- Produces: 无。

- [ ] **Step 0: 同步 README 中已过时的 skill 表述**

Task 1 的 `git mv` 和语义变更使 README 以下位置失效，逐处更新（行号为当前值，执行时以 `rg -n "skill" README.md` 实际结果为准）：

- 第 128 行命令表：`安装 / 更新 agent skill（SKILL.md）` → `安装 / 更新内置 agent skills（unityctl 参考手册 + project skill creator）`。
- 第 361 行链接：`src/unityctl/unityctl/skill_assets/SKILL.md` → `src/unityctl/unityctl/skill_assets/unityctl/SKILL.md`。
- 第 365 行：`一份 ... agent skill（SKILL.md）` 改为目录形态、两个 skill 的表述（`unityctl` 参考手册 + `unityctl-project-skill-creator`）。
- 第 373 行：`默认安装到 ... .agents/skills/unityctl/SKILL.md` → `默认安装到 Unity 项目的 .agents/skills/ 下（每个 skill 一个目录）`。
- 第 382-383 行语义说明改为：`skills init`：目录已存在时不覆盖，返回 `already_installed`；`skills update`：与内置内容有差异时整目录覆盖刷新（未安装则直接安装，无差异返回 `up_to_date`）。

- [ ] **Step 1: README 新增章节**

```markdown
## 为你的项目编写自定义 skill

官方 `unityctl` skill 是通用参考手册，由 `unityctl skills update` 整目录覆盖刷新，**不要直接修改它**。项目专属的知识与流程放在你自己的 skill 里：

1. 在 `.agents/skills/<名字>/SKILL.md` 新建自己的 skill（`skills update` 永不触碰官方分发清单之外的目录）。
2. 自定义 skill 里写项目知识（界面约定、专属验证流程），组合调用 unityctl 命令即可；不要复述命令用法，用法以官方 skill 为准，避免两处过时。
3. 现成的数据扩展点：`scenario` JSON（可复跑验证脚本）、`.unity-agent/log-rules.json`（ignore 降噪 / watch 聚焦）、`gameplay` 的 attribute / whitelist（游戏侧暴露命令）。
4. 只想手动触发的流程，在 frontmatter 加 `disable-model-invocation: true`。
5. UI 定位类知识（界面根节点、识别规则、置顶判断）推荐用 `unityctl-project-skill-creator` 引导生成：对 agent 说「用 unityctl-project-skill-creator 为这个项目生成 UI 定位 skill」。
```

- [ ] **Step 2: 官方主 SKILL.md 能力索引表后加一行**

在 Task 2 产出的「能力索引」表格之后追加：

```markdown
项目专属知识（界面约定等）不在本 skill 中：查看项目 `.agents/skills/` 下的其他 skill；如何编写见仓库 README「为你的项目编写自定义 skill」一节。
```

- [ ] **Step 3: 运行测试确认无回归**

```bash
cd src/unityctl && uv run pytest tests/test_skills.py -q
```

Expected: 全部 PASS。

- [ ] **Step 4: Commit**

```bash
git add README.md src/unityctl/unityctl/skill_assets/unityctl/SKILL.md && git commit -m "docs: sync skill docs to directory distribution and add custom skill guide"
```

---

### Task 5: 真实项目人工验收（手动）

**Files:** 无代码改动；产出验收记录（可追加到 spec 或 docs/notes）。

**Interfaces:**
- Consumes: Task 1-4 全部产出。

- [ ] **Step 1: 在测试 Unity 项目安装并检查**

```bash
cd <Unity 项目>（如 .tmp/unity-test-project）
unityctl skills update
ls .agents/skills/unityctl/references/ .agents/skills/unityctl-project-skill-creator/flows/
```

Expected: 聚合输出两个 skill；references 7 个文件、flows 1 个文件齐全；旧单文件安装被正确升级为目录。

- [ ] **Step 2: 跑一次 creator（Editor 可用路径）**

在 agent 会话中显式触发 creator，走完 A-E：检查生成物六节齐全、每条规则带验证过的查询、访谈 ≤ 5 个问题、无 unityctl 用法复述。

- [ ] **Step 3: 跑一次 creator（纯问答降级路径）**

关闭 Editor 后触发：检查走降级模式、全部规则标 `用户口述，未验证`、文件头有未验证声明。

- [ ] **Step 4: 官方 skill 渐进式披露抽查**

让 agent 执行一个 scenario 编写任务和一次错误码查询，确认它先读了对应 reference 文件而不是凭索引臆造参数。

- [ ] **Step 5: 按验收反馈迭代 flow 剧本并提交**

```bash
git add -A && git commit -m "docs: refine creator flow based on real-project acceptance"
```
