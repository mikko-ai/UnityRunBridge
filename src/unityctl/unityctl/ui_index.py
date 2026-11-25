"""Project-local UGUI discovery cache; not a runtime locator or click authority."""

import argparse
import hashlib
import json
import re
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
MAX_ARTIFACT_BYTES = 256 * 1024 * 1024
MAX_PREFABS = 100_000
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
CONTROL_ID = re.compile(r"[0-9a-f]{64}\Z")
JOB_ID = re.compile(r"job-[0-9]{17}-[0-9a-f]{4}\Z")
FILE_ID = re.compile(r"-?[0-9]{1,19}\Z")
CACHE_SCHEMA = (
    """CREATE TABLE scopes(root TEXT PRIMARY KEY, revision INTEGER NOT NULL, synced_at TEXT NOT NULL)""",
    """CREATE TABLE prefabs(root TEXT NOT NULL, guid TEXT NOT NULL, path TEXT NOT NULL,
       fingerprint TEXT NOT NULL, PRIMARY KEY(root, guid),
       FOREIGN KEY(root) REFERENCES scopes(root) ON DELETE CASCADE)""",
    """CREATE TABLE controls(root TEXT NOT NULL, guid TEXT NOT NULL, id TEXT NOT NULL, name TEXT NOT NULL,
       component_type TEXT NOT NULL, search TEXT NOT NULL, data TEXT NOT NULL,
       PRIMARY KEY(root, id), FOREIGN KEY(root, guid) REFERENCES prefabs(root, guid) ON DELETE CASCADE)""",
    "CREATE INDEX controls_by_asset ON controls(root, guid)",
)
NOTES_SCHEMA = (
    """CREATE TABLE annotations(id TEXT PRIMARY KEY, alias TEXT NOT NULL, alias_key TEXT NOT NULL,
       purpose TEXT NOT NULL, origin TEXT NOT NULL, evidence TEXT NOT NULL, fingerprint TEXT NOT NULL,
       created_at TEXT NOT NULL)""",
    "CREATE INDEX annotations_by_alias ON annotations(alias_key)",
)


class UiIndexError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def add_parser(subparsers, add_project_option):
    parser = subparsers.add_parser("ui-index", help="同步和查询本地 UGUI Prefab 索引")
    add_project_option(parser)
    actions = parser.add_subparsers(dest="ui_index_action", required=True)
    sync = actions.add_parser("sync", help="在空闲 Edit Mode 按依赖指纹增量同步")
    sync.add_argument("--root", default="Assets")
    sync.add_argument("--full", action="store_true", help="重新抽取此目录全部资产")
    sync.add_argument("--timeout", default=310, type=float)
    find = actions.add_parser("find", help="离线查找静态候选；不判断当前可点击")
    find.add_argument("query", nargs="?", default="")
    find.add_argument("--root", default="Assets")
    find.add_argument("--type", dest="component_type")
    find.add_argument("--alias")
    find.add_argument("--id", dest="control_id")
    find.add_argument("--limit", type=int, default=30)
    annotate = actions.add_parser("annotate", help="显式保存用途与证据；注释不属于可重建缓存")
    annotate.add_argument("control_id")
    annotate.add_argument("--root", default="Assets")
    annotate.add_argument("--alias", required=True)
    annotate.add_argument("--purpose", required=True)
    annotate.add_argument("--origin", choices=("source-inference", "user-confirmed", "runtime-verified"), required=True)
    annotate.add_argument("--evidence", required=True)
    for verb, help_text in (("bind", "Edit Mode 核验已保存的场景实例来源"),
                            ("resolve", "只读核验当前运行态身份"),
                            ("click", "同一请求内核验并非强制点击")):
        runtime = actions.add_parser(verb, help=help_text)
        runtime.add_argument("control_id", **({} if verb == "bind" else {"nargs": "?"}))
        runtime.add_argument("--scene", required=True, help="当前加载的完整 .unity 资源路径")
        runtime.add_argument("--root", default="Assets", help="Prefab 缓存范围")
        runtime.add_argument("--instance-root", help="唯一的运行态 Prefab 根层级路径")
        if verb == "resolve":
            runtime.add_argument("--runtime-path", help="动态节点：当前 Hierarchy 的精确路径")
            runtime.add_argument("--instance-id", type=int, help="动态节点：当前 Hierarchy 的实例 ID")
        elif verb == "click":
            runtime.add_argument("--runtime-token", help="动态节点：resolve 签发的一次性凭证")


