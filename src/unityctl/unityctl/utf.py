"""Run Unity Test Framework in an isolated batch Editor process."""

import json
import math
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree

from unityctl.config import TEST_RUNS_DIRNAME, normalize_unity_executable_path
from unityctl.discovery import is_pid_alive, is_unity_project_locked

_JOB_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}")


class UtfError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _job_dir(project: Path, job_id: str) -> Path:
    if not _JOB_ID.fullmatch(job_id):
        raise UtfError("invalid_argument", "job ID 必须由 1–64 个字母、数字、下划线或连字符组成，且以字母或数字开头")
    agent_dir = project / ".unity-agent"
    root = agent_dir / TEST_RUNS_DIRNAME
    directory = root / job_id
    if any(path.is_symlink() for path in (agent_dir, root, directory)):
        raise UtfError("invalid_argument", "测试产物目录不能是符号链接")
    return directory


def _write_report(path: Path, report: dict) -> None:
    pending = path.with_suffix(".pending")
    pending.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def read_test_job(project: Path, job_id: str) -> dict:
    path = _job_dir(project, job_id) / "test-report.json"
    if path.is_symlink():
        raise UtfError("invalid_argument", "测试报告不能是符号链接")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise UtfError("test_job_not_found", f"找不到测试任务：{job_id}") from exc
    except (ValueError, OSError) as exc:
        raise UtfError("test_report_invalid", "无法读取测试报告") from exc
    if not isinstance(report, dict) or report.get("jobId") != job_id:
        raise UtfError("test_report_invalid", "测试报告中的任务 ID 不匹配")
    if report.get("status") == "running":
        owner = report.get("runnerPid")
        if not isinstance(owner, int) or isinstance(owner, bool) or owner <= 0:
            raise UtfError("test_report_invalid", "测试报告中的 runnerPid 无效")
        if not is_pid_alive(owner):
            report.update(ok=False, status="interrupted", code="test_interrupted",
                          message="测试编排进程已退出，未生成最终报告")
    return report


def parse_nunit(path: Path) -> dict:
    root = ElementTree.parse(path).getroot()
    if root.tag != "test-run":
        raise ValueError("结果不是 NUnit test-run")
    keys = ("total", "passed", "failed", "skipped", "inconclusive")
    counts = {key: int(root.attrib[key]) for key in keys}
    if min(counts.values()) < 0 or sum(counts[key] for key in keys[1:]) != counts["total"]:
        raise ValueError("NUnit 总数与分类计数不一致")
    result = re.split(r"[:(]", root.attrib["result"], maxsplit=1)[0]
    if result not in {"Passed", "Failed", "Skipped", "Inconclusive"}:
        raise ValueError("NUnit 结果状态无效")
    failures = []
    for item in root.iter():
        if item.tag not in {"test-suite", "test-case"}:
            continue
        failure = item.find("failure")
        child_summary = item.tag == "test-suite" and "Child" in (item.get("label"), item.get("site"))
        if failure is None or child_summary:
            continue
        failures.append({
            "name": item.get("fullname") or item.get("name"),
            "kind": "suite" if item.tag == "test-suite" else "test",
            "message": failure.findtext("message") or "",
            "stackTrace": failure.findtext("stack-trace") or "",
        })
    return {"counts": counts, "failures": failures, "nunitResult": result}


def run_tests(
    project: Path, executable: Path | None, *, mode: str, test_filter: str | None = None,
    job_id: str | None = None, timeout: float = 900,
) -> dict:
    if mode not in {"EditMode", "PlayMode"} or not math.isfinite(timeout) or timeout <= 0:
        raise UtfError("invalid_argument", "mode 必须为 EditMode 或 PlayMode，timeout 必须为有限正数")
    unity = normalize_unity_executable_path(executable)
    if unity is None:
        raise UtfError("invalid_request", "请配置 Unity Editor 可执行文件")
    if is_unity_project_locked(project):
        raise UtfError("editor_running", "Unity 项目已被占用；请关闭该项目的 Editor 或使用独立测试副本")

    job_id = job_id if job_id is not None else uuid4().hex
    directory = _job_dir(project, job_id)
    try:
        directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise UtfError("test_job_exists", f"任务 ID 已存在：{job_id}") from exc
    report_path = directory / "test-report.json"
    xml_path = directory / "results.xml"
    log_path = directory / "unity.log"
    report = {
        "ok": True, "code": "ok", "schemaVersion": 1, "jobId": job_id, "status": "running",
        "mode": mode, "filter": test_filter, "runnerPid": os.getpid(),
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "reportPath": str(report_path), "resultsPath": str(xml_path), "logPath": str(log_path),
    }
    _write_report(report_path, report)
    started = time.monotonic()
    command = [str(unity), "-batchmode", "-projectPath", str(project), "-runTests",
               "-testPlatform", mode, "-testResults", str(xml_path), "-logFile", str(log_path)]
    if test_filter:
        command.extend(["-testFilter", test_filter])

    def fail(code: str, message: str, status: str = "failed") -> None:
        report.update(ok=False, code=code, message=message, status=status)

    try:
        process = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 timeout=timeout, check=False)
        report["exitCode"] = process.returncode
        try:
            report.update(parse_nunit(xml_path))
        except (OSError, ValueError, KeyError, ElementTree.ParseError):
            fail("test_result_unavailable", "Unity 未写出有效 NUnit XML；请检查 Unity 日志")
        else:
            counts = report["counts"]
            if counts["failed"] or report["failures"] or report["nunitResult"] == "Failed":
                fail("tests_failed", "UTF 测试或测试套件失败")
            elif process.returncode != 0:
                fail("test_process_failed", "Unity 进程非零退出；请检查 Unity 日志")
            elif counts["inconclusive"]:
                fail("tests_inconclusive", "UTF 包含无法判定结果的测试")
            elif not counts["passed"]:
                fail("no_tests_passed", "没有通过的测试；检查过滤器或是否全部跳过")
            else:
                report["status"] = "passed"
    except subprocess.TimeoutExpired:
        fail("test_timeout", "UTF 超时，已终止本次启动的 Unity 进程", "timed_out")
    except KeyboardInterrupt:
        fail("test_interrupted", "UTF 已由调用者中断", "interrupted")
    except OSError as exc:
        fail("test_launch_failed", f"无法启动 Unity：{exc}")
    report["durationMs"] = round((time.monotonic() - started) * 1000)
    _write_report(report_path, report)
    return report
