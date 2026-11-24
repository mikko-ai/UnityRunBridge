"""Append-only live run events kept alongside scenario evidence."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVENT_FILE = "run-events.jsonl"


def frame_name(session_path: Path, evidence: dict[str, Any] | None) -> str | None:
    """Expose only PNG basenames directly inside this run's artifacts directory."""
    evidence = evidence or {}
    raw = evidence.get("screenshotPath") or evidence.get("path")
    if not isinstance(raw, str):
        return None
    frame = Path(raw)
    artifacts = session_path / "artifacts"
    if not frame.is_absolute() or frame.suffix.lower() != ".png" or frame.is_symlink() or artifacts.is_symlink():
        return None
    if frame.resolve().parent != artifacts.resolve() or not frame.is_file():
        return None
    return frame.name


def click_marker(point: Any, reference: Any) -> dict[str, float] | None:
    """Convert Unity bottom-left coordinates only when a matching frame exists."""
    if not isinstance(point, dict) or not isinstance(reference, dict):
        return None
    x, y, w, h = (point.get(key) for key in ("x", "y", "width", "height"))
    if not all(type(value) in {int, float} and abs(value) <= 2**31 for value in (x, y, w, h)):
        return None
    if w != reference.get("width") or h != reference.get("height") or not (
        w > 0 and h > 0 and 0 <= x <= w and 0 <= y <= h
    ):
        return None
    return {"x": x / w, "y": 1 - y / h}


class RunEvents:
    def __init__(self, session_path: Path):
        self.path = session_path / EVENT_FILE
        self.sequence = 0

    def emit(self, kind: str, fields: dict[str, Any]) -> None:
        """Close each append before control continues, so a viewer can observe active steps."""
        self.sequence += 1
        record = {
            **fields,
            "schemaVersion": 1,
            "sequence": self.sequence,
            "at": datetime.now(timezone.utc).isoformat(),
            "type": kind,
        }
        if kind == "run-started":
            record["runnerPid"] = os.getpid()
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