def runtime_binding(project, root, args):
    if not args.scene.endswith(".unity") or not 0 < len(args.scene) <= 1024:
        raise UiIndexError("invalid_argument", "需要完整场景资源路径，例如 Assets/Scenes/Demo.unity")
    request = {"scene": args.scene}
    runtime_path = getattr(args, "runtime_path", None)
    instance_id = getattr(args, "instance_id", None)
    token = getattr(args, "runtime_token", None)
    if args.control_id is not None:
        if not args.instance_root or runtime_path is not None or instance_id is not None or token is not None:
            raise UiIndexError("invalid_argument", "Prefab 控件需要 --instance-root，不能混用动态绑定")
        controls = find(project, root, control_id=args.control_id, limit=1)["controls"]
        if not controls:
            raise UiIndexError("ui_index_control_missing", "本目录没有该静态控件 ID")
        control = controls[0]
        if not control["sourceGuid"] or not control["localFileId"] or not control["pointerClickHandler"]:
            raise UiIndexError("ui_index_source_unverified", "静态记录无法证明点击身份，请先从 Hierarchy 观察")
        request.update({"binding": "prefab", "controlId": control["id"], "instanceRoot": args.instance_root,
                        "relativePath": control["path"]})
        request.update({key: control[key] for key in (
            "assetGuid", "assetPath", "fingerprint", "sourceGuid", "localFileId",
            "componentType", "componentIndex",
        )})
        return request

    if args.instance_root:
        raise UiIndexError("invalid_argument", "动态绑定不使用 --instance-root")
    request["binding"] = "runtime"
    if args.ui_index_action == "resolve":
        if not runtime_path or instance_id is None or not (-(2**31) <= instance_id < 2**31) or instance_id == 0:
            raise UiIndexError("invalid_argument", "动态核验需提供 --runtime-path 与当前 --instance-id")
        request.update({"runtimePath": runtime_path, "instanceId": instance_id})
    else:
        if token is None or not HEX32.fullmatch(token):
            raise UiIndexError("invalid_argument", "动态点击需要刚刚 resolve 得到的 --runtime-token")
        request["runtimeToken"] = token
    return request


def validate_root(root: str) -> str:
    if (len(root) > 1024 or "\\" in root or any(ord(c) < 32 for c in root)
            or not (root == "Assets" or root.startswith("Assets/"))
            or any(part in {"", ".", ".."} for part in root.split("/"))):
        raise UiIndexError("invalid_argument", "索引范围必须是 Assets 或其子目录")
    return root


def now():
    return datetime.now(timezone.utc).isoformat()


def project_path(project, *parts):
    # Symlinks and redirects may not put generated artifacts or authored notes outside this project.
    location = project.joinpath(*parts)
    if not location.resolve().is_relative_to(project.resolve()):
        raise UiIndexError("ui_index_path_invalid", "索引路径不得指向工程之外")
    return location


def cache_path(project):
    return project_path(project, "Library", "UnityRunBridge", "ui-index.sqlite3")


def notes_path(project):
    return project_path(project, ".unity-agent", "ui-index-annotations.sqlite3")


def invalid_cache(path):
    return UiIndexError("ui_index_cache_invalid",
                        f"无法读取 UI 索引数据库或版本不兼容：{path}。请先备份；不自动覆盖。")


def require_schema(conn, path):
    if conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA:
        raise invalid_cache(path)


