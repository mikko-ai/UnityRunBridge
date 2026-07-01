import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class BridgeClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class BridgeClient:
    base_url: str = "http://127.0.0.1:17890"
    timeout_seconds: float = 10.0

    def get_status(self) -> dict[str, Any]:
        return self.get("status")

    def open_scene(self, scene_path: str) -> dict[str, Any]:
        return self.post("open-scene", {"scenePath": scene_path})

    def get(self, path: str) -> dict[str, Any]:
        url = self._url(path)
        request = Request(url, method="GET")
        return self._send(request)

    def post(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self._url(path)
        body = json.dumps(payload or {}).encode("utf-8")
        request = Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        return self._send(request)

    def _url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    def _send(self, request: Request) -> dict[str, Any]:
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = response.read().decode("utf-8")
                return json.loads(payload) if payload else {}
        except HTTPError as exc:
            raise BridgeClientError(f"HTTP {exc.code}: {exc.reason}") from exc
        except URLError as exc:
            raise BridgeClientError(f"Cannot reach Unity bridge: {exc.reason}") from exc
        except TimeoutError as exc:
            raise BridgeClientError("Unity bridge request timed out") from exc
        except json.JSONDecodeError as exc:
            raise BridgeClientError("Unity bridge returned invalid JSON") from exc
