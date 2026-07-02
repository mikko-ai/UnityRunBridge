import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONFIG_SCHEMA_VERSION = 1
PROJECT_CONFIG_FILENAME = "config.jsonc"
LOCAL_CONFIG_FILENAME = "config.local.jsonc"
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
    created_paths: list[Path]
    kept_paths: list[Path]
    updated_ignore: bool


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


@dataclass(frozen=True)
class ValidationIssue:
    field: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    project_path: Path
    errors: list[ValidationIssue]
    warnings: list[ValidationIssue]


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


def strip_jsonc_comments(text: str) -> str:
    result: list[str] = []
    index = 0
    in_string = False
    escape = False
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if in_string:
            result.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            result.append(char)
            index += 1
            continue
        if char == "/" and next_char == "/":
            index += 2
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue
        if char == "/" and next_char == "*":
            index += 2
            while index + 1 < len(text) and not (text[index] == "*" and text[index + 1] == "/"):
                index += 1
            index += 2
            continue
        result.append(char)
        index += 1
    return "".join(result)


def strip_jsonc_trailing_commas(text: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", text)


def read_jsonc(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    stripped = strip_jsonc_trailing_commas(strip_jsonc_comments(path.read_text(encoding="utf-8")))
    return json.loads(stripped)


def read_json(path: Path) -> dict[str, Any]:
    return read_jsonc(path)


def write_jsonc(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    write_jsonc(path, payload)


def build_project_config_template(
    unity_version: str | None = None,
    host: str = DEFAULT_BRIDGE_HOST,
    port: int = DEFAULT_BRIDGE_PORT,
    default_scene: str | None = None,
) -> str:
    return f"""// 项目级配置：建议提交到 Git。
{{
  // 配置结构版本，用于解析和未来迁移；不是 unityctl 版本，也不是 Unity 版本。
  "version": {CONFIG_SCHEMA_VERSION},

  // 可选：项目期望使用的 Unity 版本，仅用于提示和校验。
  "unityVersion": {json.dumps(unity_version, ensure_ascii=False)},

  "bridge": {{
    // Bridge 监听地址，通常保持 127.0.0.1。
    "host": {json.dumps(host, ensure_ascii=False)},

    // Bridge 监听端口；多个 Unity 项目同时打开时建议使用不同端口。
    "port": {port}
  }},

  // 可选：默认打开或运行的场景路径。
  "defaultScene": {json.dumps(default_scene, ensure_ascii=False)},

  // Session、日志和 summary 的默认保存目录。
  "sessionDirectory": "{DEFAULT_SESSION_DIRECTORY}"
}}
"""


def build_local_config_template(unity_executable_path: str | Path | None = None) -> str:
    value = None if unity_executable_path is None else str(Path(unity_executable_path).expanduser())
    return f"""// 本机配置：不要提交到 Git。
{{
  // 必填：Unity 可执行文件路径。
  // macOS 示例：
  // "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity"
  // Windows 示例：
  // "C:\\\\Program Files\\\\Unity\\\\Hub\\\\Editor\\\\2022.3.62f2\\\\Editor\\\\Unity.exe"
  "unityExecutablePath": {json.dumps(value, ensure_ascii=False)}
}}
"""


def init_project_config(
    project_path: str | Path,
    unity_path: str | Path | None = None,
    unity_version: str | None = None,
    host: str = DEFAULT_BRIDGE_HOST,
    port: int = DEFAULT_BRIDGE_PORT,
    default_scene: str | None = None,
    force: bool = False,
) -> InitResult:
    project = find_unity_project_root(project_path)
    agent_dir = project / ".unity-agent"
    config_path = agent_dir / PROJECT_CONFIG_FILENAME
    local_config_path = agent_dir / LOCAL_CONFIG_FILENAME
    created_paths: list[Path] = []
    kept_paths: list[Path] = []

    agent_dir.mkdir(parents=True, exist_ok=True)
    if force or not config_path.exists():
        config_path.write_text(
            build_project_config_template(
                unity_version=unity_version,
                host=host,
                port=port,
                default_scene=default_scene,
            ),
            encoding="utf-8",
        )
        created_paths.append(config_path)
    else:
        kept_paths.append(config_path)

    if force or not local_config_path.exists():
        local_config_path.write_text(
            build_local_config_template(unity_path),
            encoding="utf-8",
        )
        created_paths.append(local_config_path)
    else:
        kept_paths.append(local_config_path)

    gitignore_path = project / ".gitignore"
    updated_local_ignore = append_gitignore_entry(gitignore_path, ".unity-agent/config.local.jsonc")
    updated_sessions_ignore = append_gitignore_entry(gitignore_path, ".unity-agent/sessions/")
    effective = resolve_effective_config(project_path=project)

    return InitResult(
        project_path=project,
        config_path=config_path,
        local_config_path=local_config_path,
        bridge_url=effective.bridge_url,
        package_installed=is_bridge_package_installed(project),
        created_paths=created_paths,
        kept_paths=kept_paths,
        updated_ignore=updated_local_ignore or updated_sessions_ignore,
    )


def resolve_effective_config(
    start_path: str | Path | None = None,
    project_path: str | Path | None = None,
    unity_path: str | Path | None = None,
    base_url: str | None = None,
) -> EffectiveConfig:
    project = find_unity_project_root(project_path or start_path or Path.cwd())
    config_path = project / ".unity-agent" / PROJECT_CONFIG_FILENAME
    local_config_path = project / ".unity-agent" / LOCAL_CONFIG_FILENAME
    shared = read_jsonc(config_path)
    local = read_jsonc(local_config_path)
    bridge = shared.get("bridge", {})
    host = str(bridge.get("host", DEFAULT_BRIDGE_HOST))
    port = int(bridge.get("port", DEFAULT_BRIDGE_PORT))
    selected_unity_path = unity_path or local.get("unityExecutablePath")
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
        unity_app_path=None,
        unity_executable_path=unity_executable_path,
        default_scene=shared.get("defaultScene"),
        session_directory=session_directory,
    )


def append_gitignore_entry(gitignore_path: str | Path, entry: str) -> bool:
    path = Path(gitignore_path)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    if entry not in lines:
        lines.append(entry)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True
    return False


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


def validate_project_config(project_path: str | Path) -> ValidationResult:
    project = find_unity_project_root(project_path)
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    try:
        effective = resolve_effective_config(project_path=project)
    except (json.JSONDecodeError, ValueError) as exc:
        errors.append(ValidationIssue("config", f"配置文件无法解析：{exc}"))
        return ValidationResult(False, project, errors, warnings)

    if effective.bridge_port < 1 or effective.bridge_port > 65535:
        errors.append(ValidationIssue("config.bridge.port", "端口必须在 1 到 65535 之间"))

    if effective.unity_version is None:
        warnings.append(
            ValidationIssue("config.unityVersion", "未填写 Unity 版本，无法做版本提示")
        )

    executable = effective.unity_executable_path
    if executable is None:
        errors.append(
            ValidationIssue(
                "config.local.unityExecutablePath",
                "必填：用于 unityctl start 启动 Unity",
            )
        )
    elif not executable.exists():
        errors.append(
            ValidationIssue(
                "config.local.unityExecutablePath",
                f"路径不存在：{executable}",
            )
        )
    elif not executable.is_file():
        errors.append(
            ValidationIssue(
                "config.local.unityExecutablePath",
                f"不是文件：{executable}",
            )
        )

    gitignore = project / ".gitignore"
    ignored = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    if ".unity-agent/config.local.jsonc" not in ignored:
        warnings.append(
            ValidationIssue(
                "gitignore",
                "建议忽略 .unity-agent/config.local.jsonc，避免提交本机路径",
            )
        )

    return ValidationResult(len(errors) == 0, project, errors, warnings)