@contextmanager
def database(path, *, write=False, schema=()):
    if not write and (not path.is_file() or path.stat().st_size == 0):
        raise UiIndexError("ui_index_missing", "该工程没有 UI 索引，请先运行 unityctl ui-index sync")
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
    try:
        url = path.resolve().as_uri() + ("?mode=rwc" if write else "?mode=ro")
        with closing(sqlite3.connect(url, uri=True, timeout=5, isolation_level=None)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            if write and conn.execute("PRAGMA user_version").fetchone()[0] == 0:
                if conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone() is not None:
                    raise invalid_cache(path)
                for statement in schema:
                    conn.execute(statement)
                conn.execute(f"PRAGMA user_version={SCHEMA}")
            require_schema(conn, path)
            yield conn
            conn.commit()
    except sqlite3.DatabaseError as exc:
        if isinstance(exc, sqlite3.OperationalError) and "locked" in str(exc).lower():
            raise UiIndexError("ui_index_busy", "索引正被另一个操作使用，请稍后重试") from exc
        raise invalid_cache(path) from exc


def scope_state(conn, root):
    row = conn.execute("SELECT revision, synced_at FROM scopes WHERE root=?", (root,)).fetchone()
    return (row["revision"], row["synced_at"]) if row else (0, None)


def snapshot(project, root):
    path = cache_path(project)
    if not path.exists() or path.stat().st_size == 0:
        return 0, {}
    with database(path) as conn:
        revision, _ = scope_state(conn, root)
        known = {row["guid"]: row["fingerprint"] for row in conn.execute(
            "SELECT guid, fingerprint FROM prefabs WHERE root=?", (root,))}
    return revision, known


def artifact_path(project, job_id, result, root):
    if (not isinstance(result, dict) or type(result.get("schema")) is not int
            or result["schema"] != SCHEMA or result.get("root") != root
            or not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id)
            or not isinstance(result.get("artifactPath"), str)):
        raise UiIndexError("ui_index_scan_invalid", "Bridge 的扫描描述不兼容或范围不匹配")
    expected = project_path(project, "Library", "UnityRunBridge", "ui-index-results", job_id + ".jsonl")
    advertised = Path(result["artifactPath"])
    if (not advertised.is_absolute() or advertised.resolve() != expected.resolve()
            or expected.is_symlink() or not expected.is_file()
            or expected.stat().st_size > MAX_ARTIFACT_BYTES):
        raise UiIndexError("ui_index_scan_invalid", "扫描产物缺失、越界或超过大小上限")
    return expected


def string_field(item, key, *, limit=1024, allow_empty=False):
    value = item.get(key)
    if not isinstance(value, str) or len(value) > limit or (not value and not allow_empty):
        raise ValueError(f"非法的 {key}")
    return value


def asset_metadata(asset, root):
    if not isinstance(asset, dict):
        raise ValueError("资产记录必须是对象")
    guid, fingerprint, path = (string_field(asset, k) for k in ("guid", "fingerprint", "path"))
    try:
        validate_root(path)
    except UiIndexError as exc:
        raise ValueError("资产路径非法") from exc
    if (not HEX32.fullmatch(guid) or not HEX32.fullmatch(fingerprint)
            or not path.startswith(root + "/") or not path.lower().endswith(".prefab")
            or type(asset.get("changed")) is not bool):
        raise ValueError("资产身份、路径或变更状态非法")
    return guid, fingerprint, path


def control_entry(guid, control):
    if not isinstance(control, dict):
        raise ValueError("控件记录必须是对象")
    name = string_field(control, "name", allow_empty=True)
    kind = string_field(control, "componentType")
    path = control.get("path")
    index = control.get("componentIndex")
    if not isinstance(path, list) or len(path) > 1024 or type(index) is not int or index < 0:
        raise ValueError("控件路径或组件序号非法")
    parts = []
    for part in path:
        if (not isinstance(part, dict) or type(part.get("siblingIndex")) is not int
                or part["siblingIndex"] < 0):
            raise ValueError("控件路径段非法")
        parts.append([string_field(part, "name", allow_empty=True), part["siblingIndex"]])
    if parts and parts[-1][0] != name:
        raise ValueError("控件路径名称与节点名不一致")
    source, file_id = control.get("sourceGuid"), control.get("localFileId")
    if (source is not None or file_id is not None) and (
        not isinstance(source, str) or not HEX32.fullmatch(source) or not isinstance(file_id, str)
        or not FILE_ID.fullmatch(file_id) or file_id == "0"
    ):
        raise ValueError("Prefab 来源身份非法")
    for key in ("activeSelf", "enabled", "pointerClickHandler"):
        if type(control.get(key)) is not bool:
            raise ValueError(f"非法的 {key}")
    if control.get("interactable") is not None and type(control["interactable"]) is not bool:
        raise ValueError("非法的 interactable")
    callbacks = control.get("persistentCallbacks")
    if not isinstance(callbacks, list) or len(callbacks) > 64:
        raise ValueError("持久回调列表非法")
    for callback in callbacks:
        if not isinstance(callback, dict):
            raise ValueError("持久回调必须是对象")
        for key in ("method", "targetType"):
            if callback.get(key) is not None:
                string_field(callback, key, allow_empty=True)
    stable_key = json.dumps([guid, parts, index, kind, source, file_id],
                            ensure_ascii=True, separators=(",", ":"))
    normalized = {key: control.get(key) for key in (
        "name", "componentType", "componentIndex", "activeSelf", "enabled", "interactable",
        "pointerClickHandler", "sourceGuid", "localFileId",
    )}
    normalized["path"] = [{"name": segment, "siblingIndex": sibling} for segment, sibling in parts]
    normalized["persistentCallbacks"] = [{key: cb.get(key) for key in ("method", "targetType")} for cb in callbacks]
    normalized["persistentCallbacksTruncated"] = control.get("persistentCallbacksTruncated") is True
    return (hashlib.sha256(stable_key.encode()).hexdigest(), name, kind,
            "/".join(p[0] for p in parts), normalized)


