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
