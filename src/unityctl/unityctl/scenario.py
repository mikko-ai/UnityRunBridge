"""Phase 3：scenario 线性步骤表的加载/校验/执行引擎 + 录制转草稿。

设计原则（详见计划文档 Phase 3）：
- 断言判定逻辑全部在这里（Python 侧），Bridge 只提供事实（hierarchy/logs/gameplay invoke）。
- v1 无变量/条件分支/循环——scenario 是线性步骤表。
- 执行引擎只依赖 BridgeClient 的公开方法 + session 目录下的 unity-console.jsonl，
  不直接做 discover()/domain-reload 重连（那是 cmd_play/cmd_stop 的职责边界），
  便于用一个假 BridgeClient 完整覆盖单测。
"""

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from unityctl.client import BridgeClient, BridgeClientError
from unityctl.summary import read_jsonl


CONTROL_ACTIONS = {"open-scene", "play", "stop", "pause", "resume"}
OPERATION_ACTIONS = {"click", "input", "set-value", "invoke"}
OBSERVATION_ACTIONS = {"screenshot", "snapshot"}
PROFILING_ACTIONS = {"profile-start", "profile-stop"}
CONDITION_ACTIONS = {"wait-for", "assert"}
ALL_ACTIONS = (
    CONTROL_ACTIONS | OPERATION_ACTIONS | OBSERVATION_ACTIONS | PROFILING_ACTIONS | CONDITION_ACTIONS
)

METRIC_AGGREGATES = ("avg", "max", "p95")

CONDITION_SOURCES = ("ui", "log", "gameplay", "metric")
COMPARE_OPS = ("equals", "notEquals", "greaterThan", "lessThan", "atLeast", "atMost")

DEFAULT_WAIT_TIMEOUT_SECONDS = 10.0
DEFAULT_SCREENSHOT_JOB_TIMEOUT_SECONDS = 10.0


class ScenarioValidationError(RuntimeError):
    """scenario 文件结构/字段非法。errors 里每条消息都带 step 索引前缀，方便定位。"""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors) or "invalid scenario")
        self.errors = errors