def import_snapshot(project, root, revision, known, job_id, result):
    artifact = artifact_path(project, job_id, result, root)
    cache = cache_path(project)
    seen = set()
    counts = {"prefabs": 0, "scanned": 0, "unchanged": 0, "controlsScanned": 0, "unidentifiedScanned": 0}
    try:
        with database(cache, write=True, schema=CACHE_SCHEMA) as conn, artifact.open(encoding="utf-8") as stream:
            if scope_state(conn, root)[0] != revision:
                raise UiIndexError("ui_index_conflict", "同步期间此目录的缓存已更新；请重新同步")
            conn.execute("INSERT OR IGNORE INTO scopes VALUES (?, 0, '')", (root,))
            for line in stream:
                if len(seen) >= MAX_PREFABS:
                    raise ValueError("Prefab 数量超限")
                asset = json.loads(line)
                guid, fingerprint, path = asset_metadata(asset, root)
                if guid in seen:
                    raise ValueError("扫描包含重复资产")
                seen.add(guid)
                counts["prefabs"] += 1
                if not asset["changed"]:
                    if ("controls" in asset or known.get(guid) != fingerprint or
                        conn.execute("UPDATE prefabs SET path=? WHERE root=? AND guid=? AND fingerprint=?",
                                     (path, root, guid, fingerprint)).rowcount != 1):
                        raise ValueError("未变化记录缺少匹配的旧指纹")
                    counts["unchanged"] += 1
                    continue
                controls = asset.get("controls")
                if not isinstance(controls, list) or len(controls) > 4096:
                    raise ValueError("控件列表非法")
                conn.execute("DELETE FROM prefabs WHERE root=? AND guid=?", (root, guid))
                conn.execute("INSERT INTO prefabs VALUES (?, ?, ?, ?)", (root, guid, path, fingerprint))
                seen_controls = set()
                for entry in controls:
                    identity, name, kind, relative, normalized = control_entry(guid, entry)
                    if identity in seen_controls:
                        raise ValueError("扫描包含重复控件")
                    seen_controls.add(identity)
                    conn.execute("INSERT INTO controls VALUES (?, ?, ?, ?, ?, ?, ?)",
                                 (root, guid, identity, name, kind, f"{name}\n{relative}".casefold(),
                                  json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))))
                    counts["controlsScanned"] += 1
                    counts["unidentifiedScanned"] += entry.get("localFileId") is None
                counts["scanned"] += 1
            if any(type(result.get(key)) is not int or result[key] != count for key, count in counts.items()):
                raise ValueError("扫描文件与 Bridge 汇总计数不一致")
            if (type(result.get("deleted")) is not int or result["deleted"] != len(known.keys() - seen)
                    or type(result.get("skipped")) is not int or result["skipped"] < 0
                    or type(result.get("durationMs")) is not int or result["durationMs"] < 0):
                raise ValueError("扫描汇总元数据不一致")
            previous = list(conn.execute("SELECT guid FROM prefabs WHERE root=?", (root,)))
            removed = [row["guid"] for row in previous if row["guid"] not in seen]
            conn.executemany("DELETE FROM prefabs WHERE root=? AND guid=?", ((root, guid) for guid in removed))
            timestamp = now()
            conn.execute("UPDATE scopes SET revision=?, synced_at=? WHERE root=?", (revision + 1, timestamp, root))
    except UiIndexError:
        raise
    except (ValueError, OSError) as exc:
        raise UiIndexError("ui_index_scan_invalid", f"未更新缓存：{exc}") from exc

    warning = None
    try:
        artifact.unlink()
    except OSError:
        warning = "缓存已更新，未能删除本次临时扫描产物"
    return {"ok": True, "schema": SCHEMA, "root": root, "syncedAt": timestamp, "source": "asset-database",
            "deleted": len(removed), "bridgeDurationMs": result["durationMs"], "skipped": result["skipped"],
            **counts, **({"warning": warning} if warning else {})}


