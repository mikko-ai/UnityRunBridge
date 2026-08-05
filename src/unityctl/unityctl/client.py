import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class BridgeClientError(RuntimeError):
    def __init__(self, message: str, code: str = "internal_error"):
        super().__init__(message)
        self.code = code


class BridgeUnreachableError(BridgeClientError):
    """连接失败（拒绝连接/超时/DNS 等）。区分于业务失败，供收敛循环判断是否为
    domain reload 的正常窗口。"""

    def __init__(self, message: str):
        super().__init__(message, code="bridge_unreachable")


def require_bridge_route(client: Any, capability: str, method: str, path: str) -> None:
    """校验 capability，并在 Bridge 提供 routes 元数据时进一步校验具体路由。

    旧 Bridge 可能只返回 capability 列表；缺少 routes 字段时保留原有兼容行为，
    让实际请求决定是否支持。若 routes 明确存在，则缺少新路由视为能力缺失。
    """
    response = client.get_capabilities()
    capabilities = response.get("capabilities", [])
    if capability not in capabilities:
        raise BridgeClientError(
            f"缺少 {capability} 能力，请检查可选依赖或 Bridge 版本",
            code="bridge_capability_missing",
        )

    routes = response.get("routes")
    if routes is None:
        return

    expected_method = method.upper()
    for route in routes:
        if not isinstance(route, dict):
            continue
        if str(route.get("method", "")).upper() == expected_method and route.get("path") == path:
            return

    raise BridgeClientError(
        f"当前 Bridge 未注册 {expected_method} {path}，请升级 Bridge 版本",
        code="bridge_capability_missing",
    )


