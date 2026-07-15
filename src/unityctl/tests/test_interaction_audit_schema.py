from __future__ import annotations

import json
from pathlib import Path

import pytest


COMMON_REQUIRED = {
    "time",
    "action",
    "ok",
    "code",
    "request",
    "durationMs",
    "playModeFrame",
    "activeScenePath",
}
TOP_LEVEL_KEYS = COMMON_REQUIRED | {
    "scene",
    "message",
    "clicked",
    "raycastHit",
    "events",
    "forced",
    "blockedBy",
    "component",
}


def validate_record(record: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(record, dict):
        return ["record must be object"]
    missing = COMMON_REQUIRED - record.keys()
    if missing:
        errors.append(f"missing: {sorted(missing)}")
    if set(record) - TOP_LEVEL_KEYS:
        errors.append("unexpected top-level key")
    if not isinstance(record.get("ok"), bool):
        errors.append("ok must be boolean")
    if record.get("ok") is True and record.get("code") != "ok":
        errors.append("successful record must use code ok")
    if record.get("ok") is False and record.get("code") == "ok":
        errors.append("failed record cannot use code ok")
    if (
        not isinstance(record.get("durationMs"), int)
        or isinstance(record.get("durationMs"), bool)
        or record.get("durationMs", -1) < 0
    ):
        errors.append("durationMs must be non-negative integer")
    if (
        not isinstance(record.get("playModeFrame"), int)
        or isinstance(record.get("playModeFrame"), bool)
        or record.get("playModeFrame", -2) < -1
    ):
        errors.append("playModeFrame must be integer >= -1")
    if not isinstance(record.get("activeScenePath"), str):
        errors.append("activeScenePath must be string")
    action = record.get("action")
    if action not in {"click", "input", "set-value"}:
        errors.append("invalid action")
        return errors
    request = record.get("request")
    if not isinstance(request, dict):
        errors.append("request must be object")
        return errors

    allowed_request_keys = {
        "click": {"path", "force"},
        "input": {"path", "textLength", "submit"},
        "set-value": {"path", "component", "valueKind", "value", "valueLength"},
    }[action]
    if set(request) - allowed_request_keys:
        errors.append("unexpected request key")
    if record.get("code") != "invalid_argument" and not request.get("path"):
        errors.append("path required")
    if action == "click" and not isinstance(request.get("force"), bool):
        errors.append("force required")
    if action == "input" and not isinstance(request.get("submit"), bool):
        errors.append("submit required")
    if action == "input" and "text" in request:
        errors.append("text forbidden")
    if action == "click" and record.get("ok") is True:
        if not {"clicked", "raycastHit", "events", "forced"} <= record.keys():
            errors.append("click success fields required")
    if action == "click" and record.get("ok") is not True and {
        "clicked",
        "raycastHit",
        "events",
        "forced",
    } & record.keys():
        errors.append("click failure cannot contain success fields")
    if action != "click" and {
        "clicked",
        "raycastHit",
        "events",
        "forced",
        "blockedBy",
    } & record.keys():
        errors.append("click-only result field")
    if record.get("code") == "occluded" and (
        action != "click" or not record.get("blockedBy")
    ):
        errors.append("occluded requires click action and blockedBy")
    if "blockedBy" in record and (
        action != "click" or record.get("code") != "occluded"
    ):
        errors.append("blockedBy only allowed for occluded click")
    if action == "set-value" and record.get("ok") is True:
        if not record.get("component"):
            errors.append("set-value success requires component")
    elif "component" in record:
        errors.append("top-level component only allowed for set-value success")

    if action == "set-value":
        kind = request.get("valueKind")
        value_present = "value" in request
        if kind not in {"number", "boolean", "object", "string", "unknown", "invalid"}:
            errors.append("invalid valueKind")
        if kind in {"number", "boolean", "object"} and not value_present:
            errors.append("value required for typed kind")
        if kind in {"string", "unknown", "invalid"} and value_present:
            errors.append("value forbidden for redacted kind")
        if kind == "number" and (
            isinstance(request.get("value"), bool)
            or not isinstance(request.get("value"), (int, float))
        ):
            errors.append("number value required")
        if kind == "boolean" and not isinstance(request.get("value"), bool):
            errors.append("boolean value required")
        if kind == "object":
            value = request.get("value")
            if (
                not isinstance(value, dict)
                or set(value) != {"x", "y"}
                or any(
                    isinstance(item, bool) or not isinstance(item, (int, float))
                    for item in value.values()
                )
            ):
                errors.append("numeric x/y object required")
    return errors


def _schema_paths() -> tuple[Path, Path]:
    repo_root = Path(__file__).resolve().parents[3]
    root_schema = repo_root / "schemas" / "interaction-actions.schema.json"
    bundled_schema = (
        Path(__file__).resolve().parents[1]
        / "unityctl"
        / "schemas"
        / "interaction-actions.schema.json"
    )
    return root_schema, bundled_schema


def _base_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "time": "2026-07-15T15:14:00Z",
        "action": "click",
        "ok": True,
        "code": "ok",
        "request": {"path": "Canvas/Button", "force": False},
        "durationMs": 12,
        "playModeFrame": 120,
        "activeScenePath": "Assets/Scenes/Main.unity",
    }
    record.update(overrides)
    return record


