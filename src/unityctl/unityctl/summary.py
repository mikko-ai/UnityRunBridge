import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any


PROBLEM_TYPES = {"Error"}
BLOCKING_TYPES = {"Exception", "Assert"}

# Bridge 写入的 Play Mode 运行边界事件行（runStarted/runEnded），
# 不是 Unity Console 日志：不参与问题分类、watch 匹配和日志计数。
BRIDGE_EVENT_TYPE = "BridgeEvent"

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
    scenario_result: dict[str, Any] | None = None,
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
    log_count = 0
    last_problem = None
    watch_rules = rule_payload.get("watch", [])
    watched_count = 0
    watched_logs: list[dict[str, Any]] = []
    runs_by_index: dict[int, dict[str, Any]] = {}

    for line, row in enumerate(logs, start=1):
        log_type = str(row.get("type", "Log"))
        run_index = row.get("runIndex", 0)
        run = _run_entry(runs_by_index, run_index) if isinstance(run_index, int) and run_index >= 1 else None

        if run is not None:
            _track_run_sequence(run, row.get("sequence"))

        if log_type == BRIDGE_EVENT_TYPE:
            if run is not None:
                event = row.get("event")
                if event == "runStarted":
                    run["startedAt"] = row.get("time")
                elif event == "runEnded":
                    run["endedAt"] = row.get("time")
            continue

        log_count += 1
        if log_type in counts:
            counts[log_type] += 1
        if run is not None:
            run["logCount"] += 1

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
            if run is not None:
                run["problemCount"] += 1
        if severity == "blocking":
            problem_count += 1
            blocking_problem_count += 1
            last_problem = problem_payload(row, "blocking")
            if run is not None:
                run["problemCount"] += 1
                run["blockingProblemCount"] += 1

    runs = [runs_by_index[index] for index in sorted(runs_by_index)]
    # 一个 session 内 CLI 只会触发一轮 play，出现第二轮即说明有人在 Editor 中
    # 手动重新进入过 Play Mode——结果可能混入非受控运行，agent 应据此决定是否重跑。
    manual_intervention_detected = len(runs) > 1

    session_status = session_payload.get("status")
    session_failed_reason = session_payload.get("failedReason") if session_status == "failed" else None

    # 断言失败视为 blocking：与 Exception/Assert 日志同级，任何一条不通过整个 session 就是 failed。
    scenario_failed = bool(scenario_result) and scenario_result.get("stepsFailed", 0) > 0

    if session_status == "failed":
        status = "failed"
    elif blocking_problem_count > 0 or scenario_failed:
        status = "failed"
    elif problem_count > 0:
        status = "problem_detected"
    else:
        status = "passed"

    started_at = session_payload.get("startedAt")
    ended_at = session_payload.get("endedAt")

    payload: dict[str, Any] = {
        "status": status,
        "hasProblems": problem_count > 0,
        "hasBlockingProblems": blocking_problem_count > 0,
        "logCount": log_count,
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
        "runs": runs,
        "manualInterventionDetected": manual_intervention_detected,
    }

    if scenario_result:
        payload["scenario"] = {
            "name": scenario_result.get("name"),
            "stepsTotal": scenario_result.get("stepsTotal", 0),
            "stepsPassed": scenario_result.get("stepsPassed", 0),
            "stepsFailed": scenario_result.get("stepsFailed", 0),
            "assertions": scenario_result.get("assertions", []),
        }

    metrics_section = _build_metrics_section(session)
    if metrics_section:
        payload["metrics"] = metrics_section

    return payload


def _run_entry(runs_by_index: dict[int, dict[str, Any]], run_index: int) -> dict[str, Any]:
    """runIndex 标记日志发生在第 N 轮 Play Mode 开始之后、第 N+1 轮开始之前（0 表示
    第一轮开始之前的编辑期日志，不构成 run）。startedAt/endedAt 取自 Bridge 写入的
    runStarted/runEnded 边界事件行。"""
    if run_index not in runs_by_index:
        runs_by_index[run_index] = {
            "runIndex": run_index,
            "startedAt": None,
            "endedAt": None,
            "sequenceStart": None,
            "sequenceEnd": None,
            "logCount": 0,
            "problemCount": 0,
            "blockingProblemCount": 0,
        }
    return runs_by_index[run_index]


def _track_run_sequence(run: dict[str, Any], sequence: Any) -> None:
    if not isinstance(sequence, int):
        return
    if run["sequenceStart"] is None or sequence < run["sequenceStart"]:
        run["sequenceStart"] = sequence
    if run["sequenceEnd"] is None or sequence > run["sequenceEnd"]:
        run["sequenceEnd"] = sequence


def _build_metrics_section(session: Path) -> dict[str, Any] | None:
    """session 存在 artifacts/metrics.jsonl（profile-start/profile-stop 产出）时，
    按指标名聚合 avg/max/p95；不存在或没有任何数值样本时省略该字段（不写空对象）。"""
    rows = read_jsonl(session / "artifacts" / "metrics.jsonl")
    if not rows:
        return None

    values_by_metric: dict[str, list[float]] = {}
    for row in rows:
        for key, value in row.items():
            if key in ("frame", "time") or not isinstance(value, (int, float)):
                continue
            values_by_metric.setdefault(key, []).append(float(value))

    if not values_by_metric:
        return None

    metrics: dict[str, Any] = {}
    for name, values in values_by_metric.items():
        sorted_values = sorted(values)
        metrics[name] = {
            "avg": sum(sorted_values) / len(sorted_values),
            "max": sorted_values[-1],
            "p95": _percentile(sorted_values, 0.95),
        }

    return {"frameCount": len(rows), "metrics": metrics}


def _percentile(sorted_values: list[float], fraction: float) -> float:
    index = math.ceil(fraction * len(sorted_values)) - 1
    index = max(0, min(len(sorted_values) - 1, index))
    return sorted_values[index]


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