def load_scenario(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve()
    return json.loads(resolved.read_text(encoding="utf-8"))


def validate_scenario(scenario: Any) -> list[str]:
    """返回错误信息列表；空列表代表校验通过。不抛异常，方便 `scenario validate` 直接展示全部问题。"""
    errors: list[str] = []
    if not isinstance(scenario, dict):
        return ["scenario 必须是 JSON 对象"]

    if not scenario.get("name"):
        errors.append("缺少必填字段：name")

    defaults = scenario.get("defaults", {})
    if defaults is not None and not isinstance(defaults, dict):
        errors.append("defaults 必须是 JSON 对象")

    steps = scenario.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("steps 必须是非空数组")
        return errors

    seen_assert_ids: set[str] = set()
    for index, step in enumerate(steps):
        prefix = f"step[{index}]"
        if not isinstance(step, dict):
            errors.append(f"{prefix}: 必须是 JSON 对象")
            continue

        action = step.get("action")
        if action not in ALL_ACTIONS:
            errors.append(f"{prefix}: 不支持的 action '{action}'")
            continue

        if action == "open-scene" and not step.get("scene"):
            errors.append(f"{prefix}: open-scene 需要 scene 字段")
        elif action in {"click", "input", "set-value"} and not step.get("path"):
            errors.append(f"{prefix}: {action} 需要 path 字段")
        if action == "input" and "text" not in step:
            errors.append(f"{prefix}: input 需要 text 字段")
        if action == "set-value" and "value" not in step:
            errors.append(f"{prefix}: set-value 需要 value 字段")
        if action == "invoke" and not step.get("command"):
            errors.append(f"{prefix}: invoke 需要 command 字段")

        if action in CONDITION_ACTIONS:
            sources = [key for key in CONDITION_SOURCES if key in step]
            if len(sources) != 1:
                errors.append(
                    f"{prefix}: {action} 必须恰好指定一个 source（{'/'.join(CONDITION_SOURCES)}），"
                    f"当前给出 {len(sources)} 个"
                )
            else:
                errors.extend(_validate_condition(sources[0], step[sources[0]], prefix))

            if action == "assert":
                step_id = step.get("id")
                if step_id:
                    if step_id in seen_assert_ids:
                        errors.append(f"{prefix}: 重复的断言 id '{step_id}'")
                    seen_assert_ids.add(step_id)

            timeout_value = step.get("timeoutSeconds")
            if timeout_value is not None and not isinstance(timeout_value, (int, float)):
                errors.append(f"{prefix}: timeoutSeconds 必须是数字")

    return errors


def _validate_condition(source: str, condition: Any, prefix: str) -> list[str]:
    if not isinstance(condition, dict):
        return [f"{prefix}: {source} 条件必须是 JSON 对象"]

    errors: list[str] = []
    if source == "ui":
        if "path" not in condition and "find" not in condition:
            errors.append(f"{prefix}: ui 条件需要 path 或 find 之一")
        if "find" in condition and not isinstance(condition["find"], dict):
            errors.append(f"{prefix}: ui.find 必须是 JSON 对象")
    elif source == "gameplay":
        if not condition.get("command"):
            errors.append(f"{prefix}: gameplay 条件需要 command 字段")
        errors.extend(_validate_compare_ops(condition, prefix, "gameplay"))
    elif source == "metric":
        if not condition.get("name"):
            errors.append(f"{prefix}: metric 条件需要 name 字段")
        aggregate = condition.get("aggregate")
        if aggregate is not None and aggregate not in METRIC_AGGREGATES:
            errors.append(f"{prefix}: metric.aggregate 必须是 {'/'.join(METRIC_AGGREGATES)} 之一")
        errors.extend(_validate_compare_ops(condition, prefix, "metric"))
    # log 条件字段（type/messageContains/absent/sinceStep）均为可选组合，不做强校验。
    return errors


def _validate_compare_ops(condition: dict[str, Any], prefix: str, source: str) -> list[str]:
    present = [op for op in COMPARE_OPS if op in condition]
    if len(present) != 1:
        return [
            f"{prefix}: {source} 条件必须恰好指定一个比较符（{'/'.join(COMPARE_OPS)}），"
            f"当前给出 {len(present)} 个"
        ]
    return []


@dataclass
class ScenarioContext:
    """执行引擎的全部外部依赖，测试时用假 BridgeClient + tmp_path 构造。"""

    client: BridgeClient
    session_path: Path
    capture_config: dict[str, Any] = field(
        default_factory=lambda: {"onAssertFailure": True, "onScenarioStep": True}
    )
    default_wait_timeout: float = DEFAULT_WAIT_TIMEOUT_SECONDS
    poll_interval: float = 0.5
    timeout_scale: float = 1.0
    sleep_fn: Callable[[float], None] = time.sleep
    now_fn: Callable[[], float] = time.monotonic
    screenshot_target_directory: str | None = None


def run_scenario(scenario: dict[str, Any], ctx: ScenarioContext) -> dict[str, Any]:
    errors = validate_scenario(scenario)
    if errors:
        raise ScenarioValidationError(errors)

    defaults = scenario.get("defaults") or {}
    steps = scenario["steps"]

    results: list[dict[str, Any]] = []
    step_start_sequence_by_index: dict[int, int] = {}
    aborted = False
    entered_play = False

    for index, step in enumerate(steps):
        action = step["action"]

        if aborted:
            results.append(_skipped_result(index, step))
            continue

        step_start_sequence = _current_log_sequence(ctx.session_path)
        step_start_sequence_by_index[index] = step_start_sequence

        start = ctx.now_fn()
        try:
            status, failure_type, evidence, extra = _execute_step(
                ctx, step, defaults, step_start_sequence_by_index
            )
        except BridgeClientError as exc:
            status, failure_type, evidence, extra = (
                "failed",
                "execution_error",
                {"code": exc.code, "message": str(exc)},
                {},
            )
        except TimeoutError as exc:
            status, failure_type, evidence, extra = "failed", "timeout", {"message": str(exc)}, {}
        except Exception as exc:  # noqa: BLE001 - 未预期异常也要落成失败步骤，不能中断整个进程
            status, failure_type, evidence, extra = (
                "failed",
                "execution_error",
                {"message": str(exc)},
                {},
            )

        if action == "play" and status == "passed":
            entered_play = True
        if action == "stop" and status == "passed":
            entered_play = False

        duration_ms = max(int((ctx.now_fn() - start) * 1000), 0)
        step_result: dict[str, Any] = {
            "stepIndex": index,
            "action": action,
            "id": step.get("id") or f"step-{index}",
            "status": status,
            "failureType": failure_type,
            "durationMs": duration_ms,
            "evidence": evidence,
            "_extra": extra,
        }
        results.append(step_result)

        if status == "failed":
            if action == "assert" and ctx.capture_config.get("onAssertFailure", True):
                screenshot_path = _capture_screenshot(ctx, reason="assert_failure")
                if screenshot_path:
                    step_result["evidence"] = {**(evidence or {}), "screenshotPath": screenshot_path}
            if not step.get("continueOnFailure", False):
                aborted = True

    _teardown(ctx, entered_play, defaults)

    return _build_result(scenario, results)


def _teardown(ctx: ScenarioContext, entered_play: bool, defaults: dict[str, Any]) -> None:
    """无论成败必执行：若引擎发起过 play 且仍在 playing 则 stop。失败静默吞掉——
    收尾失败不应该掩盖 scenario 本身的执行结果。"""
    if not entered_play:
        return
    try:
        current = ctx.client.get_status()
        if current.get("editorState") in {"playing", "paused", "enteringPlay"}:
            ctx.client.post("stop")
            _wait_for_status(
                ctx,
                lambda s: s.get("editorState") == "idle",
                defaults.get("waitTimeoutSeconds", ctx.default_wait_timeout) * ctx.timeout_scale,
            )
    except (BridgeClientError, TimeoutError):
        pass


def _execute_step(
    ctx: ScenarioContext,
    step: dict[str, Any],
    defaults: dict[str, Any],
    step_start_sequence_by_index: dict[int, int],
) -> tuple[str, str | None, dict[str, Any] | None, dict[str, Any]]:
    action = step["action"]

    if action == "open-scene":
        response = ctx.client.open_scene(step["scene"])
        if not response.get("ok", True):
            return "failed", "execution_error", response, {}
        try:
            _wait_for_status(
                ctx, lambda s: s.get("activeScenePath") == step["scene"], _step_timeout(step, defaults, ctx)
            )
        except TimeoutError:
            return "failed", "timeout", {"message": "等待场景加载超时", "scene": step["scene"]}, {}
        return "passed", None, {"scenePath": step["scene"]}, {}

    if action == "play":
        response = ctx.client.post("play")
        if not response.get("ok", False) and response.get("code") != "already_playing":
            return "failed", "execution_error", response, {}
        try:
            _wait_for_status(ctx, lambda s: s.get("editorState") == "playing", _step_timeout(step, defaults, ctx))
        except TimeoutError:
            return "failed", "timeout", {"message": "等待进入 Play Mode 超时"}, {}
        return "passed", None, None, {}

    if action == "stop":
        response = ctx.client.post("stop")
        if not response.get("ok", False) and response.get("code") != "already_stopped":
            return "failed", "execution_error", response, {}
        try:
            _wait_for_status(ctx, lambda s: s.get("editorState") == "idle", _step_timeout(step, defaults, ctx))
        except TimeoutError:
            return "failed", "timeout", {"message": "等待退出 Play Mode 超时"}, {}
        return "passed", None, None, {}

    if action in {"pause", "resume"}:
        response = ctx.client.post(action)
        if not response.get("ok", False):
            return "failed", "execution_error", response, {}
        return "passed", None, None, {}

    if action == "click":
        response = ctx.client.interaction_click(
            path=step["path"], force=step.get("force", False), scene=step.get("scene")
        )
        return _passthrough_result(response)

    if action == "input":
        response = ctx.client.interaction_input(
            path=step["path"], text=step.get("text", ""), submit=step.get("submit", False), scene=step.get("scene")
        )
        return _passthrough_result(response)

    if action == "set-value":
        response = ctx.client.interaction_set_value(
            path=step["path"], value=step.get("value"), component=step.get("component"), scene=step.get("scene")
        )
        return _passthrough_result(response)

    if action == "invoke":
        response = ctx.client.gameplay_invoke(step["command"], step.get("args", {}))
        return _passthrough_result(response)

    if action == "profile-start":
        response = ctx.client.profiling_start(target_directory=ctx.screenshot_target_directory)
        return _passthrough_result(response)

    if action == "profile-stop":
        response = ctx.client.profiling_stop()
        return _passthrough_result(response)

    if action in {"screenshot", "snapshot"}:
        if not ctx.capture_config.get("onScenarioStep", True):
            return "passed", None, {"skipped": True, "reason": "capture.screenshot.onScenarioStep disabled"}, {}
        path = _capture_screenshot(ctx, reason="scenario")
        if path is None:
            return "failed", "execution_error", {"message": "截图失败或超时"}, {}
        return "passed", None, {"path": path}, {}

    if action in CONDITION_ACTIONS:
        source, condition = _extract_source(step)
        since_sequence = _resolve_since_sequence(condition, step_start_sequence_by_index)
        extra = {"source": source, "condition": condition}

        if action == "assert":
            ok, evidence = evaluate_condition(ctx, source, condition, since_sequence)
            return ("passed" if ok else "failed"), (None if ok else "assertion_failed"), evidence, extra

        timeout = _step_timeout(step, defaults, ctx)
        deadline = ctx.now_fn() + timeout
        evidence: dict[str, Any] | None = None
        while True:
            ok, evidence = evaluate_condition(ctx, source, condition, since_sequence)
            if ok:
                return "passed", None, evidence, extra
            if ctx.now_fn() >= deadline:
                return "failed", "timeout", evidence, extra
            ctx.sleep_fn(ctx.poll_interval)

    raise ValueError(f"unsupported action: {action}")


def _passthrough_result(response: dict[str, Any]) -> tuple[str, str | None, dict[str, Any], dict[str, Any]]:
    if not response.get("ok", True):
        return "failed", "execution_error", response, {}
    return "passed", None, response, {}


def _extract_source(step: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    for source in CONDITION_SOURCES:
        if source in step:
            return source, step[source]
    raise ValueError("assert/wait-for 步骤缺少 source（ui/log/gameplay/metric）")


def _step_timeout(step: dict[str, Any], defaults: dict[str, Any], ctx: ScenarioContext) -> float:
    seconds = step.get("timeoutSeconds", defaults.get("waitTimeoutSeconds", ctx.default_wait_timeout))
    return float(seconds) * ctx.timeout_scale


def _resolve_since_sequence(condition: dict[str, Any], step_start_sequence_by_index: dict[int, int]) -> int:
    since_step = condition.get("sinceStep")
    if since_step is None:
        return 0
    return step_start_sequence_by_index.get(since_step, 0)


def _wait_for_status(ctx: ScenarioContext, predicate: Callable[[dict[str, Any]], bool], timeout: float) -> dict[str, Any]:
    deadline = ctx.now_fn() + timeout
    while True:
        status = ctx.client.get_status()
        if predicate(status):
            return status
        if ctx.now_fn() >= deadline:
            raise TimeoutError("等待状态收敛超时")
        ctx.sleep_fn(ctx.poll_interval)


def _capture_screenshot(ctx: ScenarioContext, reason: str) -> str | None:
    try:
        start_response = ctx.client.capture_screenshot(reason=reason, target_directory=ctx.screenshot_target_directory)
    except BridgeClientError:
        return None
    if not start_response.get("ok", False):
        return None
    job_id = start_response.get("jobId")
    if not job_id:
        return None

    deadline = ctx.now_fn() + DEFAULT_SCREENSHOT_JOB_TIMEOUT_SECONDS * ctx.timeout_scale
    while True:
        try:
            response = ctx.client.get_job(job_id)
        except BridgeClientError:
            return None
        job = response.get("job", {})
        status = job.get("status")
        if status == "succeeded":
            return (job.get("result") or {}).get("path")
        if status == "failed":
            return None
        if ctx.now_fn() >= deadline:
            return None
        ctx.sleep_fn(ctx.poll_interval)


def evaluate_condition(
    ctx: ScenarioContext, source: str, condition: dict[str, Any], since_sequence: int
) -> tuple[bool, dict[str, Any]]:
    if source == "ui":
        return _evaluate_ui_condition(ctx.client, condition)
    if source == "log":
        return _evaluate_log_condition(ctx.session_path, condition, since_sequence)
    if source == "gameplay":
        return _evaluate_gameplay_condition(ctx.client, condition)
    if source == "metric":
        return _evaluate_metric_condition(ctx, condition)
    raise ValueError(f"unknown assert/wait-for source: {source}")


def _evaluate_ui_condition(client: BridgeClient, condition: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    if "path" in condition:
        params: dict[str, Any] = {"path": condition["path"]}
        if condition.get("scene"):
            params["scene"] = condition["scene"]
        try:
            response = client.hierarchy_inspect(**params)
        except BridgeClientError as exc:
            if exc.code == "node_not_found":
                return _check_ui_node_conditions(None, condition)
            return False, {"dataSource": "hierarchy/inspect", "error": exc.code, "message": str(exc)}
        return _check_ui_node_conditions(response.get("node"), condition)

    if "find" in condition:
        find_params = dict(condition["find"])
        try:
            response = client.hierarchy_find(**find_params)
        except BridgeClientError as exc:
            return False, {"dataSource": "hierarchy/find", "error": exc.code, "message": str(exc)}
        nodes = response.get("nodes", [])
        matched_count = response.get("matchedCount", len(nodes))
        return _check_ui_count_conditions(matched_count, condition)

    return False, {"error": "ui 条件需要 path 或 find 之一"}


def _check_ui_node_conditions(node: dict[str, Any] | None, condition: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    exists = node is not None
    checks: list[dict[str, Any]] = []
    ok = True

    def add(field_name: str, expected: Any, actual: Any) -> None:
        nonlocal ok
        ok = ok and (expected == actual)
        checks.append({"field": field_name, "expected": expected, "actual": actual})

    if "exists" in condition:
        add("exists", condition["exists"], exists)

    if not exists:
        for field_name in ("activeInHierarchy", "interactable", "textEquals", "textContains"):
            if field_name in condition:
                add(field_name, condition[field_name], None)
        return ok, {"dataSource": "hierarchy/inspect", "checks": checks, "node": None}

    if "activeInHierarchy" in condition:
        add("activeInHierarchy", condition["activeInHierarchy"], node.get("activeInHierarchy"))
    if "interactable" in condition:
        actual_interactable = node.get("effectiveInteractable", node.get("interactable"))
        add("interactable", condition["interactable"], actual_interactable)
    if "textEquals" in condition:
        add("textEquals", condition["textEquals"], node.get("text"))
    if "textContains" in condition:
        actual_text = node.get("text") or ""
        passed = condition["textContains"] in actual_text
        ok = ok and passed
        checks.append({"field": "textContains", "expected": condition["textContains"], "actual": actual_text})

    return ok, {
        "dataSource": "hierarchy/inspect",
        "checks": checks,
        "node": {"path": node.get("path"), "scene": node.get("scene")},
    }


def _check_ui_count_conditions(matched_count: int, condition: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    ok = True

    def add(field_name: str, expected: Any, actual: Any, passed: bool) -> None:
        nonlocal ok
        ok = ok and passed
        checks.append({"field": field_name, "expected": expected, "actual": actual})

    if "countEquals" in condition:
        add("countEquals", condition["countEquals"], matched_count, matched_count == condition["countEquals"])
    if "countAtLeast" in condition:
        add("countAtLeast", condition["countAtLeast"], matched_count, matched_count >= condition["countAtLeast"])
    if "countAtMost" in condition:
        add("countAtMost", condition["countAtMost"], matched_count, matched_count <= condition["countAtMost"])

    return ok, {"dataSource": "hierarchy/find", "checks": checks, "matchedCount": matched_count}


def _evaluate_log_condition(
    session_path: Path, condition: dict[str, Any], since_sequence: int
) -> tuple[bool, dict[str, Any]]:
    rows = read_jsonl(session_path / "unity-console.jsonl")
    expected_type = condition.get("type")
    message_contains = condition.get("messageContains")

    matched = [
        row
        for row in rows
        if row.get("sequence", 0) > since_sequence
        and (not expected_type or row.get("type") == expected_type)
        and (not message_contains or message_contains in str(row.get("message", "")))
    ]

    absent = bool(condition.get("absent", False))
    ok = (len(matched) == 0) if absent else (len(matched) > 0)
    evidence = {
        "dataSource": "unity-console.jsonl",
        "sinceSequence": since_sequence,
        "matchedCount": len(matched),
        "matchedSequences": [row.get("sequence") for row in matched[:5]],
    }
    return ok, evidence


def _evaluate_gameplay_condition(client: BridgeClient, condition: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    command = condition["command"]
    args = condition.get("args", {})
    try:
        response = client.gameplay_invoke(command, args)
    except BridgeClientError as exc:
        return False, {"dataSource": "gameplay/invoke", "command": command, "error": exc.code, "message": str(exc)}

    if not response.get("ok", True):
        return False, {
            "dataSource": "gameplay/invoke",
            "command": command,
            "error": response.get("code"),
            "message": response.get("message"),
        }

    actual = response.get("result")
    ok, expected = _apply_compare(condition, actual)
    return ok, {"dataSource": "gameplay/invoke", "command": command, "expected": expected, "actual": actual}


def _evaluate_metric_condition(ctx: ScenarioContext, condition: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """从当前 session artifacts/metrics.jsonl 读回采样，计算 avg/max/p95 后与 condition 比较。

    metrics.jsonl 由 profile-start/profile-stop 步骤产出（同 screenshot 一样写到
    session 的 artifacts 目录）；文件不存在或该指标没有任何样本（可能计数器在本机/
    渲染管线下不可用）都判 metric_not_available，不静默当成 0。
    """
    metric_name = condition["name"]
    aggregate = condition.get("aggregate", "avg")
    metrics_path = ctx.session_path / "artifacts" / "metrics.jsonl"

    if not metrics_path.exists():
        return False, {
            "dataSource": "metrics.jsonl",
            "error": "metric_not_available",
            "message": f"未找到 {metrics_path}；metric 断言依赖 profile-start/profile-stop 先产出采样数据",
        }

    values = [
        float(row[metric_name])
        for row in read_jsonl(metrics_path)
        if isinstance(row.get(metric_name), (int, float))
    ]
    if not values:
        return False, {
            "dataSource": "metrics.jsonl",
            "error": "metric_not_available",
            "message": f"metrics.jsonl 中没有指标 '{metric_name}' 的样本（可能该计数器在本机/渲染管线下不可用）",
        }

    actual = _aggregate_metric(values, aggregate)
    ok, expected = _apply_compare(condition, actual)
    return ok, {
        "dataSource": "metrics.jsonl",
        "metric": metric_name,
        "aggregate": aggregate,
        "sampleCount": len(values),
        "expected": expected,
        "actual": actual,
    }


def _aggregate_metric(values: list[float], aggregate: str) -> float:
    if aggregate == "max":
        return max(values)
    if aggregate == "p95":
        return _percentile(values, 0.95)
    return sum(values) / len(values)


def _percentile(values: list[float], fraction: float) -> float:
    sorted_values = sorted(values)
    index = math.ceil(fraction * len(sorted_values)) - 1
    index = max(0, min(len(sorted_values) - 1, index))
    return sorted_values[index]


def _apply_compare(condition: dict[str, Any], actual: Any) -> tuple[bool, Any]:
    for op in COMPARE_OPS:
        if op not in condition:
            continue
        expected = condition[op]
        if op == "equals":
            return actual == expected, expected
        if op == "notEquals":
            return actual != expected, expected
        if actual is None:
            return False, expected
        if op == "greaterThan":
            return actual > expected, expected
        if op == "lessThan":
            return actual < expected, expected
        if op == "atLeast":
            return actual >= expected, expected
        if op == "atMost":
            return actual <= expected, expected
    return False, None


def _skipped_result(index: int, step: dict[str, Any]) -> dict[str, Any]:
    return {
        "stepIndex": index,
        "action": step.get("action"),
        "id": step.get("id") or f"step-{index}",
        "status": "skipped",
        "failureType": None,
        "durationMs": 0,
        "evidence": None,
        "_extra": {},
    }


def _current_log_sequence(session_path: Path) -> int:
    rows = read_jsonl(session_path / "unity-console.jsonl")
    if not rows:
        return 0
    return max((row.get("sequence", 0) for row in rows), default=0)


def _assertion_summary(
    step_id: str, status: str, source: str | None, condition: dict[str, Any] | None, evidence: dict[str, Any] | None
) -> dict[str, Any]:
    expected: Any = None
    actual: Any = None
    if source == "ui":
        checks = (evidence or {}).get("checks", [])
        expected = {check["field"]: check["expected"] for check in checks}
        actual = {check["field"]: check["actual"] for check in checks}
    elif source == "gameplay":
        expected = (evidence or {}).get("expected")
        actual = (evidence or {}).get("actual")
    elif source == "log":
        expected = condition
        actual = {"matchedCount": (evidence or {}).get("matchedCount")}
    elif source == "metric":
        expected = (evidence or {}).get("expected")
        actual = (evidence or {}).get("actual")
    return {"id": step_id, "status": status, "expected": expected, "actual": actual, "evidence": evidence}


def _build_result(scenario: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    steps_total = len(results)
    steps_passed = sum(1 for r in results if r["status"] == "passed")
    steps_failed = sum(1 for r in results if r["status"] == "failed")
    steps_skipped = sum(1 for r in results if r["status"] == "skipped")

    assertions = []
    public_steps = []
    for result in results:
        extra = result.pop("_extra", {})
        public_steps.append(result)
        if result["action"] == "assert":
            assertions.append(
                _assertion_summary(
                    result["id"], result["status"], extra.get("source"), extra.get("condition"), result["evidence"]
                )
            )

    return {
        "name": scenario.get("name"),
        "description": scenario.get("description", ""),
        "status": "passed" if steps_failed == 0 else "failed",
        "stepsTotal": steps_total,
        "stepsPassed": steps_passed,
        "stepsFailed": steps_failed,
        "stepsSkipped": steps_skipped,
        "steps": public_steps,
        "assertions": assertions,
    }


def convert_recording_to_scenario(
    actions_path: str | Path, meta_path: str | Path | None = None, name: str | None = None
) -> dict[str, Any]:
    """把 record 产出的 actions.jsonl（+ 同目录 recording-meta.json）转成 scenario 草稿。

    只做动作 → 步骤的机械转换（保留 scene/path，附 recordedGap 注释字段，不自动插 wait），
    产出草稿不含任何断言——回放的价值由 agent 事后补 wait-for/assert 赋予。
    """
    actions_file = Path(actions_path).expanduser().resolve()
    resolved_meta_path = (
        Path(meta_path).expanduser().resolve() if meta_path is not None else actions_file.parent / "recording-meta.json"
    )
    if not resolved_meta_path.exists():
        raise ScenarioValidationError(
            [f"缺少 recording-meta.json：{resolved_meta_path}（无法倒推场景信息，不做假设，请确认录制目录完整）"]
        )

    meta = json.loads(resolved_meta_path.read_text(encoding="utf-8"))
    actions = read_jsonl(actions_file)

    steps: list[dict[str, Any]] = [
        {"action": "open-scene", "scene": meta.get("activeScene", "")},
        {"action": "play"},
    ]

    previous_time = 0.0
    for action in actions:
        current_time = action.get("time", previous_time)
        gap = round(current_time - previous_time, 3)
        previous_time = current_time

        if action.get("type") == "click":
            steps.append(
                {
                    "action": "click",
                    "path": action.get("path"),
                    "scene": action.get("scene"),
                    "recordedGap": gap,
                }
            )
        elif action.get("type") == "input":
            steps.append(
                {
                    "action": "input",
                    "path": action.get("path"),
                    "text": action.get("text", ""),
                    "scene": action.get("scene"),
                    "recordedGap": gap,
                }
            )

    steps.append({"action": "stop"})

    scenario_name = name or f"recording-{meta.get('sessionId') or 'draft'}"
    return {
        "$schema": ".unity-agent/schemas/scenario.schema.json",
        "name": scenario_name,
        "description": "从录制自动生成的草稿，不含断言；请在关键节点补充 wait-for 与 assert。",
        "defaults": {"waitTimeoutSeconds": DEFAULT_WAIT_TIMEOUT_SECONDS},
        "steps": steps,
    }
