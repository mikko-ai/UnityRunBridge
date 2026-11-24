"""Read-only Unity .meta and text MonoScript reference audit.

Adapted from awesome-gamedev-agent-skills (Apache-2.0), c6ca6c4,
skills/unity/unity-csharp-scripting/scripts/check_unity_project.py.
See the distribution's awesome-gamedev-agent-skills LICENSE and NOTICE.
"""

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

_GUID = re.compile(r"^guid:[ \t]*([0-9a-fA-F]{32})[ \t]*$")
_SCRIPT = re.compile(
    rb"^  m_Script:[ \t]*\{[ \t]*fileID:[ \t]*11500000,[ \t]*"
    rb"guid:[ \t]*([0-9a-fA-F]{32}),[ \t]*type:[ \t]*3[ \t]*\}[ \t\r\n]*$"
)
_DOC = re.compile(rb"^--- !u!114 &-?\d+(?: stripped)?[ \t\r\n]*$")
_CACHE_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.+-]+)?\Z")
_CACHE_HASH = re.compile(r"[0-9a-f]{7,64}\Z")
_PACKAGE_NAME = re.compile(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+\Z")
_YAML_EXTENSIONS = {".unity", ".prefab", ".asset", ".controller", ".playable"}
_CHUNK = 64 * 1024


@dataclass(frozen=True)
class AssetIssue:
    level: str
    code: str
    file: str
    message: str
    line: int | None = None


@dataclass
class AssetAudit:
    issues: list[AssetIssue] = field(default_factory=list)
    unresolved_packages: list[str] = field(default_factory=list)
    unchecked: Counter[str] = field(default_factory=Counter)
    files_checked: int = 0


def _visible(name: str, streaming: bool) -> bool:
    return (
        (streaming or not name.startswith("."))
        and not name.endswith("~")
        and name.lower() != "cvs"
        and not name.lower().endswith(".tmp")
    )


def _list(path: Path, report: AssetAudit, streaming: bool = False) -> dict[str, Path]:
    entries = {}
    try:
        if path.is_symlink():
            report.unchecked["symlinks"] += 1
            return {}
        for item in sorted(path.iterdir()):
            if not _visible(item.name, streaming):
                continue
            if item.is_symlink():
                report.unchecked["symlinks"] += 1
            elif item.is_file() or item.is_dir():
                entries[item.name] = item
    except OSError:
        report.unchecked["unreadable_paths"] += 1
    return entries


def _guid(path: Path, report: AssetAudit) -> tuple[str | None, int | None]:
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
            for line in range(1, 41):
                raw = handle.readline(4096)
                if not raw:
                    break
                match = _GUID.fullmatch(raw.rstrip("\r\n"))
                if match and match[1] != "0" * 32:
                    return match[1].lower(), line
                if raw.startswith("guid:"):
                    return None, line
                if len(raw) == 4096 and not raw.endswith("\n"):
                    break
    except OSError:
        report.unchecked["unreadable_paths"] += 1
        return None, None
    return None, 0


def _object(path: Path) -> dict | None:
    try:
        if path.is_symlink():
            return None
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def _packages(root: Path, report: AssetAudit) -> tuple[list[Path], list[Path]]:
    packages = root / "Packages"
    embedded = {}
    for folder in _list(packages, report).values():
        if folder.is_dir() and (data := _object(folder / "package.json")):
            name = data.get("name")
            if isinstance(name, str) and _PACKAGE_NAME.fullmatch(name):
                embedded[name] = folder

    manifest = _object(packages / "manifest.json") if not packages.is_symlink() else None
    manifest_deps = (manifest or {}).get("dependencies")
    if not isinstance(manifest_deps, dict):
        report.unresolved_packages.append("Packages/manifest.json")
        manifest_deps = {}
    lock = _object(packages / "packages-lock.json") if not packages.is_symlink() else None
    lock_deps = (lock or {}).get("dependencies")
    if (packages / "packages-lock.json").exists() and not isinstance(lock_deps, dict):
        report.unresolved_packages.append("Packages/packages-lock.json")
    lock_deps = lock_deps if isinstance(lock_deps, dict) else {}
    external: set[Path] = set()

    for name in sorted(manifest_deps.keys() | lock_deps.keys()):
        if name in embedded or name.startswith("com.unity.modules."):
            continue
        if not _PACKAGE_NAME.fullmatch(name):
            report.unresolved_packages.append(name)
            continue
        locked = lock_deps.get(name)
        locked = locked if isinstance(locked, dict) else {}
        declared = manifest_deps.get(name)
        version = declared if isinstance(declared, str) and declared.startswith("file:") else (
            locked.get("version") if declared is None else declared
        )
        if isinstance(version, str) and version.startswith("file:"):
            target = packages / unquote(version.removeprefix("file:"))
            if target.is_dir() and not target.is_symlink() and (_object(target / "package.json") or {}).get("name") == name:
                external.add(target.resolve())
                continue
        if isinstance(version, str) and _CACHE_VERSION.fullmatch(version):
            key = version
        else:
            key = locked.get("hash") if locked.get("source") == "git" and locked.get("version") == version else None
            key = key if isinstance(key, str) and _CACHE_HASH.fullmatch(key) else None
        if key:
            library = root / "Library"
            cache = library / "PackageCache"
            if not library.is_symlink() and not cache.is_symlink() and cache.is_dir():
                # Registry folders use the exact version; a Git revision may use its 12-char prefix.
                for suffix in (key, key[:12]) if locked.get("source") == "git" else (key,):
                    folder = cache / f"{name}@{suffix}"
                    if folder.is_dir() and not folder.is_symlink():
                        external.add(folder)
                        break
                else:
                    report.unresolved_packages.append(name)
                continue
        report.unresolved_packages.append(name)

    return sorted(embedded.values()), sorted(external - set(embedded.values()))


def _script_refs(path: Path, report: AssetAudit):
    try:
        with path.open("rb") as stream:
            head = stream.read(8).removeprefix(b"\xef\xbb\xbf")
            if not head.startswith(b"%YAML"):
                report.unchecked["non_yaml_assets"] += 1
                return
            stream.seek(0)
            line = 0
            start_of_line = True
            mono_doc = False
            while chunk := stream.readline(_CHUNK):
                starts = start_of_line
                start_of_line = chunk.endswith(b"\n")
                if not starts:
                    continue
                line += 1
                if chunk.startswith(b"---"):
                    mono_doc = _DOC.fullmatch(chunk) is not None
                elif mono_doc and chunk.startswith(b"  m_Script:"):
                    if (match := _SCRIPT.fullmatch(chunk)) is not None:
                        guid = match[1].decode("ascii").lower()
                        if not guid.startswith("0" * 16):
                            yield guid, line
                    else:
                        report.unchecked["unsupported_script_refs"] += 1
    except OSError:
        report.unchecked["unreadable_paths"] += 1


def audit_assets(root: Path) -> AssetAudit:
    report = AssetAudit()
    embedded, external = _packages(root, report)
    live: dict[str, list[tuple[str, int | None]]] = defaultdict(list)
    script_guids: set[str] = set()
    yaml_files = []
    streaming_root = root / "Assets" / "StreamingAssets"

    def emit(level: str, code: str, path: Path, message: str, line: int | None = None):
        report.issues.append(AssetIssue(level, code, path.relative_to(root).as_posix(), message, line))

    for top, inspect in [(p, True) for p in [root / "Assets", *embedded]] + [(p, False) for p in external]:
        folders = [(top, False)]
        while folders:
            folder, parent_lacks_meta = folders.pop()
            streaming = folder.is_relative_to(streaming_root)
            entries = _list(folder, report, streaming)
            metas = {name[:-5]: path for name, path in entries.items() if name.endswith(".meta") and path.is_file()}
            assets = {name: path for name, path in entries.items() if not name.endswith(".meta")}
            folded = defaultdict(list)
            for name in assets:
                folded[name.casefold()].append(name)
            matched = set()
            for name, meta in metas.items():
                target = assets.get(name)
                if target is None:
                    alternatives = folded[name.casefold()]
                    if len(alternatives) == 1 and alternatives[0] not in metas:
                        target = assets[alternatives[0]]
                        if inspect:
                            emit("warning", "meta-name-case", meta, f"文件名大小写与 {target.name} 不一致")
                if target is not None:
                    matched.add(target.name)
                if not inspect and (target is None or target.suffix.lower() != ".cs" or not target.is_file()):
                    continue
                guid, line = _guid(meta, report)
                if not guid and inspect and line is not None:
                    emit("error", "malformed-meta", meta, "找不到有效的 Unity GUID", line or None)
                if target is None:
                    if inspect:
                        emit("warning", "orphan-meta", meta, "未找到对应资源；先确认是否有意删除或移动，勿直接替换 GUID")
                elif guid:
                    if inspect:
                        live[guid].append((meta.relative_to(root).as_posix(), line))
                    if not streaming and target.suffix.lower() == ".cs" and target.is_file():
                        script_guids.add(guid)
            for name, path in assets.items():
                is_dir = path.is_dir()
                lacks_meta = name not in matched
                if inspect:
                    if not is_dir:
                        report.files_checked += 1
                    if lacks_meta and not parent_lacks_meta:
                        emit("warning", "missing-meta", path, "缺少 .meta；新资源尚未导入时属正常，移动资源则应保留原 .meta")
                    if not is_dir and not streaming and path.suffix.lower() in _YAML_EXTENSIONS:
                        yaml_files.append(path)
                if is_dir:
                    folders.append((path, parent_lacks_meta or lacks_meta))

    for guid, occurrences in live.items():
        first, *rest = sorted(occurrences)
        for path, line in rest:
            emit("error", "duplicate-guid", root / path, f"GUID {guid} 已被 {first[0]} 使用", line)

    for path in sorted(yaml_files):
        missing: dict[str, int] = {}
        for guid, line in _script_refs(path, report):
            if guid not in script_guids:
                missing.setdefault(guid, line)
        uncertain = report.unresolved_packages or any(
            report.unchecked[key] for key in ("symlinks", "unreadable_paths")
        )
        for guid, line in missing.items():
            qualifier = "（包或资源扫描不完整，未确认）" if uncertain else ""
            emit("warning" if uncertain else "error", "missing-script", path,
                 f"未找到 MonoScript GUID {guid}{qualifier}", line)

    report.issues.sort(key=lambda issue: (issue.level != "error", issue.file, issue.line or 0, issue.code))
    return report
