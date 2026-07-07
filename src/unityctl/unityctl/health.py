"""项目健康检查：`unityctl doctor` 回答「环境能不能跑」（Bridge/UPM 包/进程占用），
`unityctl health` 回答「项目干不干净」（编译、缺失脚本、构建场景列表、包一致性）。
四个检查项各自独立、互不依赖，未来新增检查项只需要往 `CHECK_FUNCTIONS` 里注册一个函数。

需要 Bridge 的检查项（compilation / missing_scripts）在 Bridge 不可达时标记为
`skipped` 并说明原因，不计入整体 pass/warn/fail 判定——跑 health 不应该逼着 agent
先启动 Unity Editor，纯静态的检查项（build_scenes / packages）任何时候都能跑。
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from unityctl.client import BridgeClient, BridgeClientError
from unityctl.config import EffectiveConfig
from unityctl.convergence import ConvergenceEditorExited, ConvergenceTimeout, poll_until
from unityctl.discovery import BridgeInfo, DiscoveryError, discover
from unityctl.jobs import JobEditorExited, JobFailed, JobTimeout, wait_for_job

ALL_CHECKS: tuple[str, ...] = ("compilation", "missing_scripts", "build_scenes", "packages")

_STATUS_RANK = {"pass": 0, "skipped": 0, "warn": 1, "fail": 2}

_EDITOR_BUILD_SETTINGS_SCENE_PATTERN = re.compile(
    r"-\s*enabled:\s*(\d+)\s*\n\s*path:\s*(\S+)", re.MULTILINE
)
_PROJECT_VERSION_PATTERN = re.compile(r"m_EditorVersion:\s*(\S+)")


class HealthError(RuntimeError):
    def __init__(self, message: str, code: str = "invalid_request"):
        super().__init__(message)
        self.code = code


@dataclass
class HealthContext:
    project_path: Path
    effective: EffectiveConfig
    timeout_seconds: float
    _info: BridgeInfo | None = field(default=None, repr=False)
    _bridge_error: str | None = field(default=None, repr=False)
    _resolved: bool = field(default=False, repr=False)

    def bridge_client(self) -> tuple[BridgeClient | None, str | None]:
        """惰性连接一次，多个检查项共用同一个结论（避免每个检查项各自 discover 一遍）。"""
        if not self._resolved:
            self._resolved = True
            try:
                info = discover(self.project_path)
                BridgeClient(info.base_url, info.token).get_status()
                self._info = info
            except (DiscoveryError, BridgeClientError) as exc:
                self._bridge_error = str(exc)
                self._info = None

        if self._info is None:
            return None, self._bridge_error

        return BridgeClient(self._info.base_url, self._info.token), None


def _result(name: str, status: str, details: list[str] | None = None) -> dict[str, Any]:
    return {"name": name, "status": status, "details": details or []}


def check_compilation(ctx: HealthContext) -> dict[str, Any]:
    client, bridge_error = ctx.bridge_client()
    if client is None:
        return _result("compilation", "skipped", [f"Bridge 不可达，跳过：{bridge_error}"])

    try:
        refresh_response = client.refresh()
    except BridgeClientError as exc:
        return _result("compilation", "skipped", [f"触发 refresh 失败：{exc}"])

    if not refresh_response.get("ok", False):
        return _result(
            "compilation", "skipped", [refresh_response.get("message", "触发 refresh 失败")]
        )

    try:
        poll_result = poll_until(
            ctx.project_path,
            predicate=lambda current: current.get("editorState") not in {"compiling", "updating"},
            timeout_seconds=ctx.timeout_seconds,
        )
    except ConvergenceTimeout:
        return _result("compilation", "fail", ["等待编译完成超时"])
    except ConvergenceEditorExited as exc:
        return _result("compilation", "skipped", [f"Editor 在等待编译期间退出：{exc}"])

    status = poll_result.status
    if not status.get("compilationSucceeded", True):
        errors = status.get("compilationErrors", [])
        details = [
            f"{entry.get('file')}:{entry.get('line')}: {entry.get('message')}" for entry in errors
        ] or ["编译失败（未返回具体错误详情）"]
        return _result("compilation", "fail", details)

    return _result("compilation", "pass")


def check_missing_scripts(ctx: HealthContext) -> dict[str, Any]:
    client, bridge_error = ctx.bridge_client()
    if client is None:
        return _result("missing_scripts", "skipped", [f"Bridge 不可达，跳过：{bridge_error}"])

    details: list[str] = []

    try:
        loaded_response = client.hierarchy_find(missingScript=True, pageSize=500)
    except BridgeClientError as exc:
        return _result("missing_scripts", "skipped", [f"查询已加载场景失败：{exc}"])

    for node in loaded_response.get("nodes", []):
        details.append(f"[loaded-scene] {node.get('path') or node.get('name') or '?'}")

    try:
        start_response = client.health_scan_prefabs()
    except BridgeClientError as exc:
        return _result(
            "missing_scripts",
            "fail" if details else "warn",
            details + [f"Prefab 资产扫描启动失败：{exc}"],
        )

    if not start_response.get("ok", False):
        return _result(
            "missing_scripts",
            "fail" if details else "warn",
            details + [start_response.get("message", "启动 prefab 扫描 job 失败")],
        )

    job_id = start_response.get("jobId")
    try:
        job = wait_for_job(ctx.project_path, job_id, timeout_seconds=ctx.timeout_seconds)
    except (JobFailed, JobTimeout, JobEditorExited) as exc:
        return _result(
            "missing_scripts",
            "fail" if details else "warn",
            details + [f"Prefab 资产扫描未完成：{exc}"],
        )

    result = job.get("result") or {}
    for asset_path in result.get("assetsWithMissingScripts", []):
        details.append(f"[prefab] {asset_path}")

    return _result("missing_scripts", "fail" if details else "pass", details)


def parse_editor_build_settings_scenes(text: str) -> list[tuple[bool, str]]:
    """解析 ProjectSettings/EditorBuildSettings.asset（Unity YAML）里的 m_Scenes 列表。

    只依赖固定的两行结构（`- enabled: N` 紧跟 `path: ...`），不引入 YAML 依赖——
    Unity 写出这个文件的格式是稳定的序列化布局，没有必要为此拉一个通用 YAML parser。
    """
    return [(enabled == "1", path) for enabled, path in _EDITOR_BUILD_SETTINGS_SCENE_PATTERN.findall(text)]


def parse_project_version(text: str) -> str | None:
    match = _PROJECT_VERSION_PATTERN.search(text)
    return match.group(1) if match else None


def check_build_scenes(ctx: HealthContext) -> dict[str, Any]:
    settings_path = ctx.project_path / "ProjectSettings" / "EditorBuildSettings.asset"
    if not settings_path.exists():
        return _result("build_scenes", "warn", ["ProjectSettings/EditorBuildSettings.asset 不存在"])

    scenes = parse_editor_build_settings_scenes(
        settings_path.read_text(encoding="utf-8", errors="replace")
    )

    details: list[str] = []
    status = "pass"

    for enabled, scene_path in scenes:
        if not (ctx.project_path / scene_path).exists():
            status = "fail"
            details.append(
                f"[missing] {scene_path}（enabled={enabled}）在 EditorBuildSettings.scenes 中但文件不存在"
            )

    listed_paths = {scene_path for _enabled, scene_path in scenes}
    assets_dir = ctx.project_path / "Assets"
    if assets_dir.is_dir():
        all_scene_files = sorted(
            path.relative_to(ctx.project_path).as_posix() for path in assets_dir.rglob("*.unity")
        )
        not_listed = [path for path in all_scene_files if path not in listed_paths]
        if not_listed:
            if status == "pass":
                status = "warn"
            details.extend(f"[not_listed] {path} 不在 EditorBuildSettings.scenes 中" for path in not_listed)

    return _result("build_scenes", status, details)


def check_packages(ctx: HealthContext) -> dict[str, Any]:
    manifest_path = ctx.project_path / "Packages" / "manifest.json"
    if not manifest_path.exists():
        return _result("packages", "fail", ["Packages/manifest.json 不存在"])

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return _result("packages", "fail", [f"Packages/manifest.json 解析失败：{exc}"])

    manifest_deps = set((manifest.get("dependencies") or {}).keys())
    details: list[str] = []
    status = "pass"

    lock_path = ctx.project_path / "Packages" / "packages-lock.json"
    if not lock_path.exists():
        status = "warn"
        details.append("Packages/packages-lock.json 不存在（项目从未被 Unity 打开过解析依赖时是正常的）")
    else:
        try:
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            lock_deps = set((lock.get("dependencies") or {}).keys())
            missing_in_lock = sorted(manifest_deps - lock_deps)
            if missing_in_lock:
                status = "warn"
                details.append(
                    "packages-lock.json 缺少 manifest.json 中声明的依赖："
                    + ", ".join(missing_in_lock)
                    + "（打开一次 Unity 让它重新解析依赖即可刷新）"
                )
        except json.JSONDecodeError as exc:
            status = "warn"
            details.append(f"Packages/packages-lock.json 解析失败：{exc}")

    version_path = ctx.project_path / "ProjectSettings" / "ProjectVersion.txt"
    if version_path.exists() and ctx.effective.unity_version:
        project_version = parse_project_version(
            version_path.read_text(encoding="utf-8", errors="replace")
        )
        if project_version and project_version != ctx.effective.unity_version:
            if status == "pass":
                status = "warn"
            details.append(
                f"ProjectSettings/ProjectVersion.txt 记录的 Unity 版本（{project_version}）"
                f"与 config.json 的 unityVersion（{ctx.effective.unity_version}）不一致"
            )

    return _result("packages", status, details)


CHECK_FUNCTIONS: dict[str, Callable[[HealthContext], dict[str, Any]]] = {
    "compilation": check_compilation,
    "missing_scripts": check_missing_scripts,
    "build_scenes": check_build_scenes,
    "packages": check_packages,
}


def run_health(
    project_path: Path,
    effective: EffectiveConfig,
    checks: list[str] | None = None,
    timeout_seconds: float = 180,
) -> dict[str, Any]:
    selected = checks if checks else list(ALL_CHECKS)
    unknown = [name for name in selected if name not in CHECK_FUNCTIONS]
    if unknown:
        raise HealthError(
            f"未知的检查项：{', '.join(unknown)}；可选：{', '.join(ALL_CHECKS)}"
        )

    ctx = HealthContext(project_path=project_path, effective=effective, timeout_seconds=timeout_seconds)
    results = [CHECK_FUNCTIONS[name](ctx) for name in selected]

    overall = "pass"
    for result in results:
        if _STATUS_RANK[result["status"]] > _STATUS_RANK[overall]:
            overall = result["status"]

    return {"ok": overall != "fail", "status": overall, "checks": results}
