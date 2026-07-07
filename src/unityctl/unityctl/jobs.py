import time
from pathlib import Path
from typing import Any

from unityctl.client import BridgeClient, BridgeUnreachableError
from unityctl.discovery import BridgeInfo, DiscoveryError, discover


class JobTimeout(RuntimeError):
    """轮询超过 deadline，job 仍未进入终态（succeeded/failed）。"""

    def __init__(self, message: str, last_job: dict[str, Any] | None = None):
        super().__init__(message)
        self.last_job = last_job


class JobEditorExited(RuntimeError):
    """轮询过程中 Unity Editor 进程已退出（而不是短暂的 domain reload 窗口）。"""


class JobFailed(RuntimeError):
    """job 进入 failed 终态；携带完整 job dict 供调用方读取 errorCode/errorMessage。"""

    def __init__(self, job: dict[str, Any]):
        super().__init__(job.get("errorMessage") or job.get("errorCode") or "job failed")
        self.job = job


def wait_for_job(
    project_path: str | Path,
    job_id: str,
    timeout_seconds: float,
    poll_interval: float = 0.5,
    initial_info: BridgeInfo | None = None,
    raise_on_failure: bool = True,
) -> dict[str, Any]:
    """轮询 GET /jobs/{id} 直到 job 进入终态或超时/Editor 退出。

    连接失败被当作 domain reload 的正常窗口处理，规则与 convergence.poll_until 一致：
    重新走一次 discover()，pid 还存活就继续轮询，否则判定 Editor 已退出。

    raise_on_failure=True（默认）时 job 状态为 failed 会抛 JobFailed；
    传 False 可以拿到 job dict 自行处理失败细节（例如断言引擎记录证据）。
    """
    deadline = time.monotonic() + timeout_seconds
    info = initial_info or discover(project_path)

    while True:
        try:
            client = BridgeClient(info.base_url, info.token)
            response = client.get_job(job_id)
            job = response.get("job", {})
            status = job.get("status")
            if status == "succeeded":
                return job
            if status == "failed":
                if raise_on_failure:
                    raise JobFailed(job)
                return job
        except BridgeUnreachableError:
            try:
                info = discover(project_path)
            except DiscoveryError as exc:
                raise JobEditorExited(str(exc)) from exc

        if time.monotonic() > deadline:
            raise JobTimeout(f"等待 job {job_id} 完成超时")

        time.sleep(poll_interval)
