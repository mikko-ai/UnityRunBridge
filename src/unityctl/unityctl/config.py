import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONFIG_SCHEMA_VERSION = 1
PROJECT_CONFIG_FILENAME = "config.json"
LOCAL_CONFIG_FILENAME = "config.local.json"
BRIDGE_INFO_FILENAME = "bridge.json"
SCHEMAS_DIRNAME = "schemas"
SESSIONS_DIRNAME = "sessions"

BRIDGE_HOST = "127.0.0.1"
DEFAULT_PREFERRED_PORT = 17890
DEFAULT_PLAY_TIMEOUT_SECONDS = 180
DEFAULT_STOP_TIMEOUT_SECONDS = 60
DEFAULT_START_EDITOR_TIMEOUT_SECONDS = 300

UNITY_AGENT_BRIDGE_PACKAGE_ID = "com.mk.unity-agent-bridge"

SCHEMA_SOURCE_DIR = Path(__file__).parent / "schemas"
SCHEMA_FILENAMES = (
    "config.schema.json",
    "config.local.schema.json",
    "bridge.schema.json",
    "session.schema.json",
    "summary.schema.json",
    "log-rules.schema.json",
    "unity-console-log.schema.json",
)


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Timeouts:
    play_seconds: int = DEFAULT_PLAY_TIMEOUT_SECONDS
    stop_seconds: int = DEFAULT_STOP_TIMEOUT_SECONDS
    start_editor_seconds: int = DEFAULT_START_EDITOR_TIMEOUT_SECONDS


@dataclass(frozen=True)
class InitResult:
    project_path: Path
    config_path: Path
    local_config_path: Path
    preferred_port: int
    package_installed: bool
    created_paths: list[Path]
    kept_paths: list[Path]
    updated_ignore: bool


@dataclass(frozen=True)
class EffectiveConfig:
    project_path: Path
    project_config_path: Path
    local_config_path: Path
    preferred_port: int
    unity_version: str | None
    unity_executable_path: Path | None
    default_scene: str | None
    timeouts: Timeouts


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


def normalize_unity_executable_path(unity_path: str | Path | None) -> Path | None:
    if unity_path is None:
        return None
    path = Path(unity_path).expanduser()
    if path.suffix == ".app":
        return path / "Contents" / "MacOS" / "Unity"
    return path


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path.write_text(content, encoding="utf-8")