@dataclass(frozen=True)
class BridgeClient:
    base_url: str
    token: str
    timeout_seconds: float = 10.0

    def get_status(self) -> dict[str, Any]:
        return self.get("status")

    def open_scene(self, scene_path: str) -> dict[str, Any]:
        return self.post("open-scene", {"scenePath": scene_path})

    def start_session(self, session_id: str, session_path: str) -> dict[str, Any]:
        return self.post(
            "session/start",
            {
                "sessionId": session_id,
                "sessionPath": session_path,
            },
        )

    def end_session(self) -> dict[str, Any]:
        return self.post("session/end")

    def get_session_status(self) -> dict[str, Any]:
        return self.get("session/status")

    def refresh(self) -> dict[str, Any]:
        return self.post("refresh")

    def get_capabilities(self) -> dict[str, Any]:
        """老版本 Bridge 没有 /capabilities 路由，返回 not_found；这里统一降级为
        只有 core 能力的信封，供调用方做兼容判断而不必特判 404。"""
        try:
            return self.get("capabilities")
        except BridgeClientError as exc:
            if exc.code == "not_found":
                return {"ok": True, "bridgeVersion": None, "capabilities": ["core"], "legacy": True}
            raise

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self.get(f"jobs/{job_id}")

    def hierarchy_roots(self) -> dict[str, Any]:
        return self.get("hierarchy/roots")

    def hierarchy_tree(self, **params: Any) -> dict[str, Any]:
        return self.get("hierarchy/tree", params)

    def hierarchy_find(self, **params: Any) -> dict[str, Any]:
        return self.get("hierarchy/find", params)

    def hierarchy_ancestors(self, **params: Any) -> dict[str, Any]:
        return self.get("hierarchy/ancestors", params)

    def hierarchy_inspect(self, **params: Any) -> dict[str, Any]:
        return self.get("hierarchy/inspect", params)

    def interaction_click(
        self,
        path: str,
        force: bool = False,
        scene: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"path": path, "force": force}
        if scene is not None:
            payload["scene"] = scene
        return self.post("interaction/click", payload)

    def interaction_input(
        self,
        path: str,
        text: str,
        submit: bool = False,
        scene: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"path": path, "text": text, "submit": submit}
        if scene is not None:
            payload["scene"] = scene
        return self.post("interaction/input", payload)

    def interaction_set_value(
        self,
        path: str,
        value: Any,
        component: str | None = None,
        scene: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"path": path, "value": value}
        if component is not None:
            payload["component"] = component
        if scene is not None:
            payload["scene"] = scene
        return self.post("interaction/set-value", payload)

    def recording_start(self, target_directory: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if target_directory is not None:
            payload["targetDirectory"] = target_directory
        return self.post("recording/start", payload)

    def recording_stop(self) -> dict[str, Any]:
        return self.post("recording/stop")

    def recording_status(self) -> dict[str, Any]:
        return self.get("recording/status")

    def profiling_start(self, target_directory: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if target_directory is not None:
            payload["targetDirectory"] = target_directory
        return self.post("profiling/start", payload)

    def profiling_stop(self) -> dict[str, Any]:
        return self.post("profiling/stop")

    def profiling_status(self) -> dict[str, Any]:
        return self.get("profiling/status")

    def health_scan_prefabs(self) -> dict[str, Any]:
        return self.post("health/scan-prefabs")

    def gameplay_list(self) -> dict[str, Any]:
        return self.get("gameplay/commands")

    def gameplay_invoke(self, command: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"command": command, "args": args or {}}
        return self.post("gameplay/invoke", payload)

    def capture_screenshot(
        self,
        reason: str | None = None,
        max_long_edge: int | None = None,
        target_directory: str | None = None,
        annotate: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if reason is not None:
            payload["reason"] = reason
        if max_long_edge is not None:
            payload["maxLongEdge"] = max_long_edge
        if target_directory is not None:
            payload["targetDirectory"] = target_directory
        if annotate:
            payload["annotate"] = True
        return self.post("capture/screenshot", payload)

    def capture_hit_test(
        self,
        x: float,
        y: float,
        image_width: float,
        image_height: float,
    ) -> dict[str, Any]:
        return self.post(
            "capture/hit-test",
            {
                "x": x,
                "y": y,
                "imageWidth": image_width,
                "imageHeight": image_height,
            },
        )

    def interaction_long_press(
        self,
        path: str,
        duration_seconds: float = 0.5,
        force: bool = False,
        scene: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path": path,
            "durationSeconds": duration_seconds,
            "force": force,
        }
        if scene is not None:
            payload["scene"] = scene
        return self.post("interaction/long-press", payload)

    def interaction_drag(
        self,
        path: str,
        delta_x: float,
        delta_y: float,
        duration_seconds: float = 0.3,
        steps: int = 8,
        force: bool = False,
        scene: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path": path,
            "deltaX": delta_x,
            "deltaY": delta_y,
            "durationSeconds": duration_seconds,
            "steps": steps,
            "force": force,
        }
        if scene is not None:
            payload["scene"] = scene
        return self.post("interaction/drag", payload)

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self._url(path, params)
        request = Request(url, method="GET", headers=self._headers())
        return self._send(request)

    def post(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self._url(path)
        body = json.dumps(payload or {}).encode("utf-8")
        headers = self._headers()
        headers["Content-Type"] = "application/json"
        request = Request(url, data=body, method="POST", headers=headers)
        return self._send(request)

    def _headers(self) -> dict[str, str]:
        return {"X-Bridge-Token": self.token}

    def _url(self, path: str, params: dict[str, Any] | None = None) -> str:
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        if not params:
            return url
        # None/False 值一律省略（而不是序列化成 "None"/"False" 字符串），
        # 让调用方可以直接把整个 kwargs 字典透传过来而不用逐个判空。
        # bool True 显式转成小写 "true"——Bridge 的 GetQueryBool 只认小写字面量，
        # 而 urlencode 对 Python bool 会用 str() 产出首字母大写的 "True"。
        cleaned = {
            key: ("true" if value is True else value)
            for key, value in params.items()
            if value is not None and value is not False
        }
        if not cleaned:
            return url
        return f"{url}?{urlencode(cleaned)}"

    def _send(self, request: Request) -> dict[str, Any]:
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = response.read().decode("utf-8")
                return json.loads(payload) if payload else {}
        except HTTPError as exc:
            body = _read_error_body(exc)
            code = body.get("code", "internal_error") if body else "internal_error"
            message = body.get("message") if body else None
            raise BridgeClientError(
                message or f"HTTP {exc.code}: {exc.reason}", code=code
            ) from exc
        except URLError as exc:
            raise BridgeUnreachableError(f"无法连接 Unity Bridge：{exc.reason}") from exc
        except TimeoutError as exc:
            raise BridgeUnreachableError("Unity Bridge 请求超时") from exc
        except json.JSONDecodeError as exc:
            raise BridgeClientError(
                "Unity Bridge 返回了非法 JSON", code="internal_error"
            ) from exc


def _read_error_body(exc: HTTPError) -> dict[str, Any] | None:
    try:
        raw = exc.read()
    except Exception:
        return None
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
