import re
from pathlib import Path
from typing import Any

from unityctl import __version__
from unityctl.config import (
    CONFIG_SCHEMA_VERSION,
    PROJECT_CONFIG_FILENAME,
    UNITY_AGENT_BRIDGE_GIT_URL,
    UNITY_AGENT_BRIDGE_PACKAGE_ID,
    read_json,
)
from unityctl.skills import SKILL_FILENAME, read_skill_version, resolve_skills_dir

_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.+-]+)?")
_UGUI_CAPABILITIES = {"interaction", "recording"}


def project_version_report(project: Path | None, skills_target: str | None) -> tuple[dict, list[dict]]:
    versions: dict[str, Any] = {
        "skillPath": None,
        "skillVersion": None,
        "configSchemaVersion": None,
        "expectedConfigSchemaVersion": CONFIG_SCHEMA_VERSION,
    }
    warnings = []
    if project is None:
        return versions, warnings

    def warn(code: str, message: str) -> None:
        warnings.append({"code": code, "message": message})

    skill_dir = resolve_skills_dir(project, skills_target) / "unityctl"
    versions["skillPath"] = str(skill_dir / SKILL_FILENAME)
    try:
        skill_version = read_skill_version(skill_dir)
    except (OSError, UnicodeError):
        warn("skill_version_unknown", "无法读取所选位置的 unityctl Skill 版本。")
    else:
        if not skill_version or not _VERSION.fullmatch(skill_version):
            warn("skill_version_unknown", "所选位置没有可识别的 unityctl Skill 版本；请确认 Agent 加载的是哪份。")
        else:
            versions["skillVersion"] = skill_version
            if skill_version != __version__:
                warn("skill_version_mismatch", "Skill 与 CLI 版本不同；请先对照 CLI 帮助，确认后再更新 Skill。")

    try:
        config = read_json(project / ".unity-agent" / PROJECT_CONFIG_FILENAME)
    except (OSError, ValueError):
        config = None
    schema_version = config.get("version") if isinstance(config, dict) else None
    if type(schema_version) is not int or schema_version < 1:
        warn("config_schema_version_unknown", "工程配置格式版本未知；不要猜测版本或直接补写字段。")
    else:
        versions["configSchemaVersion"] = schema_version
        if schema_version != CONFIG_SCHEMA_VERSION:
            warn("config_schema_version_mismatch", "工程配置格式与当前 CLI 预期不同；请先核对兼容性或迁移说明。")
    return versions, warnings


def read_bridge_reference(project: Path) -> str | None:
    manifest = project / "Packages" / "manifest.json"
    if not manifest.is_file():
        return None
    payload = read_json(manifest)
    dependencies = payload.get("dependencies", {}) if isinstance(payload, dict) else None
    if not isinstance(dependencies, dict):
        raise ValueError("Packages/manifest.json 的 dependencies 必须是对象")
    if UNITY_AGENT_BRIDGE_PACKAGE_ID not in dependencies:
        return None
    reference = dependencies[UNITY_AGENT_BRIDGE_PACKAGE_ID]
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError("Bridge UPM 依赖的引用必须是非空字符串")
    return reference


def version_report(reference: str | None, loaded: Any) -> tuple[dict, list[dict]]:
    declared = reference
    if declared and declared.startswith(f"{UNITY_AGENT_BRIDGE_GIT_URL}#upm/v"):
        declared = declared.removeprefix(f"{UNITY_AGENT_BRIDGE_GIT_URL}#upm/v")
    declared = declared if declared and _VERSION.fullmatch(declared) else None
    loaded = loaded if isinstance(loaded, str) and loaded.strip() else None
    warnings = []
    if loaded and loaded != __version__:
        warnings.append({
            "code": "cli_bridge_version_mismatch",
            "message": "CLI 与运行中的 Bridge 版本不同；不代表不兼容，请核验当前任务所需能力。",
        })
    if not loaded and declared and declared != __version__:
        warnings.append({
            "code": "cli_declared_version_mismatch",
            "message": "CLI 与工程声明的 UPM 版本不同；启动或连接现有 Editor 后再核对实际加载版本。",
        })
    if declared and loaded and declared != loaded:
        warnings.append({
            "code": "declared_loaded_version_mismatch",
            "message": "工程声明版本与实际加载版本不同；先检查 Unity Package Manager 是否已解析并重新加载。",
        })
    return {
        "cliVersion": __version__,
        "declaredUpmReference": reference,
        "declaredUpmVersion": declared,
        "loadedBridgeVersion": loaded,
    }, warnings


def check_requirements(
    response: dict, capabilities: list[str], routes: list[list[str]],
) -> list[dict]:
    advertised = response.get("capabilities")
    registered = response.get("routes")
    legacy = response.get("legacy") is True
    checks = []
    for capability in capabilities:
        state = "unverified"
        if isinstance(advertised, list):
            if capability in advertised:
                state = "available"
            elif not legacy:
                state = "missing"
        checks.append({"kind": "capability", "capability": capability, "state": state})
    for method, path in routes:
        method, path = method.upper(), path.lstrip("/")
        state = "unverified"
        if isinstance(registered, list):
            found = any(
                isinstance(route, dict) and str(route.get("method", "")).upper() == method
                and route.get("path") == path for route in registered
            )
            state = "available" if found else "missing"
        checks.append({"kind": "route", "method": method, "path": path, "state": state})
    return checks


def repair_guidance(evidence: list[dict], recheck: list[str]) -> list[dict]:
    guidance = []
    missing = [check for check in evidence if check["state"] == "missing"]
    if missing:
        if any(
            check.get("capability") in _UGUI_CAPABILITIES
            or check.get("path", "").startswith(("interaction/", "recording/"))
            for check in missing
        ):
            guidance.append({
                "action": "inspect_optional_dependencies",
                "requiresApproval": False,
                "message": "先确认工程是否使用 UGUI、对应依赖是否已安装，以及 Bridge 是否编译成功；升级 Bridge 不会补齐可选依赖。",
            })
        guidance.extend([
            {
                "action": "select_bridge_release",
                "requiresApproval": False,
                "message": "若确认由旧 Bridge 导致，先查正式 Release 或已验收的本地包，选一个支持所需能力且支持 Unity 2022.3 的版本。不要按 CLI 版本猜测已发布的标签。",
                "releaseUrl": "https://github.com/mikko-ai/UnityRunBridge/releases",
            },
            {
                "action": "update_bridge_dependency",
                "requiresApproval": True,
                "file": "Packages/manifest.json",
                "packageId": UNITY_AGENT_BRIDGE_PACKAGE_ID,
                "message": "向用户展示现有引用、目标引用和最小 diff。确认后先退出 Play Mode，只更新此依赖；不要用 init --force，也不要手改 packages-lock.json。等待 Unity 解析并重新编译。",
            },
        ])
    if any(check["state"] == "unverified" for check in evidence):
        guidance.append({
            "action": "inspect_bridge_metadata",
            "requiresApproval": False,
            "message": "能力未核验：先确认 Bridge 可达并完成编译。旧 Bridge 可能不提供完整元数据；缺少元数据不等于缺少能力，不要直接修改工程。",
        })
    if guidance:
        guidance.append({
            "action": "verify_repair",
            "requiresApproval": False,
            "argv": recheck,
            "message": "重新核对运行态版本和任务所需能力；能力确认后再按原任务授权范围重跑最小用例。",
        })
    return guidance
