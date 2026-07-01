import subprocess
from pathlib import Path


def validate_project_path(project_path: str | Path) -> Path:
    project = Path(project_path).expanduser().resolve()
    required = ["Assets", "Packages", "ProjectSettings"]
    if not project.is_dir() or any(not (project / name).is_dir() for name in required):
        raise ValueError(f"{project} does not look like a Unity project")
    return project


def build_editor_command(
    unity_path: str,
    project_path: str | Path,
    log_file: str | Path,
) -> list[str]:
    project = str(Path(project_path).expanduser())
    log_path = str(Path(log_file).expanduser())
    return [
        unity_path,
        "-projectPath",
        project,
        "-logFile",
        log_path,
    ]


def start_editor(
    unity_path: str,
    project_path: str | Path,
    log_file: str | Path,
) -> subprocess.Popen:
    project = validate_project_path(project_path)
    command = build_editor_command(unity_path, project, log_file)
    return subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