def _load_root_schema() -> dict[str, object]:
    root_schema, _ = _schema_paths()
    return json.loads(root_schema.read_text(encoding="utf-8"))


def _action_request_branch(
    schema: dict[str, object], action: str
) -> dict[str, object]:
    for branch in schema["allOf"]:
        condition = branch.get("if", {})
        if condition.get("properties", {}).get("action") == {"const": action}:
            request = branch.get("then", {}).get("properties", {}).get("request")
            if request is not None:
                return branch
    raise AssertionError(f"missing request branch for action: {action}")


def test_interaction_audit_schema_is_distributed_byte_for_byte():
    root_schema, bundled_schema = _schema_paths()

    assert root_schema.read_bytes() == bundled_schema.read_bytes()


def test_interaction_audit_schema_contains_all_contract_conditions():
    schema = _load_root_schema()

    expected_requests = {
        "click": {
            "required": {"force"},
            "properties": {"path", "force"},
            "property_schemas": {"force": {"type": "boolean"}},
        },
        "input": {
            "required": {"submit"},
            "properties": {"path", "textLength", "submit"},
            "property_schemas": {
                "textLength": {"type": "integer", "minimum": 0},
                "submit": {"type": "boolean"},
            },
        },
        "set-value": {
            "required": {"valueKind"},
            "properties": {
                "path",
                "component",
                "valueKind",
                "value",
                "valueLength",
            },
            "property_schemas": {
                "valueLength": {"type": "integer", "minimum": 0},
            },
        },
    }
    action_branches = {
        action: _action_request_branch(schema, action)
        for action in expected_requests
    }
    for action, expected in expected_requests.items():
        request = action_branches[action]["then"]["properties"]["request"]
        assert request["type"] == "object"
        assert request["additionalProperties"] is False
        assert set(request["required"]) == expected["required"]
        assert set(request["properties"]) == expected["properties"]
        for property_name, property_schema in expected["property_schemas"].items():
            assert request["properties"][property_name] == property_schema

    all_of = schema["allOf"]
    path_branch = next(
        branch
        for branch in all_of
        if branch.get("if", {}).get("properties", {}).get("code")
        == {"not": {"const": "invalid_argument"}}
    )
    path_request = path_branch["then"]["properties"]["request"]
    assert path_request["required"] == ["path"]
    assert path_request["properties"]["path"] == {
        "type": "string",
        "minLength": 1,
    }

    success_branch = next(
        branch
        for branch in all_of
        if branch.get("if", {}).get("properties", {}).get("ok") == {"const": True}
    )
    assert success_branch["then"]["properties"]["code"] == {"const": "ok"}
    assert success_branch["then"]["not"] == {"required": ["message"]}

    click_result_branch = next(
        branch
        for branch in all_of
        if branch.get("if", {}).get("properties")
        == {"action": {"const": "click"}, "ok": {"const": True}}
    )
    assert set(click_result_branch["if"]["required"]) == {"action", "ok"}
    assert set(click_result_branch["then"]["required"]) == {
        "clicked",
        "raycastHit",
        "events",
        "forced",
    }
    click_failure_branch = click_result_branch["else"]
    assert click_failure_branch["if"]["properties"] == {
        "action": {"const": "click"}
    }
    assert click_failure_branch["if"]["required"] == ["action"]
    assert click_failure_branch["then"]["not"] == {
        "anyOf": [
            {"required": ["clicked"]},
            {"required": ["raycastHit"]},
            {"required": ["events"]},
            {"required": ["forced"]},
        ]
    }

    occluded_branch = next(
        branch
        for branch in all_of
        if branch.get("if", {}).get("properties", {}).get("code")
        == {"const": "occluded"}
    )
    assert occluded_branch["if"]["required"] == ["code"]
    assert occluded_branch["then"]["required"] == ["blockedBy"]
    assert occluded_branch["then"]["properties"]["action"] == {"const": "click"}
    assert occluded_branch["else"]["not"] == {"required": ["blockedBy"]}

    set_value_then = action_branches["set-value"]["then"]
    value_kind_conditions = set_value_then["allOf"]
    typed_kinds = {
        condition["if"]["properties"]["request"]["properties"]["valueKind"].get(
            "const"
        ): condition
        for condition in value_kind_conditions
        if "const"
        in condition["if"]["properties"]["request"]["properties"]["valueKind"]
    }
    assert set(typed_kinds) == {"number", "boolean", "object"}
    for kind, value_type in {
        "number": "number",
        "boolean": "boolean",
        "object": "object",
    }.items():
        request = typed_kinds[kind]["then"]["properties"]["request"]
        assert request["required"] == ["value"]
        assert request["properties"]["value"]["type"] == value_type
    object_value = typed_kinds["object"]["then"]["properties"]["request"][
        "properties"
    ]["value"]
    assert object_value["additionalProperties"] is False
    assert set(object_value["required"]) == {"x", "y"}
    assert object_value["properties"] == {
        "x": {"type": "number"},
        "y": {"type": "number"},
    }
    redacted_condition = next(
        condition
        for condition in value_kind_conditions
        if condition["if"]["properties"]["request"]["properties"]["valueKind"].get(
            "enum"
        )
    )
    assert set(
        redacted_condition["if"]["properties"]["request"]["properties"]["valueKind"][
            "enum"
        ]
    ) == {"string", "unknown", "invalid"}
    assert redacted_condition["then"]["properties"]["request"]["not"] == {
        "required": ["value"]
    }

    component_branch = next(
        branch
        for branch in all_of
        if branch.get("if", {}).get("properties")
        == {"action": {"const": "set-value"}, "ok": {"const": True}}
    )
    assert set(component_branch["if"]["required"]) == {"action", "ok"}
    assert component_branch["then"]["required"] == ["component"]
    assert component_branch["else"]["not"] == {"required": ["component"]}


