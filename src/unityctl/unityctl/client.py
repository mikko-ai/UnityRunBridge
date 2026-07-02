import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
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

    def get(self, path: str) -> dict[str, Any]:
        url = self._url(path)
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

    def _url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

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
