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


def test_load_log_rules_returns_empty_ignore_when_file_missing(tmp_path):
    assert load_log_rules(tmp_path) == {"ignore": []}