def test_validate_record_accepts_expected_success_cases():
    positive_cases = [
        _base_record(
            clicked="Canvas/Button",
            raycastHit="Canvas/Button",
            events=["pointerDown", "pointerUp"],
            forced=False,
        ),
        _base_record(
            ok=False,
            code="occluded",
            blockedBy="OverlayPanel",
        ),
        {
            **_base_record(
                action="input",
                request={"textLength": 11, "submit": True},
            ),
            "ok": False,
            "code": "invalid_argument",
        },
        {
            **_base_record(
                action="input",
                request={"path": "Canvas/InputField", "textLength": 8, "submit": False},
            ),
            "ok": True,
        },
        {
            **_base_record(
                action="set-value",
                request={
                    "path": "Canvas/Slider",
                    "component": "Slider",
                    "valueKind": "number",
                    "value": 0.75,
                },
            ),
            "component": "Slider",
        },
    ]

    for record in positive_cases:
        assert validate_record(record) == []


@pytest.mark.parametrize(
    "record",
    [
        pytest.param(
            {key: value for key, value in _base_record().items() if key != "time"},
            id="missing-common-field",
        ),
        pytest.param(
            _base_record(action="drag"),
            id="invalid-action",
        ),
        pytest.param(
            _base_record(request={"force": False}),
            id="ok-true-missing-path",
        ),
        pytest.param(
            _base_record(
                ok=False,
                code="occluded",
                request={"force": False},
                blockedBy="Overlay",
            ),
            id="occluded-missing-path",
        ),
        pytest.param(
            _base_record(
                ok=False,
                code="no_click_handler",
                request={"force": False},
            ),
            id="no-click-handler-missing-path",
        ),
        pytest.param(
            _base_record(ok=False, code="node_not_found", request={"force": False}),
            id="node-not-found-missing-path",
        ),
        pytest.param(
            _base_record(ok=False, code="not_interactable", request={"force": False}),
            id="not-interactable-missing-path",
        ),
        pytest.param(
            _base_record(
                action="input",
                request={
                    "path": "Canvas/Input",
                    "textLength": 6,
                    "submit": False,
                    "secret": "hidden",
                },
            ),
            id="request-extra-key",
        ),
        pytest.param(
            _base_record(
                action="input",
                request={
                    "path": "Canvas/Input",
                    "textLength": 6,
                    "submit": False,
                    "text": "secret",
                },
            ),
            id="input-text-forbidden",
        ),
        pytest.param(
            _base_record(
                action="set-value",
                request={"path": "Canvas/Label", "value": "secret"},
            ),
            id="set-value-string-missing-kind",
        ),
        pytest.param(
            _base_record(
                action="set-value",
                request={
                    "path": "Canvas/Label",
                    "valueKind": "number",
                    "value": "secret",
                },
            ),
            id="set-value-string-wrong-kind",
        ),
        pytest.param(
            _base_record(
                action="set-value",
                request={
                    "path": "Canvas/Label",
                    "valueKind": "string",
                    "value": "secret",
                },
            ),
            id="set-value-string-kind-with-value",
        ),
        pytest.param(
            _base_record(
                action="set-value",
                request={"path": "Canvas/Slider", "valueKind": "number"},
            ),
            id="typed-number-missing-value",
        ),
        pytest.param(
            _base_record(
                action="set-value",
                request={"path": "Canvas/Toggle", "valueKind": "boolean"},
            ),
            id="typed-boolean-missing-value",
        ),
        pytest.param(
            _base_record(
                action="set-value",
                request={"path": "Canvas/Position", "valueKind": "object"},
            ),
            id="typed-object-missing-value",
        ),
        pytest.param(
            _base_record(
                action="set-value",
                request={
                    "path": "Canvas/Position",
                    "valueKind": "object",
                    "value": {"payload": {"secret": "nested"}},
                },
            ),
            id="nested-object-masquerading-as-value",
        ),
        pytest.param(
            _base_record(
                action="set-value",
                request={
                    "path": "Canvas/Position",
                    "valueKind": "object",
                    "value": ["secret"],
                },
            ),
            id="array-masquerading-as-value",
        ),
        pytest.param(
            _base_record(
                action="input",
                ok=False,
                code="occluded",
                request={"path": "Canvas/Input", "textLength": 1, "submit": False},
                blockedBy="Overlay",
            ),
            id="blocked-by-on-non-click-occluded",
        ),
        pytest.param(
            _base_record(
                ok=False,
                code="node_not_found",
                blockedBy="Overlay",
            ),
            id="blocked-by-on-non-occluded-code",
        ),
        *[
            pytest.param(
                _base_record(
                    ok=False,
                    code="node_not_found",
                    **{field: value},
                ),
                id=f"failed-click-with-{field}",
            )
            for field, value in {
                "clicked": "Canvas/Button",
                "raycastHit": "Canvas/Button",
                "events": ["pointerClick"],
                "forced": False,
            }.items()
        ],
    ],
)
def test_validate_record_rejects_contract_errors(record: object):
    assert validate_record(record)
