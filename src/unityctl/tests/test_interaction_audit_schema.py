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
    if action != "click" and {
        "clicked",
        "raycastHit",
        "events",
        "forced",
        "blockedBy",
    } & record.keys():
        errors.append("click-only result field")
    if record.get("code") == "occluded" and not record.get("blockedBy"):
        errors.append("occluded requires blockedBy")
    if record.get("code") != "occluded" and "blockedBy" in record:
        errors.append("blockedBy only allowed for occluded")
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


def test_interaction_audit_schema_is_distributed_byte_for_byte():
    root_schema, bundled_schema = _schema_paths()

    assert root_schema.read_bytes() == bundled_schema.read_bytes()


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
                request={"path": "Canvas/InputField", "textLength": 11, "submit": True},
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
        None,
        {"time": "2026-07-15T15:14:00Z"},
        {**_base_record(), "extra": True},
        {**_base_record(), "ok": "yes"},
        {**_base_record(), "request": "bad"},
        {**_base_record(), "request": {"path": "Canvas/Button", "force": False, "text": "bad"}},
        {
            **_base_record(action="input", request={"textLength": 2}),
            "ok": False,
            "code": "invalid_argument",
        },
        {
            **_base_record(
                action="set-value",
                request={"path": "Canvas/Slider", "valueKind": "number", "value": "0.75"},
            ),
            "ok": True,
            "code": "ok",
        },
    ],
)
def test_validate_record_rejects_contract_errors(record: object):
    assert validate_record(record)