def find(project, root, query="", component_type=None, alias=None, control_id=None, limit=30):
    if not 1 <= limit <= 200 or len(query) > 512 or (alias is not None and not 0 < len(alias.strip()) <= 128):
        raise UiIndexError("invalid_argument", "查询或结果数量非法")
    if control_id is not None and not CONTROL_ID.fullmatch(control_id):
        raise UiIndexError("invalid_argument", "无效的控件 ID")
    np = notes_path(project)
    has_notes = np.is_file()
    with database(cache_path(project)) as conn:
        # Annotations are deliberately a separate owner-managed document, not generated cache.
        if has_notes:
            conn.execute("ATTACH DATABASE ? AS notes", (np.resolve().as_uri() + "?mode=ro",))
            if conn.execute("PRAGMA notes.user_version").fetchone()[0] != SCHEMA:
                raise invalid_cache(np)
            annotation_cols = ", n.alias,n.purpose,n.origin,n.evidence,n.fingerprint AS note_fingerprint"
            annotation_join = " LEFT JOIN notes.annotations n ON n.id=c.id"
        else:
            annotation_cols = ", NULL AS alias"
            annotation_join = ""
        revision, synced = scope_state(conn, root)
        if not revision:
            raise UiIndexError("ui_index_scope_missing", f"没有此目录的快照：{root}；请先同步同一 --root")
        where, values = ["c.root=?"], [root]
        if query:
            where.append("(instr(c.search, ?) > 0 OR instr(lower(p.path), ?) > 0)")
            values.extend((query.casefold(), query.lower()))
        if component_type:
            where.append("(c.component_type=? OR substr(c.component_type, -length(?) - 1)=('.' || ?))")
            values.extend((component_type, component_type, component_type))
        if control_id:
            where.append("c.id=?")
            values.append(control_id)
        if alias is not None:
            where.append("n.alias_key=?" if has_notes else "0")
            if has_notes:
                values.append(alias.strip().casefold())
        rows = conn.execute(
            "SELECT c.id,c.data,p.guid,p.path,p.fingerprint" + annotation_cols
            + " FROM controls c JOIN prefabs p ON c.root=p.root AND c.guid=p.guid" + annotation_join
            + " WHERE " + " AND ".join(where) + " ORDER BY p.path,c.name,c.id LIMIT ?",
            (*values, limit + 1),
        ).fetchall()
        results = []
        for row in rows[:limit]:
            item = {"id": row["id"], "assetGuid": row["guid"], "assetPath": row["path"],
                    "fingerprint": row["fingerprint"], **json.loads(row["data"])}
            if row["alias"] is not None:
                item["annotation"] = {key: row[key] for key in ("alias", "purpose", "origin", "evidence")}
                item["annotation"]["stale"] = row["note_fingerprint"] != row["fingerprint"]
            results.append(item)
    return {"ok": True, "root": root, "syncedAt": synced, "source": "local-prefab-snapshot",
            "liveVerified": False, "ambiguous": len(rows) > 1, "truncated": len(rows) > limit,
            "controls": results}


def annotate(project, root, control_id, alias, purpose, origin, evidence):
    alias, purpose, evidence = (text.strip() for text in (alias, purpose, evidence))
    if not 0 < len(alias) <= 128 or not 0 < len(purpose) <= 512 or not 0 < len(evidence) <= 512:
        raise UiIndexError("invalid_argument", "别名、用途和证据必须非空且不超出长度限制")
    controls = find(project, root, control_id=control_id, limit=1)["controls"]
    if not controls:
        raise UiIndexError("ui_index_control_missing", "此目录没有对应控件 ID")
    with database(notes_path(project), write=True, schema=NOTES_SCHEMA) as conn:
        conn.execute(
            """INSERT INTO annotations VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET alias=excluded.alias, alias_key=excluded.alias_key,
            purpose=excluded.purpose, origin=excluded.origin, evidence=excluded.evidence,
            fingerprint=excluded.fingerprint, created_at=excluded.created_at""",
            (control_id, alias, alias.casefold(), purpose, origin, evidence, controls[0]["fingerprint"], now()),
        )
    return {"ok": True, "id": control_id, "alias": alias, "origin": origin, "liveVerified": False}
