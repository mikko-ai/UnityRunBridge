"""Read-only analysis for archived Unity builds.

Log grammar adapted from awesome-gamedev-agent-skills (Apache-2.0), c6ca6c4,
skills/unity/unity-build-size/scripts/build_report.py. See licenses/ for attribution.
"""

import heapq
import json
import os
import re
import stat
from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path
from typing import Any

_SCALES = {"b": 1, "kb": 2**10, "mb": 2**20, "gb": 2**30, "tb": 2**40}
_NUMBER = r"[0-9]{1,16}(?:\.[0-9]{1,8})?"
_SIZE = rf"({_NUMBER})\s+({'|'.join(_SCALES)})"
_PERCENT = rf"({_NUMBER})%"
_CATEGORY = re.compile(rf"^(\S.*?)\s+{_SIZE}\s+{_PERCENT}$", re.I)
_COMPLETE = re.compile(rf"^Complete build size\s+{_SIZE}$", re.I)
_ASSET = re.compile(rf"^{_SIZE}\s+{_PERCENT}\s+(\S.*)$", re.I)
_END = re.compile(r"^-{20,}$")
_MAX_BUILD_SUMMARY_BYTES = 16 * 1024 * 1024


def _size(amount: str, unit: str) -> int:
    return round(Decimal(amount) * _SCALES[unit.lower()])


def parse_build_log(lines: Iterable[str], top: int) -> dict[str, Any] | None:
    """Parse the newest block only; a truncated rebuild must not borrow an older total."""
    if not 1 <= top <= 1000:
        raise ValueError("top 必须在 1 至 1000 之间")
    report = None
    assets: list[tuple[int, int, dict[str, Any]]] = []
    phase = "outside"
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if line == "Build Report":
            report = {
                "startLine": number, "complete": False, "totalBytes": None,
                "userAssetsBytes": None, "categories": [], "assetCount": 0,
            }
            assets = []
            phase = "categories"
        elif phase == "outside":
            continue
        elif _END.fullmatch(line):
            if report["totalBytes"] is not None or report["categories"] or phase == "assets":
                report["complete"] = report["totalBytes"] is not None
                phase = "outside"
        elif line.startswith("Information on used Assets is not available"):
            report["reason"] = "player_data_not_rebuilt"
        elif line.startswith("Used Assets and files"):
            phase = "assets"
        elif phase == "categories":
            if match := _COMPLETE.fullmatch(line):
                report["totalBytes"] = _size(*match.groups())
            elif match := _CATEGORY.fullmatch(line):
                name, amount, unit, percent = match.groups()
                size = _size(amount, unit)
                if name == "Complete size":
                    report["totalBytes"] = size
                elif name == "Total User Assets":
                    report["userAssetsBytes"] = size
                elif len(report["categories"]) < 100:
                    report["categories"].append({"name": name, "bytes": size, "percent": float(percent)})
        elif match := _ASSET.fullmatch(line):
            amount, unit, percent, path = match.groups()
            size = _size(amount, unit)
            item = (size, -number, {"path": path, "bytes": size, "percent": float(percent)})
            if len(assets) < top:
                heapq.heappush(assets, item)
            elif item > assets[0]:
                heapq.heapreplace(assets, item)
            report["assetCount"] += 1
    if report is not None:
        report["topAssets"] = [item for _, _, item in sorted(assets, reverse=True)]
    return report


def _measure(path: Path) -> dict[str, Any]:
    def on_error(error: OSError) -> None:
        raise error

    try:
        kind = path.lstat()
        if stat.S_ISREG(kind.st_mode):
            return {"path": str(path), "status": "measured", "kind": "file", "bytes": kind.st_size}
        if not stat.S_ISDIR(kind.st_mode):
            raise OSError(f"不是普通文件或目录：{path}")
        total = 0
        count = 0
        for folder, dirs, files in os.walk(path, onerror=on_error, followlinks=False):
            for name in dirs:
                if not stat.S_ISDIR((Path(folder) / name).lstat().st_mode):
                    raise OSError(f"目录包含符号链接或发生变化：{name}")
            for name in files:
                entry = (Path(folder) / name).lstat()
                if not stat.S_ISREG(entry.st_mode):
                    raise OSError(f"目录包含非普通文件：{name}")
                total += entry.st_size
                count += 1
        if not count:
            raise OSError("交付目录没有普通文件")
        return {"path": str(path), "status": "measured", "kind": "directory", "bytes": total, "fileCount": count}
    except OSError as exc:
        return {"path": str(path), "status": "unavailable", "bytes": None, "reason": str(exc)}


