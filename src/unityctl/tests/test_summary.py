import json

from unityctl.summary import build_summary, load_log_rules


def write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_build_summary_marks_exception_as_failed(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    (session / "session.json").write_text(
        json.dumps(
            {
                "startedAt": "2026-06-30T18:30:12Z",
                "endedAt": "2026-06-30T18:31:02Z",
            }
        ),
        encoding="utf-8",
    )
    write_jsonl(
        session / "unity-console.jsonl",
        [
            {
                "sequence": 1,
                "type": "Log",
                "message": "ready",
                "playModeFrame": 1,
                "scenePath": "Assets/A.unity",
            },
            {
                "sequence": 2,
                "type": "Exception",
                "message": "NullReferenceException",
                "playModeFrame": 3,
                "scenePath": "Assets/A.unity",
            },
        ],
    )

    summary = build_summary(session, rules={"ignore": []})

    assert summary["status"] == "failed"
    assert summary["hasProblems"] is True
    assert summary["hasBlockingProblems"] is True
    assert summary["logCount"] == 2
    assert summary["exceptionCount"] == 1
    assert summary["blockingProblemCount"] == 1
    assert summary["lastProblem"]["message"] == "NullReferenceException"
    assert summary["durationMs"] == 50000


def test_error_without_blocking_rule_is_problem_detected(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    (session / "session.json").write_text(
        json.dumps({"startedAt": None, "endedAt": None}),
        encoding="utf-8",
    )
    write_jsonl(
        session / "unity-console.jsonl",
        [
            {
                "sequence": 1,
                "type": "Error",
                "message": "Expected test error",
                "playModeFrame": 5,
                "scenePath": "Assets/A.unity",
            }
        ],
    )

    summary = build_summary(session, rules={"ignore": []})

    assert summary["status"] == "problem_detected"
    assert summary["hasProblems"] is True
    assert summary["hasBlockingProblems"] is False
    assert summary["errorCount"] == 1
    assert summary["blockingProblemCount"] == 0


def test_ignore_rule_removes_expected_error_from_problem_count(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    (session / "session.json").write_text(
        json.dumps({"startedAt": None, "endedAt": None}),
        encoding="utf-8",
    )
    write_jsonl(
        session / "unity-console.jsonl",
        [
            {
                "sequence": 1,
                "type": "Error",
                "message": "Expected test error",
                "playModeFrame": 5,
                "scenePath": "Assets/A.unity",
            }
        ],
    )

    summary = build_summary(
        session,
        rules={"ignore": [{"type": "Error", "messageContains": "Expected test error"}]},
    )

    assert summary["status"] == "passed"
    assert summary["hasProblems"] is False
    assert summary["ignoredProblemCount"] == 1


def test_load_log_rules_returns_empty_rules_when_file_missing(tmp_path):
    assert load_log_rules(tmp_path) == {"ignore": [], "watch": []}


def test_load_log_rules_reads_watch_rules(tmp_path):
    rules_dir = tmp_path / ".unity-agent"
    rules_dir.mkdir()
    (rules_dir / "log-rules.json").write_text(
        json.dumps(
            {
                "ignore": [{"type": "Error", "messageContains": "harmless"}],
                "watch": [{"messageContains": "LoginSuccess"}],
            }
        ),
        encoding="utf-8",
    )

    rules = load_log_rules(tmp_path)

    assert rules["ignore"] == [{"type": "Error", "messageContains": "harmless"}]
    assert rules["watch"] == [{"messageContains": "LoginSuccess"}]


def test_watch_rules_extract_matching_logs_into_summary(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    (session / "session.json").write_text(
        json.dumps({"startedAt": None, "endedAt": None}),
        encoding="utf-8",
    )
    write_jsonl(
        session / "unity-console.jsonl",
        [
            {
                "sequence": 1,
                "type": "Log",
                "message": "Boot start",
                "playModeFrame": 0,
                "scenePath": "Assets/A.unity",
            },
            {
                "sequence": 2,
                "type": "Log",
                "message": "LoginSuccess user=guest01",
                "playModeFrame": 120,
                "scenePath": "Assets/A.unity",
            },
            {
                "sequence": 3,
                "type": "Error",
                "message": "LoginSuccess but inventory failed",
                "playModeFrame": 130,
                "scenePath": "Assets/A.unity",
            },
        ],
    )

    summary = build_summary(
        session,
        rules={"ignore": [], "watch": [{"messageContains": "LoginSuccess"}]},
    )

    assert summary["watchedCount"] == 2
    assert [row["line"] for row in summary["watchedLogs"]] == [2, 3]
    assert summary["watchedLogs"][0]["message"] == "LoginSuccess user=guest01"
    # watch 不影响问题分类：第 3 条 Error 仍计入问题
    assert summary["status"] == "problem_detected"


def test_watch_rules_keep_only_most_recent_entries_but_full_count(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    (session / "session.json").write_text(
        json.dumps({"startedAt": None, "endedAt": None}),
        encoding="utf-8",
    )
    write_jsonl(
        session / "unity-console.jsonl",
        [
            {
                "sequence": index,
                "type": "Log",
                "message": f"heartbeat #{index}",
                "playModeFrame": index,
                "scenePath": "Assets/A.unity",
            }
            for index in range(1, 61)
        ],
    )

    summary = build_summary(
        session,
        rules={"ignore": [], "watch": [{"messageContains": "heartbeat"}]},
    )

    assert summary["watchedCount"] == 60
    assert len(summary["watchedLogs"]) == 50
    assert summary["watchedLogs"][0]["line"] == 11
    assert summary["watchedLogs"][-1]["line"] == 60


def test_summary_without_watch_rules_has_empty_watched_fields(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    (session / "session.json").write_text(
        json.dumps({"startedAt": None, "endedAt": None}),
        encoding="utf-8",
    )
    write_jsonl(
        session / "unity-console.jsonl",
        [
            {
                "sequence": 1,
                "type": "Log",
                "message": "ready",
                "playModeFrame": 1,
                "scenePath": "Assets/A.unity",
            }
        ],
    )

    summary = build_summary(session, rules={"ignore": []})

    assert summary["watchedCount"] == 0
    assert summary["watchedLogs"] == []


def test_build_summary_propagates_session_level_failure_even_without_log_problems(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    (session / "session.json").write_text(
        json.dumps(
            {
                "startedAt": "2026-06-30T18:30:12Z",
                "endedAt": "2026-06-30T18:31:02Z",
                "status": "failed",
                "failedReason": "timeout",
            }
        ),
        encoding="utf-8",
    )
    write_jsonl(
        session / "unity-console.jsonl",
        [
            {
                "sequence": 1,
                "type": "Log",
                "message": "ready",
                "playModeFrame": 1,
                "scenePath": "Assets/A.unity",
            }
        ],
    )

    summary = build_summary(session, rules={"ignore": []})

    assert summary["status"] == "failed"
    assert summary["failedReason"] == "timeout"
    assert summary["hasProblems"] is False


def test_build_summary_embeds_scenario_section_when_provided(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    (session / "session.json").write_text(
        json.dumps({"startedAt": None, "endedAt": None, "status": "stopped"}),
        encoding="utf-8",
    )
    write_jsonl(session / "unity-console.jsonl", [])

    scenario_result = {
        "name": "login-flow",
        "stepsTotal": 3,
        "stepsPassed": 3,
        "stepsFailed": 0,
        "assertions": [
            {"id": "login-log", "status": "passed", "expected": {}, "actual": {}, "evidence": None}
        ],
    }

    summary = build_summary(session, rules={"ignore": []}, scenario_result=scenario_result)

    assert summary["status"] == "passed"
    assert summary["scenario"] == {
        "name": "login-flow",
        "stepsTotal": 3,
        "stepsPassed": 3,
        "stepsFailed": 0,
        "assertions": scenario_result["assertions"],
    }


def test_build_summary_marks_status_failed_when_scenario_has_failed_steps(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    (session / "session.json").write_text(
        json.dumps({"startedAt": None, "endedAt": None, "status": "stopped"}),
        encoding="utf-8",
    )
    write_jsonl(session / "unity-console.jsonl", [])

    scenario_result = {
        "name": "login-flow",
        "stepsTotal": 3,
        "stepsPassed": 2,
        "stepsFailed": 1,
        "assertions": [],
    }

    summary = build_summary(session, rules={"ignore": []}, scenario_result=scenario_result)

    assert summary["status"] == "failed"


def test_build_summary_omits_scenario_key_when_not_provided(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    (session / "session.json").write_text(
        json.dumps({"startedAt": None, "endedAt": None}),
        encoding="utf-8",
    )
    write_jsonl(session / "unity-console.jsonl", [])

    summary = build_summary(session, rules={"ignore": []})

    assert "scenario" not in summary


def test_build_summary_groups_logs_by_run_index(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    (session / "session.json").write_text(
        json.dumps({"startedAt": None, "endedAt": None}),
        encoding="utf-8",
    )
    write_jsonl(
        session / "unity-console.jsonl",
        [
            {"sequence": 1, "type": "Log", "message": "bridge listening", "runIndex": 0},
            {
                "time": "2026-07-08T11:51:10.000Z",
                "sequence": 2,
                "type": "BridgeEvent",
                "event": "runStarted",
                "message": "runStarted (run 1)",
                "runIndex": 1,
            },
            {"sequence": 3, "type": "Log", "message": "Awake", "runIndex": 1},
            {"sequence": 4, "type": "Error", "message": "run1 error", "runIndex": 1},
            {
                "time": "2026-07-08T11:51:48.000Z",
                "sequence": 5,
                "type": "BridgeEvent",
                "event": "runEnded",
                "message": "runEnded (run 1)",
                "runIndex": 1,
            },
            {
                "time": "2026-07-08T11:52:25.000Z",
                "sequence": 6,
                "type": "BridgeEvent",
                "event": "runStarted",
                "message": "runStarted (run 2)",
                "runIndex": 2,
            },
            {"sequence": 7, "type": "Exception", "message": "run2 exception", "runIndex": 2},
        ],
    )

    summary = build_summary(session, rules={"ignore": []})

    # BridgeEvent 边界行不计入日志统计
    assert summary["logCount"] == 4
    assert summary["manualInterventionDetected"] is True
    assert [run["runIndex"] for run in summary["runs"]] == [1, 2]

    run1, run2 = summary["runs"]
    assert run1["startedAt"] == "2026-07-08T11:51:10.000Z"
    assert run1["endedAt"] == "2026-07-08T11:51:48.000Z"
    assert run1["sequenceStart"] == 2
    assert run1["sequenceEnd"] == 5
    assert run1["logCount"] == 2
    assert run1["problemCount"] == 1
    assert run1["blockingProblemCount"] == 0

    # 第二轮仍在运行（没有 runEnded）
    assert run2["startedAt"] == "2026-07-08T11:52:25.000Z"
    assert run2["endedAt"] is None
    assert run2["logCount"] == 1
    assert run2["problemCount"] == 1
    assert run2["blockingProblemCount"] == 1


def test_build_summary_single_run_is_not_manual_intervention(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    (session / "session.json").write_text(
        json.dumps({"startedAt": None, "endedAt": None}),
        encoding="utf-8",
    )
    write_jsonl(
        session / "unity-console.jsonl",
        [
            {
                "time": "2026-07-08T11:51:10.000Z",
                "sequence": 1,
                "type": "BridgeEvent",
                "event": "runStarted",
                "message": "runStarted (run 1)",
                "runIndex": 1,
            },
            {"sequence": 2, "type": "Log", "message": "Awake", "runIndex": 1},
            {
                "time": "2026-07-08T11:51:48.000Z",
                "sequence": 3,
                "type": "BridgeEvent",
                "event": "runEnded",
                "message": "runEnded (run 1)",
                "runIndex": 1,
            },
        ],
    )

    summary = build_summary(session, rules={"ignore": []})

    assert summary["manualInterventionDetected"] is False
    assert len(summary["runs"]) == 1
    assert summary["status"] == "passed"


def test_build_summary_without_runs_has_empty_runs(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    (session / "session.json").write_text(
        json.dumps({"startedAt": None, "endedAt": None}),
        encoding="utf-8",
    )
    write_jsonl(
        session / "unity-console.jsonl",
        [{"sequence": 1, "type": "Log", "message": "edit mode only", "runIndex": 0}],
    )

    summary = build_summary(session, rules={"ignore": []})

    assert summary["runs"] == []
    assert summary["manualInterventionDetected"] is False


def test_build_summary_embeds_metrics_section_when_metrics_jsonl_present(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    (session / "session.json").write_text(
        json.dumps({"startedAt": None, "endedAt": None}),
        encoding="utf-8",
    )
    write_jsonl(session / "unity-console.jsonl", [])
    artifacts_dir = session / "artifacts"
    artifacts_dir.mkdir()
    write_jsonl(
        artifacts_dir / "metrics.jsonl",
        [
            {"frame": 0, "time": 0.0, "frameTimeMs": 10.0, "drawCalls": 100},
            {"frame": 1, "time": 0.1, "frameTimeMs": 20.0, "drawCalls": 200},
        ],
    )

    summary = build_summary(session, rules={"ignore": []})

    assert summary["metrics"]["frameCount"] == 2
    assert summary["metrics"]["metrics"]["frameTimeMs"]["avg"] == 15.0
    assert summary["metrics"]["metrics"]["frameTimeMs"]["max"] == 20.0
    assert summary["metrics"]["metrics"]["drawCalls"]["avg"] == 150.0


def test_build_summary_omits_metrics_key_when_metrics_jsonl_absent(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    (session / "session.json").write_text(
        json.dumps({"startedAt": None, "endedAt": None}),
        encoding="utf-8",
    )
    write_jsonl(session / "unity-console.jsonl", [])

    summary = build_summary(session, rules={"ignore": []})

    assert "metrics" not in summary