def build_project_config_payload(
    unity_version: str | None = None,
    preferred_port: int = DEFAULT_PREFERRED_PORT,
    default_scene: str | None = None,
    play_seconds: int = DEFAULT_PLAY_TIMEOUT_SECONDS,
    stop_seconds: int = DEFAULT_STOP_TIMEOUT_SECONDS,
    start_editor_seconds: int = DEFAULT_START_EDITOR_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    return {
        "$schema": f"{SCHEMAS_DIRNAME}/config.schema.json",
        "version": CONFIG_SCHEMA_VERSION,
        "unityVersion": unity_version,
        "bridge": {"preferredPort": preferred_port},
        "defaultScene": default_scene,
        "timeouts": {
            "playSeconds": play_seconds,
            "stopSeconds": stop_seconds,
            "startEditorSeconds": start_editor_seconds,
        },
    }


def build_local_config_payload(unity_executable_path: str | Path | None = None) -> dict[str, Any]:
    value = None if unity_executable_path is None else str(Path(unity_executable_path).expanduser())
    return {
        "$schema": f"{SCHEMAS_DIRNAME}/config.local.schema.json",
        "unityExecutablePath": value,
    }


def init_project_config(
    project_path: str | Path,
    unity_path: str | Path | None = None,
    unity_version: str | None = None,
    preferred_port: int = DEFAULT_PREFERRED_PORT,
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
        write_json(
            config_path,
            build_project_config_payload(
                unity_version=unity_version,
                preferred_port=preferred_port,
                default_scene=default_scene,
            ),
        )
        created_paths.append(config_path)
    else:
        kept_paths.append(config_path)

    if force or not local_config_path.exists():
        write_json(local_config_path, build_local_config_payload(unity_path))
        created_paths.append(local_config_path)
    else:
        kept_paths.append(local_config_path)

    copy_bundled_schemas(agent_dir / SCHEMAS_DIRNAME)

    gitignore_path = project / ".gitignore"
    updated_local_ignore = append_gitignore_entry(
        gitignore_path, f".unity-agent/{LOCAL_CONFIG_FILENAME}"
    )
    updated_sessions_ignore = append_gitignore_entry(
        gitignore_path, f".unity-agent/{SESSIONS_DIRNAME}/"
    )
    updated_bridge_ignore = append_gitignore_entry(
        gitignore_path, f".unity-agent/{BRIDGE_INFO_FILENAME}"
    )

    effective = resolve_effective_config(project_path=project)

    return InitResult(
        project_path=project,
        config_path=config_path,
        local_config_path=local_config_path,
        preferred_port=effective.preferred_port,
        package_installed=is_bridge_package_installed(project),
        created_paths=created_paths,
        kept_paths=kept_paths,
        updated_ignore=updated_local_ignore or updated_sessions_ignore or updated_bridge_ignore,
    )


def copy_bundled_schemas(schemas_dir: str | Path) -> None:
    """把 CLI 内置的 schema 文件复制到项目里，供编辑器读取 $schema 引用做提示与校验。

    schema 是机器生成物，每次 init 都会覆盖刷新，不需要考虑用户手改的情况。
    """
    target_dir = Path(schemas_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    for filename in SCHEMA_FILENAMES:
        source = SCHEMA_SOURCE_DIR / filename
        if not source.exists():
            continue
        (target_dir / filename).write_text(
            source.read_text(encoding="utf-8"), encoding="utf-8"
        )


def resolve_effective_config(
    start_path: str | Path | None = None,
    project_path: str | Path | None = None,
    unity_path: str | Path | None = None,
) -> EffectiveConfig:
    project = find_unity_project_root(project_path or start_path or Path.cwd())
    config_path = project / ".unity-agent" / PROJECT_CONFIG_FILENAME
    local_config_path = project / ".unity-agent" / LOCAL_CONFIG_FILENAME
    shared = read_json(config_path)
    local = read_json(local_config_path)
    bridge = shared.get("bridge", {})
    preferred_port = int(bridge.get("preferredPort", DEFAULT_PREFERRED_PORT))
    selected_unity_path = unity_path or local.get("unityExecutablePath")
    unity_executable_path = normalize_unity_executable_path(selected_unity_path)
    raw_timeouts = shared.get("timeouts", {})
    timeouts = Timeouts(
        play_seconds=int(raw_timeouts.get("playSeconds", DEFAULT_PLAY_TIMEOUT_SECONDS)),
        stop_seconds=int(raw_timeouts.get("stopSeconds", DEFAULT_STOP_TIMEOUT_SECONDS)),
        start_editor_seconds=int(
            raw_timeouts.get("startEditorSeconds", DEFAULT_START_EDITOR_TIMEOUT_SECONDS)
        ),
    )

    return EffectiveConfig(
        project_path=project,
        project_config_path=config_path,
        local_config_path=local_config_path,
        preferred_port=preferred_port,
        unity_version=shared.get("unityVersion"),
        unity_executable_path=unity_executable_path,
        default_scene=shared.get("defaultScene"),
        timeouts=timeouts,
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
    return UNITY_AGENT_BRIDGE_PACKAGE_ID in dependencies


def find_latest_session_path(project_path: str | Path) -> Path:
    project = find_unity_project_root(project_path)
    sessions = project / ".unity-agent" / SESSIONS_DIRNAME
    candidates = (
        sorted(path for path in sessions.iterdir() if path.is_dir())
        if sessions.exists()
        else []
    )
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

    if effective.preferred_port < 1 or effective.preferred_port > 65535:
        errors.append(
            ValidationIssue("config.bridge.preferredPort", "端口必须在 1 到 65535 之间")
        )

    if effective.timeouts.play_seconds <= 0:
        errors.append(ValidationIssue("config.timeouts.playSeconds", "必须为正整数"))
    if effective.timeouts.stop_seconds <= 0:
        errors.append(ValidationIssue("config.timeouts.stopSeconds", "必须为正整数"))
    if effective.timeouts.start_editor_seconds <= 0:
        errors.append(ValidationIssue("config.timeouts.startEditorSeconds", "必须为正整数"))

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
    if f".unity-agent/{LOCAL_CONFIG_FILENAME}" not in ignored:
        warnings.append(
            ValidationIssue(
                "gitignore",
                f"建议忽略 .unity-agent/{LOCAL_CONFIG_FILENAME}，避免提交本机路径",
            )
        )

    return ValidationResult(len(errors) == 0, project, errors, warnings)