def _read_summary(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError("构建归档缺少 build-report.json")
    with path.open("rb") as handle:
        raw = handle.read(_MAX_BUILD_SUMMARY_BYTES + 1)
    if len(raw) > _MAX_BUILD_SUMMARY_BYTES:
        raise ValueError("build-report.json 超过读取上限")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or payload.get("result") not in ("Succeeded", "Failed", "Cancelled"):
        raise ValueError("build-report.json 缺少有效的构建结果")
    size = payload.get("sizeBytes")
    output = payload.get("outputPath")
    return {
        "path": str(path), "result": payload["result"],
        "sizeBytes": size if type(size) is int and size >= 0 else None,
        "outputPath": output if isinstance(output, str) and output and "\x00" not in output else None,
    }


def _archive_artifact(summary: dict[str, Any], build_dir: Path) -> Path | None:
    output = summary["outputPath"]
    if not output:
        return None
    candidate = build_dir / output
    if candidate == build_dir:
        return None
    # Copied archives may contain the old absolute path. Do not silently measure it.
    try:
        if not candidate.absolute().is_relative_to(build_dir.resolve()):
            return None
        if not candidate.resolve().is_relative_to(build_dir.resolve()):
            return None
    except (OSError, RuntimeError):
        return None
    return candidate


def analyze_build_size(
    *, build_dir: Path | None = None, log: Path | None = None, artifact: Path | None = None,
    report_budget_bytes: int | None = None, artifact_budget_bytes: int | None = None, top: int = 15,
) -> dict[str, Any]:
    """Keep the log estimate, BuildReport.summary, and measured delivery bytes distinct."""
    if build_dir is not None and log is not None:
        raise ValueError("--build-dir 与 --log 不可同时指定")
    notes = []
    explicit_log = log is not None
    explicit_artifact = artifact is not None
    summary = None
    archive_ok = build_dir is None
    if build_dir is not None:
        build_dir = build_dir.resolve()
        log = build_dir / "build.log"
        try:
            summary = _read_summary(build_dir / "build-report.json")
            archive_ok = summary["result"] == "Succeeded"
            if not archive_ok:
                notes.append("归档构建未成功，不用历史产物或部分日志通过预算")
            if artifact is None and archive_ok:
                artifact = _archive_artifact(summary, build_dir)
                if artifact is None:
                    notes.append("归档不含可定位的交付产物；移动归档或自定义输出请明确指定 --artifact")
        except (ValueError, OSError, RecursionError) as exc:
            notes.append(str(exc))

    parsed = None
    if log is not None:
        try:
            if not log.is_file():
                raise OSError(f"构建日志不是可读的普通文件：{log}")
            with log.open("r", encoding="utf-8-sig", errors="replace") as handle:
                parsed = parse_build_log(handle, top)
            if not parsed or not parsed["complete"]:
                if parsed and parsed.get("reason") == "player_data_not_rebuilt":
                    notes.append("增量构建未重建 Player 数据；需要资源明细时可执行 unityctl build --clean")
                else:
                    notes.append("最新构建日志块缺失、未结束或无完整总量")
        except OSError as exc:
            notes.append(str(exc))

    measured = _measure(artifact) if artifact is not None else None
    if measured is not None and measured["status"] != "measured":
        notes.append("未能计量交付产物：" + measured["reason"])
    report_value = parsed["totalBytes"] if archive_ok and parsed and parsed["complete"] else None
    artifact_value = measured["bytes"] if archive_ok and measured else None
    budgets = {}
    for name, limit, actual in (
        ("report", report_budget_bytes, report_value), ("artifact", artifact_budget_bytes, artifact_value),
    ):
        if limit is not None:
            budgets[name] = {
                "limitBytes": limit, "measuredBytes": actual,
                "status": "unverified" if actual is None else "exceeded" if actual > limit else "passed",
            }
    valid_evidence = archive_ok and (
        (log is not None and bool(parsed and parsed["complete"]))
        or (measured is not None and measured["status"] == "measured")
        or (log is None and artifact is None)
    )
    if (explicit_log and report_value is None) or (explicit_artifact and artifact_value is None):
        valid_evidence = False
    ok = valid_evidence and all(item["status"] == "passed" for item in budgets.values())
    code = "ok" if ok else (
        "build_size_budget_exceeded" if any(item["status"] == "exceeded" for item in budgets.values())
        else "build_size_unverified"
    )
    return {
        "ok": ok, "code": code, "notes": notes, "buildSummary": summary, "logReport": parsed,
        "logPath": str(log) if log is not None else None, "artifact": measured, "budgets": budgets,
    }
