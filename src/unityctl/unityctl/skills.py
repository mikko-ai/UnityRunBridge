"""Agent skill 的安装与更新。

skill 内容作为 CLI 包内资源（skill_assets/SKILL.md）随版本发布，
安装时把 frontmatter 中的版本占位符替换为当前 CLI 版本后写入目标目录。
语义与 init 对配置文件的处理保持一致：init 只补缺失、绝不覆盖；update 总是刷新为内置版本。
"""

import re
from dataclasses import dataclass
from pathlib import Path

SKILL_NAME = "unityctl"
SKILL_FILENAME = "SKILL.md"
DEFAULT_SKILLS_DIRNAME = ".agents/skills"

SKILL_SOURCE_PATH = Path(__file__).parent / "skill_assets" / SKILL_FILENAME
VERSION_PLACEHOLDER = "__UNITYCTL_VERSION__"
VERSION_FIELD_PATTERN = re.compile(r"^x-unityctl-version:\s*(\S+)\s*$", re.MULTILINE)


class SkillError(RuntimeError):
    pass


@dataclass(frozen=True)
class SkillResult:
    skill_path: Path
    # installed / already_installed / updated / up_to_date
    action: str
    version: str
    previous_version: str | None


def render_skill_content(version: str) -> str:
    content = SKILL_SOURCE_PATH.read_text(encoding="utf-8")
    if VERSION_PLACEHOLDER not in content:
        raise SkillError(f"内置 skill 模板缺少版本占位符 {VERSION_PLACEHOLDER}")
    return content.replace(VERSION_PLACEHOLDER, version)


def read_skill_version(skill_path: Path) -> str | None:
    if not skill_path.exists():
        return None
    match = VERSION_FIELD_PATTERN.search(skill_path.read_text(encoding="utf-8"))
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


def install_skill(skills_dir: Path, version: str, overwrite: bool) -> SkillResult:
    """把内置 skill 写入 <skills_dir>/unityctl/SKILL.md。

    overwrite=False（init）：已存在时保持原样返回 already_installed。
    overwrite=True（update）：内容有差异则覆盖；未安装时直接安装。
    """
    skill_path = skills_dir / SKILL_NAME / SKILL_FILENAME
    content = render_skill_content(version)

    if not skill_path.exists():
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(content, encoding="utf-8")
        return SkillResult(skill_path, "installed", version, None)

    previous_version = read_skill_version(skill_path)
    if not overwrite:
        return SkillResult(skill_path, "already_installed", version, previous_version)

    if skill_path.read_text(encoding="utf-8") == content:
        return SkillResult(skill_path, "up_to_date", version, previous_version)

    skill_path.write_text(content, encoding="utf-8")
    return SkillResult(skill_path, "updated", version, previous_version)
