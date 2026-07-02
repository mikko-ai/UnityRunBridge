import json
import os
from dataclasses import dataclass
from pathlib import Path

from unityctl.config import BRIDGE_HOST, BRIDGE_INFO_FILENAME, find_unity_project_root


class DiscoveryError(RuntimeError):
    def __init__(self, message: str, code: str = "bridge_unreachable"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class BridgeInfo:
    port: int
    pid: int
    token: str
    unity_version: str
    project_path: str
    started_at: str

    @property
    def base_url(self) -> str:
        return f"http://{BRIDGE_HOST}:{self.port}"


def bridge_info_path(project_path: str | Path) -> Path:
    project = find_unity_project_root(project_path)
    return project / ".unity-agent" / BRIDGE_INFO_FILENAME


def read_bridge_info(project_path: str | Path) -> BridgeInfo:
    path = bridge_info_path(project_path)
    if not path.exists():
        raise DiscoveryError(
            "找不到 .unity-agent/bridge.json，Unity Editor 可能尚未启动。"
            "请先运行 unityctl start"
        )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DiscoveryError(f"bridge.json 解析失败：{exc}") from exc

    schema_version = payload.get("schemaVersion") if isinstance(payload, dict) else None
    if schema_version != 1:
        raise DiscoveryError(f"bridge.json 的 schemaVersion 不受支持：{schema_version!r}")

    try:
        info = BridgeInfo(
            port=int(payload["port"]),
            pid=int(payload["pid"]),
            token=str(payload["token"]),
            unity_version=str(payload.get("unityVersion", "")),
            project_path=str(payload.get("projectPath", "")),
            started_at=str(payload.get("startedAt", "")),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise DiscoveryError(f"bridge.json 内容不完整：{exc}") from exc

    if not 1 <= info.port <= 65535:
        raise DiscoveryError(f"bridge.json 的端口非法：{info.port}")
    if not info.token:
        raise DiscoveryError("bridge.json 缺少鉴权 token")
    return info


def is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # 没有权限发信号通常意味着进程存在但属于其他用户，仍然视为存活。
        return True
    except OSError:
        return False
    return True


def discover(project_path: str | Path) -> BridgeInfo:
    """握手校验的前两步：读取 bridge.json，再确认里面记录的 pid 仍然存活。

    第三步（带 token 请求 GET /status）交由调用方使用返回的 BridgeInfo 自行发起，
    避免 discovery 模块依赖 client 模块，形成循环依赖。
    """
    info = read_bridge_info(project_path)
    if not is_pid_alive(info.pid):
        path = bridge_info_path(project_path)
        if path.exists():
            path.unlink()
        raise DiscoveryError(
            f"Unity Editor 进程（pid={info.pid}）已不存在，bridge.json 是过期文件，已自动清理。"
            "请先运行 unityctl start",
            code="editor_not_running",
        )
    return info
