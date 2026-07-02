import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from unityctl.client import BridgeClient, BridgeUnreachableError
from unityctl.discovery import BridgeInfo, DiscoveryError, discover


class ConvergenceTimeout(RuntimeError):
    """轮询超过 deadline 仍未达成目标状态。"""

    def __init__(self, message: str, last_status: dict[str, Any] | None = None):
        super().__init__(message)
        self.last_status = last_status


class ConvergenceEditorExited(RuntimeError):
    """轮询过程中 Unity Editor 进程已退出（而不是短暂的 domain reload 窗口）。"""


class ConvergenceFailed(RuntimeError):
    """业务层判定的终止性失败（例如编译失败），无需等到超时即可提前退出轮询。"""

    def __init__(self, reason: str, status: dict[str, Any] | None = None):
        super().__init__(reason)
        self.reason = reason
        self.status = status


@dataclass
class ConvergenceResult:
    status: dict[str, Any]
    info: BridgeInfo


def parse_utc_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def poll_until(
    project_path: str | Path,
    predicate: Callable[[dict[str, Any]], bool],
    timeout_seconds: float,
    poll_interval: float = 0.5,
    initial_info: BridgeInfo | None = None,
) -> ConvergenceResult:
    """轮询 GET /status 直到 predicate(status) 返回 True、超时或 Editor 进程退出。

    predicate 除了返回 bool 之外，也可以主动抛出 ConvergenceFailed 以立即终止轮询
    （例如探测到编译失败，没有必要继续等到超时）。

    连接失败（HTTP 层无法连接）被当作 domain reload 的正常窗口来处理：
    重新走一次 discover()，只要 bridge.json 记录的 pid 还存活就继续轮询；
    pid 已经不存在则判定为 Editor 真的退出了，立即抛出 ConvergenceEditorExited。
    """
    deadline = time.monotonic() + timeout_seconds
    info = initial_info or discover(project_path)
    last_status: dict[str, Any] | None = None

    while True:
        try:
            client = BridgeClient(info.base_url, info.token)
            status = client.get_status()
            last_status = status
            if predicate(status):
                return ConvergenceResult(status=status, info=info)
        except BridgeUnreachableError:
            try:
                info = discover(project_path)
            except DiscoveryError as exc:
                raise ConvergenceEditorExited(str(exc)) from exc

        if time.monotonic() > deadline:
            raise ConvergenceTimeout("等待 Unity Editor 状态收敛超时", last_status=last_status)

        time.sleep(poll_interval)
