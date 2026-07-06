import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROBLEM_TYPES = {"Error"}
BLOCKING_TYPES = {"Exception", "Assert"}

# summary.json 中 watchedLogs 保留的最大条数（watchedCount 始终是全量命中数）。
# watch 规则匹配到高频日志（如每帧心跳）时避免 summary 无限膨胀。
WATCHED_LOGS_LIMIT = 50


def load_log_rules(project_path: str | Path) -> dict[str, list[dict[str, str]]]:
    rules_path = Path(project_path).expanduser().resolve() / ".unity-agent" / "log-rules.json"
    empty: dict[str, list[dict[str, str]]] = {"ignore": [], "watch": []}
    if not rules_path.exists():
        return empty
    payload = json.loads(rules_path.read_text(encoding="utf-8"))
    result = dict(empty)
    for key in ("ignore", "watch"):
        rules = payload.get(key, [])
        if isinstance(rules, list):
            result[key] = [rule for rule in rules if isinstance(rule, dict)]
    return result


def build_summary(
    session_path: str | Path,
    rules: dict[str, list[dict[str, str]]] | None = None,
) -> dict[str, Any]:
    session = Path(session_path).expanduser().resolve()
    rule_payload = rules or {"ignore": [], "watch": []}
    logs = read_jsonl(session / "unity-console.jsonl")
    session_payload = read_json(session / "session.json")

    counts = {
        "Log": 0,
        "Warning": 0,
        "Error": 0,
        "Exception": 0,
        "Assert": 0,
    }
    ignored_problem_count = 0
    problem_count = 0
    blocking_problem_count = 0
    last_problem = None
    watch_rules = rule_payload.get("watch", [])
    watched_count = 0
    watched_logs: list[dict[str, Any]] = []

    for line, row in enumerate(logs, start=1):
        log_type = str(row.get("type", "Log"))
        if log_type in counts:
            counts[log_type] += 1

        if watch_rules and matches_rules(row, watch_rules):
            watched_count += 1
            watched_logs.append(watched_payload(row, line))

        severity = classify_log(row, rule_payload)
        if severity == "ignored_problem":
            ignored_problem_count += 1
            continue
        if severity == "problem":
            problem_count += 1
            last_problem = problem_payload(row, "problem")
        if severity == "blocking":
            problem_count += 1
            blocking_problem_count += 1
            last_problem = problem_payload(row, "blocking")

    session_status = session_payload.get("status")
    session_failed_reason = session_payload.get("failedReason") if session_status == "failed" else None

    if session_status == "failed":
        status = "failed"
    elif blocking_problem_count > 0:
        status = "failed"
    elif problem_count > 0:
        status = "problem_detected"
    else:
        status = "passed"

    started_at = session_payload.get("startedAt")
    ended_at = session_payload.get("endedAt")

    return {
        "status": status,
        "hasProblems": problem_count > 0,
        "hasBlockingProblems": blocking_problem_count > 0,
        "logCount": len(logs),
        "warningCount": counts["Warning"],
        "errorCount": counts["Error"],
        "exceptionCount": counts["Exception"],
        "assertCount": counts["Assert"],
        "ignoredProblemCount": ignored_problem_count,
        "blockingProblemCount": blocking_problem_count,
        "lastProblem": last_problem,
        "watchedCount": watched_count,
        "watchedLogs": watched_logs[-WATCHED_LOGS_LIMIT:],
        "startedAt": started_at,
        "endedAt": ended_at,
        "durationMs": duration_ms(started_at, ended_at),
        "failedReason": session_failed_reason,
    }


def write_summary(session_path: str | Path, summary: dict[str, Any]) -> Path:
    path = Path(session_path).expanduser().resolve() / "summary.json"
    path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def classify_log(row: dict[str, Any], rules: dict[str, list[dict[str, str]]]) -> str:
    log_type = str(row.get("type", "Log"))
    if log_type not in PROBLEM_TYPES and log_type not in BLOCKING_TYPES:
        return "normal"
    if matches_rules(row, rules.get("ignore", [])):
        return "ignored_problem"
    if log_type in BLOCKING_TYPES:
        return "blocking"
    return "problem"


def matches_rules(row: dict[str, Any], rules: list[dict[str, str]]) -> bool:
    """ignore 与 watch 共用的规则匹配：type 精确匹配，messageContains 子串匹配，
    两个条件都给出时须同时满足。"""
    log_type = str(row.get("type", ""))
    message = str(row.get("message", ""))
    for rule in rules:
        expected_type = rule.get("type")
        message_contains = rule.get("messageContains")
        if expected_type and expected_type != log_type:
            continue
        if message_contains and message_contains not in message:
            continue
        return True
    return False


def problem_payload(row: dict[str, Any], severity: str) -> dict[str, Any]:
    return {
        "type": row.get("type"),
        "message": row.get("message"),
        "severity": severity,
        "sequence": row.get("sequence"),
        "playModeFrame": row.get("playModeFrame"),
        "scenePath": row.get("scenePath"),
    }


def watched_payload(row: dict[str, Any], line: int) -> dict[str, Any]:
    return {
        "line": line,
        "type": row.get("type"),
        "message": row.get("message"),
        "sequence": row.get("sequence"),
        "playModeFrame": row.get("playModeFrame"),
        "scenePath": row.get("scenePath"),
    }


def duration_ms(started_at: str | None, ended_at: str | None) -> int | None:
    if not started_at or not ended_at:
        return None
    start = parse_time(started_at)
    end = parse_time(ended_at)
    return int((end - start).total_seconds() * 1000)


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
