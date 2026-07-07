"""独立进程构建编排：不经过 Bridge，直接 spawn 一个新的 batchmode Unity 进程执行
`Mk.UnityAgentBridge.Editor.Build.BuildRunner.Build`。目标平台用 Unity 原生
`-buildTarget <target>` 传递（保证脚本编译符号与目标平台一致），CLI 只负责拼命令行、
起子进程、读取 BuildRunner 写出的 `build-report.json`；报告缺失时（多半是编译错误导致
`-executeMethod` 从未跑起来）从 `build.log` 里兜底提取 CS 编译错误行。

刻意不走 Bridge/HTTP：构建需要独占整个项目（Unity 一次只能有一个进程持有同一个
Library/Temp），与「正在跑的、供交互调试用的 Editor 实例」互斥，所以设计上就是两条
完全独立的路径，而不是给 Bridge 加一个「构建」路由。
"""

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from unityctl.config import BUILDS_DIRNAME, normalize_unity_executable_path
from unityctl.discovery import is_unity_project_locked

DEFAULT_BUILD_ENTRY_POINT = "Mk.UnityAgentBridge.Editor.Build.BuildRunner.Build"

_DEFAULT_OUTPUT_NAMES: dict[str, str] = {
    "StandaloneOSX": "Build.app",
    "StandaloneWindows": "Build.exe",
    "StandaloneWindows64": "Build.exe",
    "StandaloneLinux64": "Build",
    "Android": "Build.apk",
    "iOS": "XcodeProject",
    "WebGL": "WebGLBuild",
}

# BuildRunner 兜底解析 build.log 用：匹配形如
# `Assets/Foo.cs(12,34): error CS0103: The name 'Bar' does not exist ...` 的编译错误行。
_CS_ERROR_PATTERN = re.compile(r"^.*\.cs\(\d+,\d+\):\s*error\s+CS\d+:.*$", re.MULTILINE)


class BuildError(RuntimeError):
    def __init__(self, message: str, code: str = "internal_error"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class BuildResult:
    ok: bool
    build_id: str
    result: str
    report: dict[str, Any]
    report_path: Path
    log_path: Path
    output_path: Path
    exit_code: int
    command: list[str] = field(default_factory=list)


def default_output_path(build_dir: Path, target: str | None) -> Path:
    name = _DEFAULT_OUTPUT_NAMES.get(target or "", "Build")
    return build_dir / "Build" / name


def make_build_id(target: str | None, now_fn: Callable[[], float] = time.time) -> str:
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now_fn()))
    return f"{timestamp}-{target or 'default'}"


def build_command(
    unity_executable: str | Path,
    project_path: str | Path,
    target: str | None,
    output_path: str | Path,
    report_path: str | Path,
    log_path: str | Path,
) -> list[str]:
    command = [
        str(unity_executable),
        "-batchmode",
        "-quit",
        "-projectPath",
        str(project_path),
    ]
    if target:
        command += ["-buildTarget", target]
    command += [
        "-executeMethod",
        DEFAULT_BUILD_ENTRY_POINT,
        "-logFile",
        str(log_path),
        "-agentBuildOutput",
        str(output_path),
        "-agentReportPath",
        str(report_path),
    ]
    return command


def parse_log_fallback_errors(log_text: str) -> list[str]:
    return [line.strip() for line in _CS_ERROR_PATTERN.findall(log_text)]


def run_build(
    project_path: str | Path,
    unity_executable: str | Path | None,
    target: str | None = None,
    output_path: str | Path | None = None,
    timeout_seconds: float = 3600,
    popen: Callable[..., "subprocess.Popen[bytes]"] = subprocess.Popen,
    now_fn: Callable[[], float] = time.time,
) -> BuildResult:
    project = Path(project_path)

    if is_unity_project_locked(project):
        raise BuildError(
            "项目被另一个 Unity 实例占用（Temp/UnityLockfile 已加锁）。"
            "构建需要独占访问项目，请先关闭已打开的 Editor 窗口（或换一台构建机），"
            "不会自动尝试关闭正在运行的 Editor。",
            code="editor_running",
        )

    executable = normalize_unity_executable_path(unity_executable)
    if executable is None:
        raise BuildError("Unity executable path is required", code="invalid_request")

    build_id = make_build_id(target, now_fn=now_fn)
    build_dir = project / ".unity-agent" / BUILDS_DIRNAME / build_id
    build_dir.mkdir(parents=True, exist_ok=True)

    report_path = build_dir / "build-report.json"
    log_path = build_dir / "build.log"
    resolved_output = Path(output_path) if output_path else default_output_path(build_dir, target)
    resolved_output.parent.mkdir(parents=True, exist_ok=True)

    command = build_command(executable, project, target, resolved_output, report_path, log_path)

    process = popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        exit_code = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.wait()
        raise BuildError(
            f"构建超时（>{timeout_seconds:.0f}s），已强制终止 Unity 构建进程",
            code="build_timeout",
        ) from exc

    report, report_source = _read_report(report_path, log_path, exit_code)

    return BuildResult(
        ok=report.get("result") == "Succeeded",
        build_id=build_id,
        result=report.get("result", "Failed"),
        report={**report, "reportSource": report_source},
        report_path=report_path,
        log_path=log_path,
        output_path=resolved_output,
        exit_code=exit_code,
        command=command,
    )


def _read_report(report_path: Path, log_path: Path, exit_code: int) -> tuple[dict[str, Any], str]:
    if report_path.exists():
        try:
            return json.loads(report_path.read_text(encoding="utf-8")), "build_report"
        except json.JSONDecodeError:
            pass

    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    errors = parse_log_fallback_errors(log_text)
    if not errors:
        errors = [
            f"构建报告缺失，且未能从 build.log 中提取具体编译错误（Unity 进程 exit code {exit_code}）"
        ]

    return (
        {
            "result": "Failed",
            "durationMs": 0,
            "outputPath": "",
            "sizeBytes": 0,
            "errors": errors,
            "warnings": [],
        },
        "log_fallback",
    )
