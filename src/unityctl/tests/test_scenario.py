import json
from pathlib import Path
from typing import Any, Callable

import pytest

from unityctl.client import BridgeClientError
from unityctl.scenario import (
    ScenarioContext,
    ScenarioValidationError,
    convert_recording_to_scenario,
    evaluate_condition,
    load_scenario,
    run_scenario,
    validate_scenario,
)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


class FakeClient:
    """最小可用的假 BridgeClient：每个方法都可以按需覆盖为固定返回值/异常/回调序列。"""

    def __init__(self) -> None:
        self.status_queue: list[dict[str, Any]] = [{"editorState": "idle"}]
        self.post_handler: Callable[[str, dict[str, Any] | None], dict[str, Any]] = (
            lambda path, payload=None: {"ok": True, "code": "accepted"}
        )
        self.hierarchy_inspect_handler: Callable[..., dict[str, Any]] = lambda **params: {
            "ok": True,
            "node": None,
        }
        self.hierarchy_find_handler: Callable[..., dict[str, Any]] = lambda **params: {
            "ok": True,
            "matchedCount": 0,
            "nodes": [],
        }
        self.gameplay_invoke_handler: Callable[[str, dict[str, Any]], dict[str, Any]] = (
            lambda command, args: {"ok": True, "result": None}
        )
        self.interaction_click_handler: Callable[..., dict[str, Any]] = lambda **kwargs: {
            "ok": True,
            "clicked": kwargs.get("path"),
        }
        self.interaction_input_handler: Callable[..., dict[str, Any]] = lambda **kwargs: {"ok": True}
        self.interaction_set_value_handler: Callable[..., dict[str, Any]] = lambda **kwargs: {"ok": True}
        self.interaction_long_press_handler: Callable[..., dict[str, Any]] = lambda **kwargs: {
            "ok": True,
            "jobId": "job-lp-1",
        }
        self.interaction_drag_handler: Callable[..., dict[str, Any]] = lambda **kwargs: {
            "ok": True,
            "jobId": "job-drag-1",
        }
        self.capture_screenshot_handler: Callable[..., dict[str, Any]] = lambda **kwargs: {
            "ok": True,
            "jobId": "job-1",
        }
        self.get_job_handler: Callable[[str], dict[str, Any]] = lambda job_id: {
            "job": {
                "status": "succeeded",
                "result": {
                    "path": "/tmp/shot.png",
                    "ok": True,
                    "kind": "long-press",
                    "events": ["pointerEnter", "pointerDown", "pointerUp", "pointerExit"],
                },
            }
        }
        self.get_capabilities_handler: Callable[[], dict[str, Any]] = lambda: {
            "ok": True,
            "capabilities": ["core", "interaction"],
            "routes": [
                {"method": "POST", "path": "interaction/long-press"},
                {"method": "POST", "path": "interaction/drag"},
            ],
        }
        self.open_scene_handler: Callable[[str], dict[str, Any]] = lambda scene: {"ok": True}
        self.profiling_start_handler: Callable[..., dict[str, Any]] = lambda **kwargs: {
            "ok": True,
            "metricsPath": "/tmp/metrics.jsonl",
            "unavailableMetrics": [],
        }
        self.profiling_stop_handler: Callable[[], dict[str, Any]] = lambda: {
            "ok": True,
            "metricsPath": "/tmp/metrics.jsonl",
            "frameCount": 120,
            "interrupted": False,
            "aggregates": {},
        }
        self.calls: list[tuple[str, Any]] = []

    def get_status(self) -> dict[str, Any]:
        status = self.status_queue[-1] if len(self.status_queue) == 1 else self.status_queue.pop(0)
        self.calls.append(("get_status", None))
        return status

    def post(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((f"post:{path}", payload))
        return self.post_handler(path, payload)

    def open_scene(self, scene_path: str) -> dict[str, Any]:
        self.calls.append(("open_scene", scene_path))
        return self.open_scene_handler(scene_path)

    def interaction_click(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("interaction_click", kwargs))
        return self.interaction_click_handler(**kwargs)

    def interaction_input(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("interaction_input", kwargs))
        return self.interaction_input_handler(**kwargs)

    def interaction_set_value(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("interaction_set_value", kwargs))
        return self.interaction_set_value_handler(**kwargs)

    def interaction_long_press(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("interaction_long_press", kwargs))
        return self.interaction_long_press_handler(**kwargs)

    def interaction_drag(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("interaction_drag", kwargs))
        return self.interaction_drag_handler(**kwargs)

    def gameplay_invoke(self, command: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append(("gameplay_invoke", (command, args)))
        return self.gameplay_invoke_handler(command, args or {})

    def hierarchy_inspect(self, **params: Any) -> dict[str, Any]:
        self.calls.append(("hierarchy_inspect", params))
        return self.hierarchy_inspect_handler(**params)

    def hierarchy_find(self, **params: Any) -> dict[str, Any]:
        self.calls.append(("hierarchy_find", params))
        return self.hierarchy_find_handler(**params)

    def capture_screenshot(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("capture_screenshot", kwargs))
        return self.capture_screenshot_handler(**kwargs)

    def get_job(self, job_id: str) -> dict[str, Any]:
        self.calls.append(("get_job", job_id))
        return self.get_job_handler(job_id)

    def get_capabilities(self) -> dict[str, Any]:
        self.calls.append(("get_capabilities", None))
        return self.get_capabilities_handler()

    def profiling_start(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("profiling_start", kwargs))
        return self.profiling_start_handler(**kwargs)

    def profiling_stop(self) -> dict[str, Any]:
        self.calls.append(("profiling_stop", None))
        return self.profiling_stop_handler()


def make_ctx(tmp_path: Path, client: FakeClient | None = None, **overrides: Any) -> ScenarioContext:
    session_path = tmp_path / "session"
    session_path.mkdir(exist_ok=True)
    defaults: dict[str, Any] = {
        "client": client or FakeClient(),
        "session_path": session_path,
        "sleep_fn": lambda seconds: None,
        "poll_interval": 0,
    }
    defaults.update(overrides)
    return ScenarioContext(**defaults)


# ---------------------------------------------------------------------------
# validate_scenario
# ---------------------------------------------------------------------------


def test_validate_scenario_requires_name_and_steps():
    errors = validate_scenario({})
    assert any("name" in e for e in errors)
    assert any("steps" in e for e in errors)


@pytest.mark.parametrize("value", ["bad", 0, -1, float("nan"), float("inf"), True])
def test_validate_scenario_rejects_invalid_default_wait_timeout(value):
    errors = validate_scenario(
        {
            "name": "x",
            "defaults": {"waitTimeoutSeconds": value},
            "steps": [{"action": "play"}],
        }
    )

    assert any("defaults.waitTimeoutSeconds" in error for error in errors)


def test_validate_scenario_rejects_unsupported_action():
    errors = validate_scenario({"name": "x", "steps": [{"action": "teleport"}]})
    assert len(errors) == 1
    assert "step[0]" in errors[0]
    assert "teleport" in errors[0]


def test_validate_scenario_requires_scene_for_open_scene():
    errors = validate_scenario({"name": "x", "steps": [{"action": "open-scene"}]})
    assert any("scene" in e for e in errors)


def test_validate_scenario_requires_path_for_click_input_set_value():
    for action in ("click", "input", "set-value"):
        errors = validate_scenario({"name": "x", "steps": [{"action": action}]})
        assert any("path" in e for e in errors), f"{action} should require path"


def test_validate_scenario_requires_path_and_delta_for_gestures():
    assert any("path" in e for e in validate_scenario({"name": "x", "steps": [{"action": "long-press"}]}))
    assert any("path" in e for e in validate_scenario({"name": "x", "steps": [{"action": "drag"}]}))
    errors = validate_scenario({"name": "x", "steps": [{"action": "drag", "path": "A/B"}]})
    assert any("deltaX" in e for e in errors)


@pytest.mark.parametrize(
    "step,field",
    [
        ({"action": "long-press", "path": "A/B", "durationSeconds": 0}, "durationSeconds"),
        ({"action": "long-press", "path": "A/B", "durationSeconds": 3601}, "durationSeconds"),
        (
            {"action": "drag", "path": "A/B", "deltaX": float("inf"), "deltaY": 1},
            "deltaX",
        ),
        (
            {"action": "drag", "path": "A/B", "deltaX": 10**1000, "deltaY": 1},
            "deltaX",
        ),
        ({"action": "drag", "path": "A/B", "deltaX": 1, "deltaY": 1, "steps": 1.9}, "steps"),
        ({"action": "drag", "path": "A/B", "deltaX": 1, "deltaY": 1, "steps": 4097}, "steps"),
        (
            {
                "action": "long-press",
                "path": "A/B",
                "durationSeconds": 1,
                "timeoutSeconds": float("nan"),
            },
            "timeoutSeconds",
        ),
    ],
)
def test_validate_scenario_rejects_invalid_gesture_numeric_fields(step, field):
    errors = validate_scenario({"name": "x", "steps": [step]})

    assert any(field in error for error in errors)


def test_validate_scenario_requires_text_for_input():
    errors = validate_scenario({"name": "x", "steps": [{"action": "input", "path": "A/B"}]})
    assert any("text" in e for e in errors)


def test_validate_scenario_requires_value_for_set_value():
    errors = validate_scenario({"name": "x", "steps": [{"action": "set-value", "path": "A/B"}]})
    assert any("value" in e for e in errors)


def test_validate_scenario_requires_command_for_invoke():
    errors = validate_scenario({"name": "x", "steps": [{"action": "invoke"}]})
    assert any("command" in e for e in errors)


def test_validate_scenario_assert_requires_exactly_one_source():
    errors = validate_scenario({"name": "x", "steps": [{"action": "assert"}]})
    assert any("source" in e for e in errors)

    errors_two_sources = validate_scenario(
        {"name": "x", "steps": [{"action": "assert", "ui": {"path": "A"}, "log": {}}]}
    )
    assert any("source" in e for e in errors_two_sources)


def test_validate_scenario_ui_condition_requires_path_or_find():
    errors = validate_scenario({"name": "x", "steps": [{"action": "assert", "ui": {"exists": True}}]})
    assert any("path 或 find" in e for e in errors)


def test_validate_scenario_gameplay_condition_requires_single_compare_op():
    no_op = validate_scenario(
        {"name": "x", "steps": [{"action": "assert", "gameplay": {"command": "Foo.Bar"}}]}
    )
    assert any("比较符" in e for e in no_op)

    two_ops = validate_scenario(
        {
            "name": "x",
            "steps": [
                {"action": "assert", "gameplay": {"command": "Foo.Bar", "equals": 1, "atLeast": 1}}
            ],
        }
    )
    assert any("比较符" in e for e in two_ops)


def test_validate_scenario_detects_duplicate_assert_ids():
    scenario = {
        "name": "x",
        "steps": [
            {"action": "assert", "id": "dup", "ui": {"path": "A", "exists": True}},
            {"action": "assert", "id": "dup", "ui": {"path": "B", "exists": True}},
        ],
    }
    errors = validate_scenario(scenario)
    assert any("重复" in e for e in errors)


def test_validate_scenario_accepts_profile_start_and_stop():
    scenario = {
        "name": "x",
        "steps": [{"action": "profile-start"}, {"action": "profile-stop"}],
    }
    assert validate_scenario(scenario) == []


def test_validate_scenario_rejects_invalid_metric_aggregate():
    errors = validate_scenario(
        {
            "name": "x",
            "steps": [
                {"action": "assert", "metric": {"name": "frameTimeMs", "aggregate": "median", "atMost": 16}}
            ],
        }
    )
    assert any("aggregate" in e for e in errors)


def test_validate_scenario_accepts_well_formed_scenario():
    scenario = {
        "name": "login-flow",
        "steps": [
            {"action": "open-scene", "scene": "Assets/Scenes/Login.unity"},
            {"action": "play"},
            {"action": "wait-for", "ui": {"path": "A/B", "activeInHierarchy": True}},
            {"action": "assert", "id": "closed", "ui": {"path": "A/B", "activeInHierarchy": False}},
            {"action": "stop"},
        ],
    }
    assert validate_scenario(scenario) == []


def test_load_scenario_reads_json_file(tmp_path):
    scenario_file = tmp_path / "scenario.json"
    scenario_file.write_text(json.dumps({"name": "x", "steps": [{"action": "play"}]}), encoding="utf-8")
    loaded = load_scenario(scenario_file)
    assert loaded["name"] == "x"


# ---------------------------------------------------------------------------
# evaluate_condition：断言判定的四类 source
# ---------------------------------------------------------------------------


def test_evaluate_ui_condition_path_mode_pass_and_fail(tmp_path):
    client = FakeClient()
    client.hierarchy_inspect_handler = lambda **params: {
        "ok": True,
        "node": {"path": params["path"], "scene": "Main", "activeInHierarchy": True, "text": "Hello"},
    }
    ctx = make_ctx(tmp_path, client)

    ok, evidence = evaluate_condition(ctx, "ui", {"path": "A/B", "activeInHierarchy": True}, 0)
    assert ok is True
    assert evidence["dataSource"] == "hierarchy/inspect"

    ok, _ = evaluate_condition(ctx, "ui", {"path": "A/B", "activeInHierarchy": False}, 0)
    assert ok is False


def test_evaluate_ui_condition_text_contains(tmp_path):
    client = FakeClient()
    client.hierarchy_inspect_handler = lambda **params: {
        "ok": True,
        "node": {"path": params["path"], "scene": "Main", "text": "购买道具"},
    }
    ctx = make_ctx(tmp_path, client)

    ok, _ = evaluate_condition(ctx, "ui", {"path": "A/B", "textContains": "购买"}, 0)
    assert ok is True

    ok, _ = evaluate_condition(ctx, "ui", {"path": "A/B", "textEquals": "购买道具"}, 0)
    assert ok is True

    ok, _ = evaluate_condition(ctx, "ui", {"path": "A/B", "textEquals": "出售"}, 0)
    assert ok is False


def test_evaluate_ui_condition_node_not_found_treated_as_missing(tmp_path):
    client = FakeClient()

    def raise_not_found(**params):
        raise BridgeClientError("not found", code="node_not_found")

    client.hierarchy_inspect_handler = raise_not_found
    ctx = make_ctx(tmp_path, client)

    ok, evidence = evaluate_condition(ctx, "ui", {"path": "A/B", "exists": False}, 0)
    assert ok is True
    assert evidence["node"] is None

    ok, _ = evaluate_condition(ctx, "ui", {"path": "A/B", "exists": True}, 0)
    assert ok is False


def test_evaluate_ui_condition_other_errors_surface_as_evidence(tmp_path):
    client = FakeClient()

    def raise_ambiguous(**params):
        raise BridgeClientError("ambiguous", code="ambiguous_path")

    client.hierarchy_inspect_handler = raise_ambiguous
    ctx = make_ctx(tmp_path, client)

    ok, evidence = evaluate_condition(ctx, "ui", {"path": "A/B", "exists": True}, 0)
    assert ok is False
    assert evidence["error"] == "ambiguous_path"


def test_evaluate_ui_condition_find_mode_count_checks(tmp_path):
    client = FakeClient()
    client.hierarchy_find_handler = lambda **params: {"ok": True, "matchedCount": 5, "nodes": []}
    ctx = make_ctx(tmp_path, client)

    ok, evidence = evaluate_condition(ctx, "ui", {"find": {"component": "Slot"}, "countEquals": 5}, 0)
    assert ok is True
    assert evidence["matchedCount"] == 5

    ok, _ = evaluate_condition(ctx, "ui", {"find": {"component": "Slot"}, "countAtLeast": 6}, 0)
    assert ok is False

    ok, _ = evaluate_condition(ctx, "ui", {"find": {"component": "Slot"}, "countAtMost": 10}, 0)
    assert ok is True


def test_evaluate_log_condition_message_contains_and_since_sequence(tmp_path):
    ctx = make_ctx(tmp_path)
    write_jsonl(
        ctx.session_path / "unity-console.jsonl",
        [
            {"sequence": 1, "type": "Log", "message": "Login success"},
            {"sequence": 2, "type": "Log", "message": "unrelated"},
        ],
    )

    ok, evidence = evaluate_condition(ctx, "log", {"messageContains": "Login success"}, 0)
    assert ok is True
    assert evidence["matchedCount"] == 1

    # sinceSequence=2 排除掉 sequence=1 的那条命中日志
    ok, _ = evaluate_condition(ctx, "log", {"messageContains": "Login success"}, 2)
    assert ok is False


def test_evaluate_log_condition_absent(tmp_path):
    ctx = make_ctx(tmp_path)
    write_jsonl(
        ctx.session_path / "unity-console.jsonl",
        [{"sequence": 1, "type": "Exception", "message": "boom"}],
    )

    ok, _ = evaluate_condition(ctx, "log", {"type": "Exception", "absent": True}, 0)
    assert ok is False

    ok, _ = evaluate_condition(ctx, "log", {"type": "Assert", "absent": True}, 0)
    assert ok is True


@pytest.mark.parametrize(
    "op,expected_value,actual,should_pass",
    [
        ("equals", 100, 100, True),
        ("equals", 100, 99, False),
        ("notEquals", 100, 99, True),
        ("greaterThan", 10, 11, True),
        ("greaterThan", 10, 9, False),
        ("lessThan", 10, 9, True),
        ("atLeast", 10, 10, True),
        ("atMost", 10, 10, True),
        ("atMost", 10, 11, False),
    ],
)
def test_evaluate_gameplay_condition_compare_ops(tmp_path, op, expected_value, actual, should_pass):
    client = FakeClient()
    client.gameplay_invoke_handler = lambda command, args: {"ok": True, "result": actual}
    ctx = make_ctx(tmp_path, client)

    ok, evidence = evaluate_condition(ctx, "gameplay", {"command": "Foo.Bar", op: expected_value}, 0)
    assert ok is should_pass
    assert evidence["actual"] == actual


def test_evaluate_gameplay_condition_handles_bridge_error(tmp_path):
    client = FakeClient()

    def raise_not_found(command, args):
        raise BridgeClientError("not found", code="command_not_found")

    client.gameplay_invoke_handler = raise_not_found
    ctx = make_ctx(tmp_path, client)

    ok, evidence = evaluate_condition(ctx, "gameplay", {"command": "Foo.Bar", "equals": 1}, 0)
    assert ok is False
    assert evidence["error"] == "command_not_found"


def test_evaluate_metric_condition_returns_not_available_when_file_missing(tmp_path):
    ctx = make_ctx(tmp_path)
    ok, evidence = evaluate_condition(ctx, "metric", {"name": "frameTimeMs", "atMost": 16}, 0)
    assert ok is False
    assert evidence["error"] == "metric_not_available"


def test_evaluate_metric_condition_returns_not_available_when_metric_absent(tmp_path):
    ctx = make_ctx(tmp_path)
    artifacts_dir = ctx.session_path / "artifacts"
    artifacts_dir.mkdir(parents=True)
    write_jsonl(artifacts_dir / "metrics.jsonl", [{"frame": 1, "time": 0.0, "drawCalls": 10}])

    ok, evidence = evaluate_condition(ctx, "metric", {"name": "frameTimeMs", "atMost": 16}, 0)
    assert ok is False
    assert evidence["error"] == "metric_not_available"


def test_evaluate_metric_condition_computes_avg_by_default(tmp_path):
    ctx = make_ctx(tmp_path)
    artifacts_dir = ctx.session_path / "artifacts"
    artifacts_dir.mkdir(parents=True)
    write_jsonl(
        artifacts_dir / "metrics.jsonl",
        [
            {"frame": 1, "time": 0.0, "frameTimeMs": 10.0},
            {"frame": 2, "time": 0.1, "frameTimeMs": 20.0},
        ],
    )

    ok, evidence = evaluate_condition(ctx, "metric", {"name": "frameTimeMs", "atMost": 15}, 0)
    assert ok is True
    assert evidence["actual"] == pytest.approx(15.0)
    assert evidence["aggregate"] == "avg"
    assert evidence["sampleCount"] == 2


def test_evaluate_metric_condition_max_and_p95(tmp_path):
    ctx = make_ctx(tmp_path)
    artifacts_dir = ctx.session_path / "artifacts"
    artifacts_dir.mkdir(parents=True)
    rows = [{"frame": i, "time": float(i), "frameTimeMs": float(i)} for i in range(1, 21)]
    write_jsonl(artifacts_dir / "metrics.jsonl", rows)

    ok, evidence = evaluate_condition(
        ctx, "metric", {"name": "frameTimeMs", "aggregate": "max", "atMost": 20}, 0
    )
    assert ok is True
    assert evidence["actual"] == 20.0

    ok, evidence = evaluate_condition(
        ctx, "metric", {"name": "frameTimeMs", "aggregate": "p95", "atMost": 19}, 0
    )
    assert ok is True
    assert evidence["actual"] == 19.0


# ---------------------------------------------------------------------------
# run_scenario：整体执行引擎
# ---------------------------------------------------------------------------


def _base_scenario(steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {"name": "test-scenario", "description": "", "defaults": {"waitTimeoutSeconds": 5}, "steps": steps}


def test_run_scenario_all_pass(tmp_path):
    client = FakeClient()
    client.status_queue = [{"editorState": "playing"}]
    client.hierarchy_inspect_handler = lambda **params: {
        "ok": True,
        "node": {"path": params["path"], "scene": "Main", "activeInHierarchy": True},
    }

    scenario = _base_scenario(
        [
            {"action": "play"},
            {"action": "click", "path": "A/Button"},
            {"action": "assert", "id": "visible", "ui": {"path": "A/Panel", "activeInHierarchy": True}},
        ]
    )
    ctx = make_ctx(tmp_path, client)

    result = run_scenario(scenario, ctx)

    assert result["status"] == "passed"
    assert result["stepsTotal"] == 3
    assert result["stepsPassed"] == 3
    assert result["stepsFailed"] == 0
    assert result["stepsSkipped"] == 0
    assert len(result["assertions"]) == 1
    assert result["assertions"][0]["id"] == "visible"
    assert result["assertions"][0]["status"] == "passed"
    # 每个 step 的内部记录不应该泄漏到公开结果里
    assert "_extra" not in result["steps"][0]


def test_run_scenario_long_press_and_drag_wait_for_jobs(tmp_path):
    client = FakeClient()
    scenario = _base_scenario(
        [
            {"action": "long-press", "path": "A/Button", "durationSeconds": 0.2},
            {"action": "drag", "path": "A/Handle", "deltaX": 10, "deltaY": -5, "steps": 3},
        ]
    )
    ctx = make_ctx(tmp_path, client)
    result = run_scenario(scenario, ctx)

    assert result["status"] == "passed"
    assert result["stepsPassed"] == 2
    assert any(call[0] == "interaction_long_press" for call in client.calls)
    assert any(call[0] == "interaction_drag" for call in client.calls)
    assert any(call[0] == "get_job" for call in client.calls)


def test_run_scenario_gesture_job_failure_keeps_evidence(tmp_path):
    client = FakeClient()
    client.interaction_long_press_handler = lambda **kwargs: {"ok": True, "jobId": "job-fail"}
    client.get_job_handler = lambda job_id: {
        "job": {
            "status": "failed",
            "errorCode": "occluded",
            "errorMessage": "blocked",
            "result": {
                "events": ["pointerEnter"],
                "blockedBy": "A/Overlay",
                "start": {"x": 1, "y": 2},
                "end": {"x": 1, "y": 2},
                "durationSeconds": 0.2,
            },
        }
    }
    scenario = _base_scenario([{"action": "long-press", "path": "A/Button"}])
    ctx = make_ctx(tmp_path, client)
    result = run_scenario(scenario, ctx)

    assert result["status"] == "failed"
    evidence = result["steps"][0]["evidence"]
    assert evidence["code"] == "occluded"
    assert evidence["blockedBy"] == "A/Overlay"
    assert evidence["events"] == ["pointerEnter"]


def test_run_scenario_uses_injected_reload_aware_job_waiter(tmp_path):
    client = FakeClient()
    observed = {}

    def wait_job(job_id, timeout_seconds, raise_on_failure):
        observed.update(
            {
                "jobId": job_id,
                "timeout": timeout_seconds,
                "raiseOnFailure": raise_on_failure,
            }
        )
        return {
            "id": job_id,
            "status": "failed",
            "errorCode": "interrupted_by_reload",
            "errorMessage": "job interrupted by editor domain reload",
        }

    scenario = _base_scenario([{"action": "long-press", "path": "A/Button"}])
    ctx = make_ctx(tmp_path, client, job_wait_fn=wait_job)

    result = run_scenario(scenario, ctx)

    assert observed["jobId"] == "job-lp-1"
    assert observed["raiseOnFailure"] is False
    assert result["steps"][0]["evidence"]["jobId"] == "job-lp-1"
    assert result["steps"][0]["evidence"]["code"] == "interrupted_by_reload"


def test_run_scenario_gesture_job_timeout_keeps_job_id(tmp_path):
    client = FakeClient()
    client.get_job_handler = lambda job_id: {"job": {"id": job_id, "status": "running"}}
    now = [0.0]
    scenario = _base_scenario(
        [{"action": "long-press", "path": "A/Button", "timeoutSeconds": 0.15}]
    )
    ctx = make_ctx(
        tmp_path,
        client,
        now_fn=lambda: now[0],
        sleep_fn=lambda seconds: now.__setitem__(0, now[0] + 0.1),
        poll_interval=0.1,
    )

    result = run_scenario(scenario, ctx)

    step = result["steps"][0]
    assert step["status"] == "failed"
    assert step["failureType"] == "timeout"
    assert step["evidence"]["jobId"] == "job-lp-1"


def test_run_scenario_gesture_default_timeout_covers_server_deadline(tmp_path):
    client = FakeClient()
    client.get_job_handler = lambda job_id: {"job": {"id": job_id, "status": "running"}}
    now = [0.0]
    scenario = _base_scenario(
        [{"action": "long-press", "path": "A/Button", "durationSeconds": 30}]
    )
    ctx = make_ctx(
        tmp_path,
        client,
        now_fn=lambda: now[0],
        sleep_fn=lambda seconds: now.__setitem__(0, now[0] + 10.0),
        poll_interval=10.0,
    )

    result = run_scenario(scenario, ctx)

    assert result["steps"][0]["failureType"] == "timeout"
    assert now[0] >= 36.0


def test_run_scenario_gesture_explicit_timeout_is_not_extended(tmp_path):
    client = FakeClient()
    client.get_job_handler = lambda job_id: {"job": {"id": job_id, "status": "running"}}
    now = [0.0]
    scenario = _base_scenario(
        [
            {
                "action": "long-press",
                "path": "A/Button",
                "durationSeconds": 30,
                "timeoutSeconds": 2,
            }
        ]
    )
    ctx = make_ctx(
        tmp_path,
        client,
        now_fn=lambda: now[0],
        sleep_fn=lambda seconds: now.__setitem__(0, now[0] + 1.0),
        poll_interval=1.0,
    )

    result = run_scenario(scenario, ctx)

    assert result["steps"][0]["failureType"] == "timeout"
    assert now[0] == 2.0


def test_run_scenario_gesture_missing_route_returns_capability_error(tmp_path):
    client = FakeClient()
    client.get_capabilities_handler = lambda: {
        "ok": True,
        "capabilities": ["core", "interaction"],
        "routes": [{"method": "POST", "path": "interaction/click"}],
    }
    scenario = _base_scenario([{"action": "drag", "path": "A/Handle", "deltaX": 10, "deltaY": 5}])

    result = run_scenario(scenario, make_ctx(tmp_path, client))

    step = result["steps"][0]
    assert step["status"] == "failed"
    assert step["evidence"]["code"] == "bridge_capability_missing"
    assert not any(call[0] == "interaction_drag" for call in client.calls)


def test_run_scenario_assertion_failure_skips_subsequent_steps_by_default(tmp_path):
    client = FakeClient()
    client.hierarchy_inspect_handler = lambda **params: {
        "ok": True,
        "node": {"path": params["path"], "scene": "Main", "activeInHierarchy": False},
    }

    scenario = _base_scenario(
        [
            {"action": "assert", "id": "should-fail", "ui": {"path": "A/Panel", "activeInHierarchy": True}},
            {"action": "click", "path": "A/Button"},
        ]
    )
    ctx = make_ctx(tmp_path, client)

    result = run_scenario(scenario, ctx)

    assert result["status"] == "failed"
    assert result["stepsFailed"] == 1
    assert result["stepsSkipped"] == 1
    assert result["steps"][0]["status"] == "failed"
    assert result["steps"][0]["failureType"] == "assertion_failed"
    assert result["steps"][1]["status"] == "skipped"


def test_run_scenario_assertion_failure_captures_screenshot_when_enabled(tmp_path):
    client = FakeClient()
    client.hierarchy_inspect_handler = lambda **params: {"ok": True, "node": None}

    scenario = _base_scenario([{"action": "assert", "ui": {"path": "A/Panel", "exists": True}}])
    ctx = make_ctx(tmp_path, client, capture_config={"onAssertFailure": True, "onScenarioStep": True})

    result = run_scenario(scenario, ctx)

    assert result["steps"][0]["status"] == "failed"
    assert result["steps"][0]["evidence"]["screenshotPath"] == "/tmp/shot.png"
    assert any(call[0] == "capture_screenshot" for call in client.calls)


def test_run_scenario_assertion_failure_skips_screenshot_when_disabled(tmp_path):
    client = FakeClient()
    client.hierarchy_inspect_handler = lambda **params: {"ok": True, "node": None}

    scenario = _base_scenario([{"action": "assert", "ui": {"path": "A/Panel", "exists": True}}])
    ctx = make_ctx(tmp_path, client, capture_config={"onAssertFailure": False, "onScenarioStep": True})

    result = run_scenario(scenario, ctx)

    assert result["steps"][0]["status"] == "failed"
    assert "screenshotPath" not in (result["steps"][0]["evidence"] or {})
    assert not any(call[0] == "capture_screenshot" for call in client.calls)


def test_run_scenario_continue_on_failure_keeps_running_subsequent_steps(tmp_path):
    client = FakeClient()
    client.hierarchy_inspect_handler = lambda **params: {"ok": True, "node": None}

    scenario = _base_scenario(
        [
            {"action": "assert", "continueOnFailure": True, "ui": {"path": "A/Panel", "exists": True}},
            {"action": "click", "path": "A/Button"},
        ]
    )
    ctx = make_ctx(tmp_path, client)

    result = run_scenario(scenario, ctx)

    assert result["stepsFailed"] == 1
    assert result["stepsSkipped"] == 0
    assert result["steps"][1]["status"] == "passed"


def test_run_scenario_wait_for_timeout_reports_timeout_failure_type(tmp_path):
    client = FakeClient()
    client.hierarchy_inspect_handler = lambda **params: {"ok": True, "node": None}

    ticks = {"count": 0}

    def fake_now():
        # 单调递增而不是两段式取值：run_scenario 本身也会在步骤前后各调用一次
        # now_fn 来计算 durationMs，两段式设计会让 deadline 恰好等于后续所有取值，永远无法超时。
        ticks["count"] += 1
        return ticks["count"] * 10.0

    scenario = _base_scenario(
        [{"action": "wait-for", "timeoutSeconds": 1, "ui": {"path": "A/Panel", "exists": True}}]
    )
    ctx = make_ctx(tmp_path, client, now_fn=fake_now)

    result = run_scenario(scenario, ctx)

    assert result["steps"][0]["status"] == "failed"
    assert result["steps"][0]["failureType"] == "timeout"


def test_run_scenario_teardown_stops_play_mode_when_still_playing(tmp_path):
    client = FakeClient()
    client.status_queue = [{"editorState": "playing"}, {"editorState": "playing"}, {"editorState": "idle"}]
    client.hierarchy_inspect_handler = lambda **params: {"ok": True, "node": None}

    scenario = _base_scenario(
        [
            {"action": "play"},
            {"action": "assert", "ui": {"path": "A/Panel", "exists": True}},
        ]
    )
    ctx = make_ctx(tmp_path, client)

    result = run_scenario(scenario, ctx)

    assert result["status"] == "failed"
    assert any(call == ("post:stop", None) for call in client.calls)


def test_run_scenario_execution_error_from_bridge_client_error(tmp_path):
    client = FakeClient()

    def raise_error(**kwargs):
        raise BridgeClientError("occluded", code="occluded")

    client.interaction_click_handler = raise_error

    scenario = _base_scenario([{"action": "click", "path": "A/Button"}])
    ctx = make_ctx(tmp_path, client)

    result = run_scenario(scenario, ctx)

    assert result["steps"][0]["status"] == "failed"
    assert result["steps"][0]["failureType"] == "execution_error"
    assert result["steps"][0]["evidence"]["code"] == "occluded"


def test_run_scenario_screenshot_step_skipped_when_config_disabled(tmp_path):
    client = FakeClient()
    scenario = _base_scenario([{"action": "screenshot"}])
    ctx = make_ctx(tmp_path, client, capture_config={"onAssertFailure": True, "onScenarioStep": False})

    result = run_scenario(scenario, ctx)

    assert result["steps"][0]["status"] == "passed"
    assert result["steps"][0]["evidence"]["skipped"] is True
    assert not any(call[0] == "capture_screenshot" for call in client.calls)


def test_run_scenario_profile_start_and_stop(tmp_path):
    client = FakeClient()
    scenario = _base_scenario([{"action": "profile-start"}, {"action": "profile-stop"}])
    ctx = make_ctx(tmp_path, client)

    result = run_scenario(scenario, ctx)

    assert result["status"] == "passed"
    assert any(call[0] == "profiling_start" for call in client.calls)
    assert any(call[0] == "profiling_stop" for call in client.calls)
    assert result["steps"][1]["evidence"]["frameCount"] == 120


def test_run_scenario_profile_start_failure_reports_execution_error(tmp_path):
    client = FakeClient()
    client.profiling_start_handler = lambda **kwargs: {"ok": False, "code": "already_profiling"}
    scenario = _base_scenario([{"action": "profile-start"}])
    ctx = make_ctx(tmp_path, client)

    result = run_scenario(scenario, ctx)

    assert result["steps"][0]["status"] == "failed"
    assert result["steps"][0]["failureType"] == "execution_error"


def test_run_scenario_metric_assertion_end_to_end(tmp_path):
    client = FakeClient()
    session_path = tmp_path / "session"
    session_path.mkdir(exist_ok=True)

    def fake_profile_stop():
        artifacts_dir = session_path / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        write_jsonl(
            artifacts_dir / "metrics.jsonl",
            [{"frame": i, "time": float(i), "frameTimeMs": 10.0} for i in range(5)],
        )
        return {"ok": True, "metricsPath": str(artifacts_dir / "metrics.jsonl"), "frameCount": 5}

    client.profiling_stop_handler = fake_profile_stop

    scenario = _base_scenario(
        [
            {"action": "profile-start"},
            {"action": "profile-stop"},
            {"action": "assert", "id": "frame-budget", "metric": {"name": "frameTimeMs", "atMost": 16}},
        ]
    )
    ctx = make_ctx(tmp_path, client, session_path=session_path)

    result = run_scenario(scenario, ctx)

    assert result["status"] == "passed"
    assert result["assertions"][0]["id"] == "frame-budget"
    assert result["assertions"][0]["actual"] == 10.0


def test_run_scenario_raises_validation_error_for_invalid_scenario(tmp_path):
    ctx = make_ctx(tmp_path)
    with pytest.raises(ScenarioValidationError):
        run_scenario({"name": "x", "steps": [{"action": "not-a-real-action"}]}, ctx)


# ---------------------------------------------------------------------------
# convert_recording_to_scenario
# ---------------------------------------------------------------------------


def test_convert_recording_to_scenario_requires_meta_file(tmp_path):
    actions_path = tmp_path / "actions.jsonl"
    write_jsonl(actions_path, [])
    with pytest.raises(ScenarioValidationError):
        convert_recording_to_scenario(actions_path)


def test_convert_recording_to_scenario_builds_steps_from_actions(tmp_path):
    actions_path = tmp_path / "actions.jsonl"
    meta_path = tmp_path / "recording-meta.json"
    meta_path.write_text(
        json.dumps({"activeScene": "Main", "sessionId": "2026-07-07_120000_demo"}), encoding="utf-8"
    )
    write_jsonl(
        actions_path,
        [
            {"time": 0.5, "frame": 10, "type": "click", "scene": "Main", "path": "A/Button", "screenPos": {"x": 1, "y": 2}},
            {"time": 1.2, "frame": 20, "type": "input", "scene": "Main", "path": "A/Field", "text": "hello"},
        ],
    )

    scenario = convert_recording_to_scenario(actions_path)

    assert scenario["steps"][0] == {"action": "open-scene", "scene": "Main"}
    assert scenario["steps"][1] == {"action": "play"}
    assert scenario["steps"][2]["action"] == "click"
    assert scenario["steps"][2]["path"] == "A/Button"
    assert scenario["steps"][2]["recordedGap"] == 0.5
    assert scenario["steps"][3]["action"] == "input"
    assert scenario["steps"][3]["text"] == "hello"
    assert scenario["steps"][3]["recordedGap"] == pytest.approx(0.7)
    assert scenario["steps"][-1] == {"action": "stop"}
    assert scenario["name"] == "recording-2026-07-07_120000_demo"
    # 草稿不含任何断言
    assert not any(step["action"] == "assert" for step in scenario["steps"])
    assert validate_scenario(scenario) == []


def test_convert_recording_to_scenario_accepts_custom_name(tmp_path):
    actions_path = tmp_path / "actions.jsonl"
    meta_path = tmp_path / "recording-meta.json"
    meta_path.write_text(json.dumps({"activeScene": "Main", "sessionId": "s1"}), encoding="utf-8")
    write_jsonl(actions_path, [])

    scenario = convert_recording_to_scenario(actions_path, name="custom-name")

    assert scenario["name"] == "custom-name"
