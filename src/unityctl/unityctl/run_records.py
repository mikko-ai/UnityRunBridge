"""Read Scenario, UTF and Midscene evidence from one project-local index."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from unityctl.config import SESSIONS_DIRNAME, TEST_RUNS_DIRNAME, VISUAL_RUNS_DIRNAME
from unityctl.discovery import is_pid_alive

_SOURCES = {
    "scenario": (SESSIONS_DIRNAME, "session.json"),
    "utf": (TEST_RUNS_DIRNAME, "test-report.json"),
    "midscene": (VISUAL_RUNS_DIRNAME, "run-record.json"),
}
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}")
_MAX_JSON = 8 * 1024 * 1024


class RunRecordError(ValueError):
    pass


def _under(directory: Path, candidate: Path) -> Path | None:
    """Do not follow project-controlled symlinks or expose paths outside a run."""
    try:
        relative = candidate.relative_to(directory)
        if any(part == ".." for part in relative.parts):
            return None
        parent = directory
        if parent.is_symlink():
            return None
        for part in relative.parts:
            parent /= part
            if parent.is_symlink():
                return None
        return parent if parent.is_file() else None
    except (OSError, ValueError):
        return None


def _load(path: Path) -> dict:
    with path.open("rb") as stream:
        raw = stream.read(_MAX_JSON + 1)
    if len(raw) > _MAX_JSON:
        raise ValueError("报告过大")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("报告不是对象")
    return result


def _pid_state(record: dict, status: str) -> str:
    if status != "running":
        return status
    pid = record.get("runnerPid")
    if type(pid) is int and pid > 0:
        return "running" if is_pid_alive(pid) else "interrupted"
    return "unknown"


def _artifact(run: Path, name: str, kind: str, raw: str | None = None) -> dict[str, str] | None:
    candidate = Path(raw) if isinstance(raw, str) else run / name
    if not candidate.is_absolute():
        candidate = run / candidate
    scoped = _under(run, candidate)
    return {"kind": kind, "path": str(scoped)} if scoped else None


def _opened_at(meta: dict, path: Path) -> str:
    raw = meta.get("startedAt") or meta.get("createdAt")
    if isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is not None:
                return dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def _read(directory: Path, kind: str, *, details: bool) -> dict[str, Any]:
    filename = _SOURCES[kind][1]
    meta_path = _under(directory, directory / filename)
    if meta_path is None:
        raise RunRecordError("运行不存在或报告路径不可读")
    meta = _load(meta_path)
    record = {
        "key": f"{kind}:{directory.name}", "id": directory.name, "kind": kind,
        "name": directory.name, "status": "unknown", "at": _opened_at(meta, meta_path),
    }
    if details:
        record.update(artifacts=[], steps=[], failures=[])

    def add(name: str, artifact_kind: str, raw: str | None = None, *, within: Path | None = None) -> str | None:
        root = within or directory
        entry = _artifact(root, name, artifact_kind, raw)
        if entry is not None and entry not in record["artifacts"]:
            record["artifacts"].append(entry)
        return entry["path"] if entry else None

    if kind == "scenario":
        if meta.get("trigger") != "scenario" or meta.get("sessionId") != directory.name:
            raise RunRecordError("该会话不是 Scenario 运行")
        record["name"] = meta.get("name") or directory.name
        source = _under(directory, directory / "artifacts/scenario-result.json")
        if source is not None:
            result = _load(source)
            record["status"] = result.get("status") if result.get("status") in {"passed", "failed"} else "unknown"
            if details:
                add("artifacts/scenario-result.json", "report")
                for step in result.get("steps", []):
                    if not isinstance(step, dict):
                        continue
                    evidence = step.get("evidence")
                    evidence = evidence if isinstance(evidence, dict) else {}
                    raw = evidence.get("screenshotPath")
                    if raw is None and step.get("action") in {"snapshot", "screenshot"}:
                        raw = evidence.get("path")
                    frame = None
                    if isinstance(raw, str) and Path(raw).suffix.lower() == ".png":
                        frame = add("", "screenshot", raw, within=directory / "artifacts")
                    row = {key: step.get(key) for key in ("id", "action", "status", "failureType")}
                    row.update(screenshot=frame, code=evidence.get("code"))
                    if step.get("status") == "failed":
                        row["expected"] = evidence.get("expected")
                        row["actual"] = evidence.get("actual")
                        row["message"] = evidence.get("message")
                        record["failures"].append(row)
                    record["steps"].append(row)
        elif meta.get("status") == "failed":
            record["status"] = "failed"
        elif meta.get("status") == "running":
            # A session alone only knows the Editor PID; it cannot prove the runner is alive.
            events_file = _under(directory, directory / "run-events.jsonl")
            record["status"] = "unknown"
            if events_file is not None:
                with events_file.open("rb") as events:
                    first = events.readline(65536)
                if first.endswith(b"\n"):
                    start = json.loads(first)
                    if isinstance(start, dict) and start.get("type") == "run-started":
                        record["status"] = _pid_state(start, "running")
        if details:
            record["code"] = meta.get("failedReason")
            add("session.json", "session")
            add("summary.json", "summary")
            add("unity-console.jsonl", "log")
            add("run-events.jsonl", "events")
    elif kind == "utf":
        if meta.get("jobId") != directory.name or meta.get("schemaVersion") != 1:
            raise RunRecordError("UTF 报告与任务 ID 不匹配")
        record["name"] = f"{meta.get('mode') or 'UTF'} · {meta.get('filter') or directory.name}"
        record["status"] = _pid_state(meta, meta.get("status") or "unknown")
        if details:
            record.update(counts=meta.get("counts"), code=meta.get("code"))
            record["failures"] = [item for item in meta.get("failures", []) if isinstance(item, dict)]
            add("test-report.json", "report")
            add("results.xml", "nunit")
            add("unity.log", "log")
    else:
        if meta.get("id") != directory.name or meta.get("schemaVersion") != 1:
            raise RunRecordError("Midscene 记录与运行 ID 不匹配")
        record["name"] = meta.get("name") or directory.name
        record["status"] = _pid_state(meta, meta.get("status") or "unknown")
        record["mode"] = meta.get("mode")
        if details:
            add("run-record.json", "record")
            add("events.jsonl", "log")
            report = meta.get("report")
            if isinstance(report, str) and Path(report).suffix.lower() == ".html":
                add("", "html", report)
            for step in meta.get("steps", []):
                if not isinstance(step, dict):
                    continue
                row = {key: step.get(key) for key in ("id", "action", "status", "code")}
                frame = step.get("screenshot")
                if isinstance(frame, str) and Path(frame).suffix.lower() == ".png":
                    row["screenshot"] = add("", "screenshot", frame)
                if row["status"] == "failed":
                    record["failures"].append(row)
                record["steps"].append(row)
    return record


def _root(project: Path, kind: str) -> Path | None:
    state = project / ".unity-agent"
    directory = state / _SOURCES[kind][0]
    if state.is_symlink() or directory.is_symlink() or not directory.is_dir():
        return None
    return directory


def list_runs(project: Path, kind: str | None, limit: int) -> dict:
    records = []
    unreadable = 0
    for source in [kind] if kind else _SOURCES:
        root = _root(project, source)
        if root is None:
            continue
        for path in root.iterdir():
            if path.is_symlink() or not path.is_dir() or not _ID.fullmatch(path.name):
                continue
            try:
                records.append(_read(path, source, details=False))
            except RunRecordError:
                # Non-scenario play sessions, empty dirs and unrelated output are not part of the index.
                pass
            except (OSError, ValueError, TypeError):
                unreadable += 1
    records.sort(key=lambda item: (item["at"], item["key"]), reverse=True)
    return {"runs": records[:limit], "total": len(records), "unreadable": unreadable}


def show_run(project: Path, key: str) -> dict:
    kind, separator, run_id = key.partition(":")
    if not separator or kind not in _SOURCES or not _ID.fullmatch(run_id):
        raise RunRecordError("运行 ID 应为 scenario:<id>、utf:<id> 或 midscene:<id>")
    root = _root(project, kind)
    if root is None:
        raise RunRecordError("没有该运行")
    try:
        return _read(root / run_id, kind, details=True)
    except (OSError, TypeError, ValueError) as exc:
        if isinstance(exc, RunRecordError):
            raise
        raise RunRecordError("运行报告损坏或不可读") from exc
