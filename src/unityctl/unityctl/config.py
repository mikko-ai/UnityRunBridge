import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_BRIDGE_HOST = "127.0.0.1"
DEFAULT_BRIDGE_PORT = 17890
DEFAULT_SESSION_DIRECTORY = ".unity-agent/sessions"


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class InitResult:
    project_path: Path
    config_path: Path
    local_config_path: Path
    bridge_url: str
    package_installed: bool


@dataclass(frozen=True)
class EffectiveConfig:
    project_path: Path
    project_config_path: Path
    local_config_path: Path
    bridge_url: str
    bridge_host: str
    bridge_port: int
    unity_version: str | None
    unity_app_path: Path | None
    unity_executable_path: Path | None
    default_scene: str | None
    session_directory: Path


def find_unity_project_root(start: str | Path) -> Path:
    current = Path(start).expanduser().resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if is_unity_project_root(candidate):
            return candidate
    raise ConfigError(f"Could not find Unity project root from {current}")


def is_unity_project_root(path: Path) -> bool:
    return all((path / name).is_dir() for name in ["Assets", "Packages", "ProjectSettings"])


def build_bridge_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def normalize_unity_executable_path(unity_path: str | Path | None) -> Path | None:
    if unity_path is None:
        return None
    path = Path(unity_path).expanduser()
    if path.suffix == ".app":
        return path / "Contents" / "MacOS" / "Unity"
    return path


def normalize_unity_app_path(unity_path: str | Path | None) -> Path | None:
    if unity_path is None:
        return None
    path = Path(unity_path).expanduser()
    if path.name == "Unity" and path.parent.name == "MacOS":
        return path.parents[2]
    return path


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path.write_text(content, encoding="utf-8")


def init_project_config(
    project_path: str | Path,
    unity_path: str | Path | None,
    unity_version: str | None,
    host: str = DEFAULT_BRIDGE_HOST,
    port: int = DEFAULT_BRIDGE_PORT,
    default_scene: str | None = None,
) -> InitResult:
    project = find_unity_project_root(project_path)
    agent_dir = project / ".unity-agent"
    config_path = agent_dir / "config.json"
    local_config_path = agent_dir / "config.local.json"
    existing = read_json(config_path)
    local_existing = read_json(local_config_path)

    payload = {
        "version": 1,
        "unityVersion": unity_version or existing.get("unityVersion"),
        "bridge": {
            "host": host,
            "port": port,
        },
        "defaultScene": default_scene,
        "sessionDirectory": existing.get("sessionDirectory", DEFAULT_SESSION_DIRECTORY),
    }
    write_json(config_path, payload)

    unity_app_path = normalize_unity_app_path(unity_path)
    local_payload = dict(local_existing)
    if unity_app_path is not None:
        local_payload["unityAppPath"] = str(unity_app_path)
    write_json(local_config_path, local_payload)

    gitignore_path = project / ".gitignore"
    append_gitignore_entry(gitignore_path, ".unity-agent/config.local.json")
    append_gitignore_entry(gitignore_path, ".unity-agent/sessions/")

    return InitResult(
        project_path=project,
        config_path=config_path,
        local_config_path=local_config_path,
        bridge_url=build_bridge_url(host, port),
        package_installed=is_bridge_package_installed(project),
    )


def resolve_effective_config(
    start_path: str | Path | None = None,
    project_path: str | Path | None = None,
    unity_path: str | Path | None = None,
    base_url: str | None = None,
) -> EffectiveConfig:
    project = find_unity_project_root(project_path or start_path or Path.cwd())
    config_path = project / ".unity-agent" / "config.json"
    local_config_path = project / ".unity-agent" / "config.local.json"
    shared = read_json(config_path)
    local = read_json(local_config_path)
    bridge = shared.get("bridge", {})
    host = str(bridge.get("host", DEFAULT_BRIDGE_HOST))
    port = int(bridge.get("port", DEFAULT_BRIDGE_PORT))
    selected_unity_path = (
        unity_path or local.get("unityExecutablePath") or local.get("unityAppPath")
    )
    unity_app_path = normalize_unity_app_path(selected_unity_path)
    unity_executable_path = normalize_unity_executable_path(selected_unity_path)
    session_directory = project / str(
        shared.get("sessionDirectory", DEFAULT_SESSION_DIRECTORY)
    )

    return EffectiveConfig(
        project_path=project,
        project_config_path=config_path,
        local_config_path=local_config_path,
        bridge_url=base_url or build_bridge_url(host, port),
        bridge_host=host,
        bridge_port=port,
        unity_version=shared.get("unityVersion"),
        unity_app_path=unity_app_path,
        unity_executable_path=unity_executable_path,
        default_scene=shared.get("defaultScene"),
        session_directory=session_directory,
    )


def append_gitignore_entry(gitignore_path: str | Path, entry: str) -> None:
    path = Path(gitignore_path)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    if entry not in lines:
        lines.append(entry)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def is_bridge_package_installed(project_path: str | Path) -> bool:
    manifest = Path(project_path) / "Packages" / "manifest.json"
    if not manifest.exists():
        return False
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    dependencies = payload.get("dependencies", {})
    return "com.elex.unity-agent-bridge" in dependencies


def find_latest_session_path(project_path: str | Path) -> Path:
    project = find_unity_project_root(project_path)
    sessions = project / DEFAULT_SESSION_DIRECTORY
    candidates = sorted(path for path in sessions.iterdir() if path.is_dir()) if sessions.exists() else []
    if not candidates:
        raise ConfigError(f"No sessions found under {sessions}")
    return candidates[-1]
