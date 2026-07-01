# Unity Editor Control 实现计划

> **给 agentic worker 的要求：** 实施本计划时必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`。所有步骤都使用 checkbox（`- [ ]`）格式，方便逐项跟踪。

**目标：** 构建第一版低侵入 Unity Editor 控制服务，让外部 agent 可以启动、查询、进入 PlayMode、停止、暂停、恢复，并打开单个 Unity 项目中的场景。

**架构：** Unity 项目通过一个 Editor-only UPM package 接入 Bridge。Bridge 在 Unity Editor 内启动本地 HTTP 服务，外部 Python CLI `unityctl` 负责启动 Editor 进程，并通过 HTTP 调用 Bridge 控制 PlayMode。由于 `HttpListener` 回调不在 Unity 主线程执行，所有 Unity Editor API 调用都必须通过主线程队列转发。

**技术栈：** Unity Editor C# UPM package、`System.Net.HttpListener`、Unity `EditorApplication`、Unity `EditorSceneManager`、Python 3.11+、`uv`、`argparse`、`urllib.request`、`pytest`。

---

## 范围

本计划只覆盖第一段“运行控制”能力：

- 单 Unity 项目
- 单 Unity Editor 实例
- 固定本地 Bridge 地址：`http://127.0.0.1:17890`
- Editor PlayMode 控制
- 打开指定 scene
- 面向人和通用 agent 的 CLI 命令

本计划不包含：

- 游戏运行状态结构化
- UI tree 提取
- 截图理解
- 游戏内点击/输入
- MCP tools
- 多项目发现
- WebSocket 日志流
- 自动验证断言

## 文件结构

创建以下文件：

- `packages/com.elex.unity-agent-bridge/package.json`  
  Unity Bridge 的 UPM package manifest。
- `packages/com.elex.unity-agent-bridge/Editor/UnityAgentBridge.asmdef`  
  Editor-only assembly definition。
- `packages/com.elex.unity-agent-bridge/Editor/BridgeConfig.cs`  
  Bridge host、port、version 等常量。
- `packages/com.elex.unity-agent-bridge/Editor/BridgeResponse.cs`  
  HTTP response 和 request DTO。
- `packages/com.elex.unity-agent-bridge/Editor/EditorStateProvider.cs`  
  只读查询当前 Unity Editor 状态。
- `packages/com.elex.unity-agent-bridge/Editor/PlayModeController.cs`  
  通过 `EditorApplication` 控制 PlayMode、Pause、Resume。
- `packages/com.elex.unity-agent-bridge/Editor/SceneController.cs`  
  通过 `EditorSceneManager` 打开项目内 scene。
- `packages/com.elex.unity-agent-bridge/Editor/BridgeServer.cs`  
  启动 localhost HTTP server，并把请求路由到 Unity 主线程。
- `packages/com.elex.unity-agent-bridge/Tests/Editor/UnityAgentBridge.Tests.asmdef`  
  Unity EditMode tests assembly definition。
- `packages/com.elex.unity-agent-bridge/Tests/Editor/EditorStateProviderTests.cs`  
  测试 status 数据形状。
- `packages/com.elex.unity-agent-bridge/Tests/Editor/SceneControllerTests.cs`  
  测试 scene path 校验。
- `src/unityctl/pyproject.toml`  
  Python CLI package metadata。
- `src/unityctl/uv.lock`
  `uv sync` 生成的 Python dependency lockfile。
- `src/unityctl/unityctl/__init__.py`  
  Python package marker。
- `src/unityctl/unityctl/client.py`  
  Unity Bridge HTTP client。
- `src/unityctl/unityctl/editor.py`  
  Unity Editor 进程启动器。
- `src/unityctl/unityctl/cli.py`  
  `unityctl` 命令行入口。
- `src/unityctl/tests/test_client.py`  
  Python HTTP client tests。
- `src/unityctl/tests/test_cli.py`  
  Python CLI routing tests。
- `src/unityctl/tests/test_editor.py`  
  Unity 启动命令构造 tests。
- `README.md`  
  最小安装和首次运行说明。

## Task 1: 搭建 Python CLI Package

**Files:**
- Create: `src/unityctl/pyproject.toml`
- Create: `src/unityctl/uv.lock`
- Create: `src/unityctl/unityctl/__init__.py`
- Create: `src/unityctl/unityctl/client.py`
- Create: `src/unityctl/tests/test_client.py`

- [ ] **Step 1: 编写失败的 HTTP client tests**

创建 `src/unityctl/tests/test_client.py`：

```python
import json
from urllib.error import HTTPError

import pytest

from unityctl.client import BridgeClient, BridgeClientError


class FakeResponse:
    def __init__(self, status: int, payload: dict):
        self.status = status
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_get_status_returns_json(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, request.get_method(), timeout))
        return FakeResponse(200, {"ok": True, "isPlaying": False})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890", timeout_seconds=2.0)
    result = client.get_status()

    assert result == {"ok": True, "isPlaying": False}
    assert calls == [("http://127.0.0.1:17890/status", "GET", 2.0)]


def test_post_command_returns_json(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, request.get_method(), request.data))
        return FakeResponse(200, {"ok": True, "message": "entered play mode"})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890")
    result = client.post("play")

    assert result == {"ok": True, "message": "entered play mode"}
    assert calls == [("http://127.0.0.1:17890/play", "POST", b"{}")]


def test_open_scene_sends_scene_path(monkeypatch):
    captured_body = []

    def fake_urlopen(request, timeout):
        captured_body.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(200, {"ok": True, "scenePath": "Assets/Scenes/Login.unity"})

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890")
    result = client.open_scene("Assets/Scenes/Login.unity")

    assert captured_body == [{"scenePath": "Assets/Scenes/Login.unity"}]
    assert result["ok"] is True


def test_http_error_becomes_bridge_client_error(monkeypatch):
    def fake_urlopen(request, timeout):
        raise HTTPError(
            url=request.full_url,
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("unityctl.client.urlopen", fake_urlopen)

    client = BridgeClient("http://127.0.0.1:17890")

    with pytest.raises(BridgeClientError) as exc:
        client.post("play")

    assert "HTTP 500" in str(exc.value)
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge
uvx pytest src/unityctl/tests/test_client.py -v
```

预期：测试失败，错误包含 `ModuleNotFoundError: No module named 'unityctl'`。

- [ ] **Step 3: 创建 Python package metadata**

创建 `src/unityctl/pyproject.toml`：

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "unityctl"
version = "0.1.0"
description = "Local CLI for controlling a Unity Editor bridge"
requires-python = ">=3.11"
dependencies = []

[project.scripts]
unityctl = "unityctl.cli:main"

[dependency-groups]
dev = [
    "pytest>=8.0",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["unityctl*"]
```

- [ ] **Step 4: 创建 package marker**

创建 `src/unityctl/unityctl/__init__.py`：

```python
__version__ = "0.1.0"
```

- [ ] **Step 5: 实现 Bridge HTTP client**

创建 `src/unityctl/unityctl/client.py`：

```python
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
```

- [ ] **Step 6: 运行 client tests**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests/test_client.py -v
```

预期：`4 passed`。

说明：`uv run` 会根据 `pyproject.toml` 同步本地环境，并生成应提交的 `src/unityctl/uv.lock`。

- [ ] **Step 7: 提交**

Run:

```bash
git add src/unityctl/pyproject.toml src/unityctl/uv.lock src/unityctl/unityctl/__init__.py src/unityctl/unityctl/client.py src/unityctl/tests/test_client.py
git commit -m "feat: add unity bridge http client"
```

预期：commit 成功。

## Task 2: 添加 Unity Editor 进程启动器

**Files:**
- Create: `src/unityctl/unityctl/editor.py`
- Create: `src/unityctl/tests/test_editor.py`

- [ ] **Step 1: 编写失败的 launcher tests**

创建 `src/unityctl/tests/test_editor.py`：

```python
from pathlib import Path

import pytest

from unityctl.editor import build_editor_command, validate_project_path


def test_build_editor_command_uses_project_path_and_log_file():
    command = build_editor_command(
        unity_path="/Applications/Unity/Hub/Editor/6000.0.0f1/Unity.app/Contents/MacOS/Unity",
        project_path="/game/project",
        log_file="/game/project/.unity-agent/unity-editor.log",
    )

    assert command == [
        "/Applications/Unity/Hub/Editor/6000.0.0f1/Unity.app/Contents/MacOS/Unity",
        "-projectPath",
        "/game/project",
        "-logFile",
        "/game/project/.unity-agent/unity-editor.log",
    ]


def test_validate_project_path_accepts_directory_with_assets(tmp_path):
    project = tmp_path / "Game"
    (project / "Assets").mkdir(parents=True)
    (project / "Packages").mkdir()
    (project / "ProjectSettings").mkdir()

    assert validate_project_path(project) == project


def test_validate_project_path_rejects_non_unity_project(tmp_path):
    with pytest.raises(ValueError) as exc:
        validate_project_path(tmp_path)

    assert "does not look like a Unity project" in str(exc.value)
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests/test_editor.py -v
```

预期：测试失败，错误包含 `ModuleNotFoundError: No module named 'unityctl.editor'`。

- [ ] **Step 3: 实现 launcher helpers**

创建 `src/unityctl/unityctl/editor.py`：

```python
import subprocess
from pathlib import Path


def validate_project_path(project_path: str | Path) -> Path:
    project = Path(project_path).expanduser().resolve()
    required = ["Assets", "Packages", "ProjectSettings"]
    if not project.is_dir() or any(not (project / name).is_dir() for name in required):
        raise ValueError(f"{project} does not look like a Unity project")
    return project


def build_editor_command(
    unity_path: str,
    project_path: str | Path,
    log_file: str | Path,
) -> list[str]:
    project = str(Path(project_path).expanduser().resolve())
    log_path = str(Path(log_file).expanduser().resolve())
    return [
        unity_path,
        "-projectPath",
        project,
        "-logFile",
        log_path,
    ]


def start_editor(
    unity_path: str,
    project_path: str | Path,
    log_file: str | Path,
) -> subprocess.Popen:
    project = validate_project_path(project_path)
    command = build_editor_command(unity_path, project, log_file)
    return subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
```

- [ ] **Step 4: 运行 launcher tests**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests/test_editor.py -v
```

预期：`3 passed`。

- [ ] **Step 5: 提交**

Run:

```bash
git add src/unityctl/unityctl/editor.py src/unityctl/tests/test_editor.py
git commit -m "feat: add unity editor launcher"
```

预期：commit 成功。

## Task 3: 添加 CLI Commands

**Files:**
- Create: `src/unityctl/unityctl/cli.py`
- Create: `src/unityctl/tests/test_cli.py`

- [ ] **Step 1: 编写失败的 CLI tests**

创建 `src/unityctl/tests/test_cli.py`：

```python
import json

from unityctl import cli


class FakeClient:
    def __init__(self, base_url):
        self.base_url = base_url
        self.calls = []

    def get_status(self):
        self.calls.append(("status", None))
        return {"ok": True, "isPlaying": False}

    def post(self, path, payload=None):
        self.calls.append((path, payload))
        return {"ok": True, "command": path}

    def open_scene(self, scene_path):
        self.calls.append(("open-scene", {"scenePath": scene_path}))
        return {"ok": True, "scenePath": scene_path}


def test_status_command_prints_json(monkeypatch, capsys):
    clients = []

    def fake_client(base_url):
        client = FakeClient(base_url)
        clients.append(client)
        return client

    monkeypatch.setattr(cli, "BridgeClient", fake_client)

    exit_code = cli.main(["status"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "isPlaying": False}
    assert clients[0].calls == [("status", None)]


def test_play_command_posts_play(monkeypatch):
    clients = []

    def fake_client(base_url):
        client = FakeClient(base_url)
        clients.append(client)
        return client

    monkeypatch.setattr(cli, "BridgeClient", fake_client)

    assert cli.main(["play"]) == 0
    assert clients[0].calls == [("play", None)]


def test_open_scene_command_sends_path(monkeypatch):
    clients = []

    def fake_client(base_url):
        client = FakeClient(base_url)
        clients.append(client)
        return client

    monkeypatch.setattr(cli, "BridgeClient", fake_client)

    assert cli.main(["open-scene", "Assets/Scenes/Login.unity"]) == 0
    assert clients[0].calls == [
        ("open-scene", {"scenePath": "Assets/Scenes/Login.unity"})
    ]
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests/test_cli.py -v
```

预期：测试失败，原因是 `unityctl.cli` 不存在。

- [ ] **Step 3: 实现 CLI**

创建 `src/unityctl/unityctl/cli.py`：

```python
import argparse
import json
import sys
from pathlib import Path

from unityctl.client import BridgeClient, BridgeClientError
from unityctl.editor import start_editor


DEFAULT_BASE_URL = "http://127.0.0.1:17890"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="unityctl")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status")
    subparsers.add_parser("play")
    subparsers.add_parser("stop")
    subparsers.add_parser("pause")
    subparsers.add_parser("resume")

    open_scene = subparsers.add_parser("open-scene")
    open_scene.add_argument("scene_path")

    start = subparsers.add_parser("start-editor")
    start.add_argument("--unity", required=True, dest="unity_path")
    start.add_argument("--project", required=True, dest="project_path")
    start.add_argument(
        "--log-file",
        default=str(Path.home() / ".unity-agent" / "unity-editor.log"),
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "start-editor":
            Path(args.log_file).expanduser().parent.mkdir(parents=True, exist_ok=True)
            process = start_editor(args.unity_path, args.project_path, args.log_file)
            print_json({"ok": True, "pid": process.pid, "logFile": args.log_file})
            return 0

        client = BridgeClient(args.base_url)

        if args.command == "status":
            print_json(client.get_status())
            return 0
        if args.command == "play":
            print_json(client.post("play"))
            return 0
        if args.command == "stop":
            print_json(client.post("stop"))
            return 0
        if args.command == "pause":
            print_json(client.post("pause"))
            return 0
        if args.command == "resume":
            print_json(client.post("resume"))
            return 0
        if args.command == "open-scene":
            print_json(client.open_scene(args.scene_path))
            return 0

        parser.error(f"unsupported command: {args.command}")
        return 2
    except (BridgeClientError, ValueError) as exc:
        print_json({"ok": False, "error": str(exc)}, stream=sys.stderr)
        return 1


def print_json(payload: dict, stream=None) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream or sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行 CLI tests**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests/test_cli.py -v
```

预期：`3 passed`。

- [ ] **Step 5: 运行全部 Python tests**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests -v
```

预期：`10 passed`。

- [ ] **Step 6: 提交**

Run:

```bash
git add src/unityctl/unityctl/cli.py src/unityctl/tests/test_cli.py
git commit -m "feat: add unityctl commands"
```

预期：commit 成功。

## Task 4: 创建 Unity Bridge Package Manifest

**Files:**
- Create: `packages/com.elex.unity-agent-bridge/package.json`
- Create: `packages/com.elex.unity-agent-bridge/Editor/UnityAgentBridge.asmdef`
- Create: `packages/com.elex.unity-agent-bridge/Tests/Editor/UnityAgentBridge.Tests.asmdef`

- [ ] **Step 1: 创建 package manifest**

创建 `packages/com.elex.unity-agent-bridge/package.json`：

```json
{
  "name": "com.elex.unity-agent-bridge",
  "version": "0.1.0",
  "displayName": "Unity Agent Bridge",
  "description": "Editor-only localhost bridge for controlling Unity PlayMode from external agent tools.",
  "unity": "2021.3",
  "author": {
    "name": "Elex"
  }
}
```

- [ ] **Step 2: 创建 Editor assembly definition**

创建 `packages/com.elex.unity-agent-bridge/Editor/UnityAgentBridge.asmdef`：

```json
{
  "name": "Elex.UnityAgentBridge.Editor",
  "rootNamespace": "Elex.UnityAgentBridge.Editor",
  "references": [],
  "includePlatforms": [
    "Editor"
  ],
  "excludePlatforms": [],
  "allowUnsafeCode": false,
  "overrideReferences": false,
  "precompiledReferences": [],
  "autoReferenced": true,
  "defineConstraints": [],
  "versionDefines": [],
  "noEngineReferences": false
}
```

- [ ] **Step 3: 创建 test assembly definition**

创建 `packages/com.elex.unity-agent-bridge/Tests/Editor/UnityAgentBridge.Tests.asmdef`：

```json
{
  "name": "Elex.UnityAgentBridge.Editor.Tests",
  "rootNamespace": "Elex.UnityAgentBridge.Editor.Tests",
  "references": [
    "Elex.UnityAgentBridge.Editor"
  ],
  "includePlatforms": [
    "Editor"
  ],
  "excludePlatforms": [],
  "allowUnsafeCode": false,
  "overrideReferences": false,
  "precompiledReferences": [],
  "autoReferenced": false,
  "defineConstraints": [],
  "versionDefines": [],
  "noEngineReferences": false
}
```

- [ ] **Step 4: 校验 JSON 文件**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge
python3 -m json.tool packages/com.elex.unity-agent-bridge/package.json >/dev/null
python3 -m json.tool packages/com.elex.unity-agent-bridge/Editor/UnityAgentBridge.asmdef >/dev/null
python3 -m json.tool packages/com.elex.unity-agent-bridge/Tests/Editor/UnityAgentBridge.Tests.asmdef >/dev/null
```

预期：命令退出码为 `0`。

- [ ] **Step 5: 提交**

Run:

```bash
git add packages/com.elex.unity-agent-bridge/package.json packages/com.elex.unity-agent-bridge/Editor/UnityAgentBridge.asmdef packages/com.elex.unity-agent-bridge/Tests/Editor/UnityAgentBridge.Tests.asmdef
git commit -m "feat: add unity bridge package manifest"
```

预期：commit 成功。

## Task 5: 添加 Editor State DTOs

**Files:**
- Create: `packages/com.elex.unity-agent-bridge/Editor/BridgeConfig.cs`
- Create: `packages/com.elex.unity-agent-bridge/Editor/BridgeResponse.cs`
- Create: `packages/com.elex.unity-agent-bridge/Editor/EditorStateProvider.cs`
- Create: `packages/com.elex.unity-agent-bridge/Tests/Editor/EditorStateProviderTests.cs`

- [ ] **Step 1: 编写失败的 EditMode tests**

创建 `packages/com.elex.unity-agent-bridge/Tests/Editor/EditorStateProviderTests.cs`：

```csharp
using NUnit.Framework;

namespace Elex.UnityAgentBridge.Editor.Tests
{
    public sealed class EditorStateProviderTests
    {
        [Test]
        public void GetStatus_ReturnsBridgeStatus()
        {
            BridgeStatusResponse status = EditorStateProvider.GetStatus();

            Assert.IsTrue(status.ok);
            Assert.AreEqual("0.1.0", status.bridgeVersion);
            Assert.IsNotEmpty(status.unityVersion);
            Assert.IsNotNull(status.activeScenePath);
        }
    }
}
```

- [ ] **Step 2: 运行 Unity EditMode test 并确认失败**

在已引用 `packages/com.elex.unity-agent-bridge` 的 Unity project 中运行：

```bash
"/path/to/Unity" -batchmode -projectPath "/path/to/unity/project" -runTests -testPlatform EditMode -testResults ".tmp/test-results/unity-agent-bridge-editmode.xml"
```

预期：测试编译失败，原因是 `EditorStateProvider` 未定义。

- [ ] **Step 3: 添加 bridge config**

创建 `packages/com.elex.unity-agent-bridge/Editor/BridgeConfig.cs`：

```csharp
namespace Elex.UnityAgentBridge.Editor
{
    internal static class BridgeConfig
    {
        public const string Version = "0.1.0";
        public const string Host = "127.0.0.1";
        public const int Port = 17890;
        public const string Prefix = "http://127.0.0.1:17890/";
    }
}
```

- [ ] **Step 4: 添加 response DTOs**

创建 `packages/com.elex.unity-agent-bridge/Editor/BridgeResponse.cs`：

```csharp
using System;

namespace Elex.UnityAgentBridge.Editor
{
    [Serializable]
    public class BridgeResponse
    {
        public bool ok;
        public string message;
        public string error;

        public static BridgeResponse Success(string message)
        {
            return new BridgeResponse
            {
                ok = true,
                message = message,
                error = string.Empty
            };
        }

        public static BridgeResponse Failure(string error)
        {
            return new BridgeResponse
            {
                ok = false,
                message = string.Empty,
                error = error
            };
        }
    }

    [Serializable]
    public sealed class BridgeStatusResponse : BridgeResponse
    {
        public string bridgeVersion;
        public string unityVersion;
        public string activeScenePath;
        public bool isPlaying;
        public bool isPaused;
        public bool isCompiling;
        public bool isUpdating;
    }

    [Serializable]
    public sealed class OpenSceneRequest
    {
        public string scenePath;
    }
}
```

- [ ] **Step 5: 添加 Editor state provider**

创建 `packages/com.elex.unity-agent-bridge/Editor/EditorStateProvider.cs`：

```csharp
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Elex.UnityAgentBridge.Editor
{
    internal static class EditorStateProvider
    {
        public static BridgeStatusResponse GetStatus()
        {
            return new BridgeStatusResponse
            {
                ok = true,
                message = "ready",
                error = string.Empty,
                bridgeVersion = BridgeConfig.Version,
                unityVersion = Application.unityVersion,
                activeScenePath = EditorSceneManager.GetActiveScene().path,
                isPlaying = EditorApplication.isPlaying,
                isPaused = EditorApplication.isPaused,
                isCompiling = EditorApplication.isCompiling,
                isUpdating = EditorApplication.isUpdating
            };
        }
    }
}
```

- [ ] **Step 6: 运行 EditMode test**

在已引用 `packages/com.elex.unity-agent-bridge` 的 Unity project 中运行：

```bash
"/path/to/Unity" -batchmode -projectPath "/path/to/unity/project" -runTests -testPlatform EditMode -testResults ".tmp/test-results/unity-agent-bridge-editmode.xml"
```

预期：`EditorStateProviderTests.GetStatus_ReturnsBridgeStatus` 通过。

- [ ] **Step 7: 提交**

Run:

```bash
git add packages/com.elex.unity-agent-bridge/Editor/BridgeConfig.cs packages/com.elex.unity-agent-bridge/Editor/BridgeResponse.cs packages/com.elex.unity-agent-bridge/Editor/EditorStateProvider.cs packages/com.elex.unity-agent-bridge/Tests/Editor/EditorStateProviderTests.cs
git commit -m "feat: expose unity editor status"
```

预期：commit 成功。

## Task 6: 添加 PlayMode 和 Scene Controllers

**Files:**
- Create: `packages/com.elex.unity-agent-bridge/Editor/PlayModeController.cs`
- Create: `packages/com.elex.unity-agent-bridge/Editor/SceneController.cs`
- Create: `packages/com.elex.unity-agent-bridge/Tests/Editor/SceneControllerTests.cs`

- [ ] **Step 1: 编写失败的 scene validation tests**

创建 `packages/com.elex.unity-agent-bridge/Tests/Editor/SceneControllerTests.cs`：

```csharp
using NUnit.Framework;

namespace Elex.UnityAgentBridge.Editor.Tests
{
    public sealed class SceneControllerTests
    {
        [Test]
        public void IsValidProjectScenePath_AcceptsAssetsScene()
        {
            Assert.IsTrue(SceneController.IsValidProjectScenePath("Assets/Scenes/Login.unity"));
        }

        [Test]
        public void IsValidProjectScenePath_RejectsAbsolutePath()
        {
            Assert.IsFalse(SceneController.IsValidProjectScenePath("/tmp/Login.unity"));
        }

        [Test]
        public void IsValidProjectScenePath_RejectsNonSceneAsset()
        {
            Assert.IsFalse(SceneController.IsValidProjectScenePath("Assets/Scenes/Login.prefab"));
        }
    }
}
```

- [ ] **Step 2: 运行 Unity EditMode tests 并确认失败**

在已引用 `packages/com.elex.unity-agent-bridge` 的 Unity project 中运行：

```bash
"/path/to/Unity" -batchmode -projectPath "/path/to/unity/project" -runTests -testPlatform EditMode -testResults ".tmp/test-results/unity-agent-bridge-editmode.xml"
```

预期：测试编译失败，原因是 `SceneController` 未定义。

- [ ] **Step 3: 添加 PlayMode controller**

创建 `packages/com.elex.unity-agent-bridge/Editor/PlayModeController.cs`：

```csharp
using UnityEditor;

namespace Elex.UnityAgentBridge.Editor
{
    internal static class PlayModeController
    {
        public static BridgeResponse EnterPlayMode()
        {
            if (EditorApplication.isPlaying)
            {
                return BridgeResponse.Success("already in play mode");
            }

            if (EditorApplication.isCompiling || EditorApplication.isUpdating)
            {
                return BridgeResponse.Failure("editor is compiling or updating");
            }

            EditorApplication.isPlaying = true;
            return BridgeResponse.Success("entering play mode");
        }

        public static BridgeResponse ExitPlayMode()
        {
            if (!EditorApplication.isPlaying)
            {
                return BridgeResponse.Success("already stopped");
            }

            EditorApplication.isPlaying = false;
            return BridgeResponse.Success("exiting play mode");
        }

        public static BridgeResponse Pause()
        {
            if (!EditorApplication.isPlaying)
            {
                return BridgeResponse.Failure("cannot pause when editor is not in play mode");
            }

            EditorApplication.isPaused = true;
            return BridgeResponse.Success("paused");
        }

        public static BridgeResponse Resume()
        {
            if (!EditorApplication.isPlaying)
            {
                return BridgeResponse.Failure("cannot resume when editor is not in play mode");
            }

            EditorApplication.isPaused = false;
            return BridgeResponse.Success("resumed");
        }
    }
}
```

- [ ] **Step 4: 添加 scene controller**

创建 `packages/com.elex.unity-agent-bridge/Editor/SceneController.cs`：

```csharp
using System;
using UnityEditor.SceneManagement;

namespace Elex.UnityAgentBridge.Editor
{
    internal static class SceneController
    {
        public static BridgeResponse OpenScene(string scenePath)
        {
            if (!IsValidProjectScenePath(scenePath))
            {
                return BridgeResponse.Failure("scenePath must be a Unity scene under Assets");
            }

            try
            {
                EditorSceneManager.OpenScene(scenePath);
                return BridgeResponse.Success("scene opened");
            }
            catch (Exception ex)
            {
                return BridgeResponse.Failure(ex.Message);
            }
        }

        public static bool IsValidProjectScenePath(string scenePath)
        {
            if (string.IsNullOrWhiteSpace(scenePath))
            {
                return false;
            }

            string normalized = scenePath.Replace('\\', '/');
            return normalized.StartsWith("Assets/", StringComparison.Ordinal)
                && normalized.EndsWith(".unity", StringComparison.OrdinalIgnoreCase)
                && !normalized.Contains("../", StringComparison.Ordinal);
        }
    }
}
```

- [ ] **Step 5: 运行 Unity EditMode tests**

在已引用 `packages/com.elex.unity-agent-bridge` 的 Unity project 中运行：

```bash
"/path/to/Unity" -batchmode -projectPath "/path/to/unity/project" -runTests -testPlatform EditMode -testResults ".tmp/test-results/unity-agent-bridge-editmode.xml"
```

预期：`EditorStateProviderTests` 和 `SceneControllerTests` 都通过。

- [ ] **Step 6: 提交**

Run:

```bash
git add packages/com.elex.unity-agent-bridge/Editor/PlayModeController.cs packages/com.elex.unity-agent-bridge/Editor/SceneController.cs packages/com.elex.unity-agent-bridge/Tests/Editor/SceneControllerTests.cs
git commit -m "feat: add play mode and scene controllers"
```

预期：commit 成功。

## Task 7: 添加 Unity HTTP Bridge Server

**Files:**
- Create: `packages/com.elex.unity-agent-bridge/Editor/BridgeServer.cs`

- [ ] **Step 1: 添加 bridge server**

创建 `packages/com.elex.unity-agent-bridge/Editor/BridgeServer.cs`：

```csharp
using System;
using System.Collections.Concurrent;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;
using UnityEditor;
using UnityEngine;

namespace Elex.UnityAgentBridge.Editor
{
    [InitializeOnLoad]
    internal static class BridgeServer
    {
        private static readonly ConcurrentQueue<QueuedRequest> PendingRequests = new ConcurrentQueue<QueuedRequest>();
        private static HttpListener listener;
        private static Thread listenerThread;
        private static bool isRunning;

        static BridgeServer()
        {
            EditorApplication.update += ProcessPendingRequests;
            AssemblyReloadEvents.beforeAssemblyReload += Stop;
            EditorApplication.quitting += Stop;
            Start();
        }

        public static void Start()
        {
            if (isRunning)
            {
                return;
            }

            try
            {
                listener = new HttpListener();
                listener.Prefixes.Add(BridgeConfig.Prefix);
                listener.Start();
                isRunning = true;

                listenerThread = new Thread(ListenLoop)
                {
                    IsBackground = true,
                    Name = "UnityAgentBridgeServer"
                };
                listenerThread.Start();

                Debug.Log($"Unity Agent Bridge listening on {BridgeConfig.Prefix}");
            }
            catch (HttpListenerException ex)
            {
                Debug.LogWarning($"Unity Agent Bridge could not start: {ex.Message}");
                isRunning = false;
            }
        }

        public static void Stop()
        {
            isRunning = false;

            EditorApplication.update -= ProcessPendingRequests;
            AssemblyReloadEvents.beforeAssemblyReload -= Stop;
            EditorApplication.quitting -= Stop;

            if (listener != null)
            {
                listener.Stop();
                listener.Close();
                listener = null;
            }
        }

        private static void ListenLoop()
        {
            while (isRunning && listener != null && listener.IsListening)
            {
                try
                {
                    HttpListenerContext context = listener.GetContext();
                    HandleContext(context);
                }
                catch (HttpListenerException)
                {
                    isRunning = false;
                }
                catch (ObjectDisposedException)
                {
                    isRunning = false;
                }
            }
        }

        private static void HandleContext(HttpListenerContext context)
        {
            QueuedRequest request = new QueuedRequest(context);
            PendingRequests.Enqueue(request);

            if (!request.Completed.WaitOne(TimeSpan.FromSeconds(30)))
            {
                request.TimedOut = true;
                WriteJson(context.Response, 504, BridgeResponse.Failure("bridge request timed out"));
                return;
            }

            WriteJson(context.Response, request.StatusCode, request.Payload);
        }

        private static void ProcessPendingRequests()
        {
            while (PendingRequests.TryDequeue(out QueuedRequest request))
            {
                if (request.TimedOut)
                {
                    request.Completed.Set();
                    continue;
                }

                try
                {
                    request.StatusCode = 200;
                    request.Payload = Route(request.Context.Request);
                }
                catch (Exception ex)
                {
                    request.StatusCode = 500;
                    request.Payload = BridgeResponse.Failure(ex.Message);
                }
                finally
                {
                    request.Completed.Set();
                }
            }
        }

        private static object Route(HttpListenerRequest request)
        {
            string method = request.HttpMethod.ToUpperInvariant();
            string path = request.Url.AbsolutePath.Trim('/').ToLowerInvariant();

            if (method == "GET" && path == "status")
            {
                return EditorStateProvider.GetStatus();
            }

            if (method == "POST" && path == "play")
            {
                return PlayModeController.EnterPlayMode();
            }

            if (method == "POST" && path == "stop")
            {
                return PlayModeController.ExitPlayMode();
            }

            if (method == "POST" && path == "pause")
            {
                return PlayModeController.Pause();
            }

            if (method == "POST" && path == "resume")
            {
                return PlayModeController.Resume();
            }

            if (method == "POST" && path == "open-scene")
            {
                string body = ReadBody(request);
                OpenSceneRequest sceneRequest = JsonUtility.FromJson<OpenSceneRequest>(body);
                return SceneController.OpenScene(sceneRequest == null ? string.Empty : sceneRequest.scenePath);
            }

            return BridgeResponse.Failure($"unsupported route: {method} /{path}");
        }

        private static string ReadBody(HttpListenerRequest request)
        {
            using StreamReader reader = new StreamReader(request.InputStream, request.ContentEncoding);
            return reader.ReadToEnd();
        }

        private static void WriteJson(HttpListenerResponse response, int statusCode, object payload)
        {
            string json = JsonUtility.ToJson(payload);
            byte[] bytes = Encoding.UTF8.GetBytes(json);
            response.StatusCode = statusCode;
            response.ContentType = "application/json";
            response.ContentEncoding = Encoding.UTF8;
            response.ContentLength64 = bytes.Length;
            response.OutputStream.Write(bytes, 0, bytes.Length);
            response.OutputStream.Close();
        }

        private sealed class QueuedRequest
        {
            public readonly HttpListenerContext Context;
            public readonly ManualResetEvent Completed = new ManualResetEvent(false);
            public volatile bool TimedOut;
            public int StatusCode = 200;
            public object Payload = BridgeResponse.Success("ok");

            public QueuedRequest(HttpListenerContext context)
            {
                Context = context;
            }
        }
    }
}
```

- [ ] **Step 2: 编译 Unity package**

在已引用 `packages/com.elex.unity-agent-bridge` 的 Unity project 中运行：

```bash
"/path/to/Unity" -batchmode -projectPath "/path/to/unity/project" -quit -logFile ".tmp/logs/unity-agent-bridge-compile.log"
```

预期：Unity 退出码为 `0`，并且 `.tmp/logs/unity-agent-bridge-compile.log` 中没有 `error CS`。

- [ ] **Step 3: 手动验证 bridge status**

正常打开 Unity project，等待脚本编译完成，然后运行：

```bash
curl -s http://127.0.0.1:17890/status
```

预期返回类似 JSON：

```json
{
  "ok": true,
  "message": "ready",
  "error": "",
  "bridgeVersion": "0.1.0",
  "unityVersion": "6000.0.0f1",
  "activeScenePath": "Assets/Scenes/Login.unity",
  "isPlaying": false,
  "isPaused": false,
  "isCompiling": false,
  "isUpdating": false
}
```

- [ ] **Step 4: 手动验证 PlayMode commands**

Run:

```bash
curl -s -X POST http://127.0.0.1:17890/play -d '{}'
curl -s http://127.0.0.1:17890/status
curl -s -X POST http://127.0.0.1:17890/pause -d '{}'
curl -s -X POST http://127.0.0.1:17890/resume -d '{}'
curl -s -X POST http://127.0.0.1:17890/stop -d '{}'
```

预期：

- `/play` 返回 `{"ok":true,"message":"entering play mode","error":""}` 或 `{"ok":true,"message":"already in play mode","error":""}`。
- `/status` 最终显示 `"isPlaying":true`。
- `/pause` 返回 `{"ok":true,"message":"paused","error":""}`。
- `/resume` 返回 `{"ok":true,"message":"resumed","error":""}`。
- `/stop` 返回 `{"ok":true,"message":"exiting play mode","error":""}` 或 `{"ok":true,"message":"already stopped","error":""}`。

- [ ] **Step 5: 提交**

Run:

```bash
git add packages/com.elex.unity-agent-bridge/Editor/BridgeServer.cs
git commit -m "feat: add unity editor http bridge"
```

预期：commit 成功。

## Task 8: 添加 README 和端到端 Smoke Test

**Files:**
- Create: `README.md`

- [ ] **Step 1: 创建 README**

创建 `README.md`：

````markdown
# Unity Agent Bridge

Unity Agent Bridge 是一个低侵入的 Unity 运行控制工具。它让外部 agent 和人类用户可以通过 localhost HTTP Bridge 与 CLI 控制一个已打开的 Unity Editor。

## 第一版范围

- 单 Unity 项目
- 单 Unity Editor 实例
- 固定 Bridge 地址：`http://127.0.0.1:17890`
- 命令：`status`、`play`、`stop`、`pause`、`resume`、`open-scene`、`start-editor`

## 安装 Unity Package

在 Unity project 的 `Packages/manifest.json` 中添加：

```json
{
  "dependencies": {
    "com.elex.unity-agent-bridge": "file:/Users/elex-mb0203/MyWork/my_github/UnityRunBridge/packages/com.elex.unity-agent-bridge"
  }
}
```

打开 Unity project，并等待编译完成。Bridge 会自动启动并监听：

```text
http://127.0.0.1:17890
```

## 安装开发版 CLI

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv sync
```

## CLI 示例

```bash
uv run unityctl status
uv run unityctl play
uv run unityctl pause
uv run unityctl resume
uv run unityctl stop
uv run unityctl open-scene Assets/Scenes/Login.unity
```

启动一个 Unity Editor 进程：

```bash
uv run unityctl start-editor \
  --unity "/Applications/Unity/Hub/Editor/6000.0.0f1/Unity.app/Contents/MacOS/Unity" \
  --project "/path/to/unity/project"
```

## Agent 调用约定

外部 coding agent 优先调用 CLI。成功时 CLI 向 stdout 输出 JSON，失败时向 stderr 输出 JSON。

成功示例：

```json
{
  "ok": true,
  "message": "entering play mode"
}
```

失败示例：

```json
{
  "ok": false,
  "error": "Cannot reach Unity bridge: Connection refused"
}
```
````

- [ ] **Step 2: 运行全部 Python tests**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests -v
```

预期：`10 passed`。

- [ ] **Step 3: 对已打开的 Unity Editor 运行 CLI smoke test**

在 Unity project 已打开、且 Bridge package 已安装的前提下运行：

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv sync
uv run unityctl status
uv run unityctl play
uv run unityctl pause
uv run unityctl resume
uv run unityctl stop
```

预期：

- 每条命令退出码都是 `0`。
- 每条命令都输出包含 `"ok": true` 的 JSON。
- `unityctl play` 后 Unity Editor 进入 PlayMode。
- `unityctl stop` 后 Unity Editor 离开 PlayMode。

- [ ] **Step 4: 提交**

Run:

```bash
git add README.md
git commit -m "docs: add unity agent bridge usage"
```

预期：commit 成功。

## Self-Review

需求覆盖：

- 单 Unity 项目：通过固定 URL 和不做 discovery 体现。
- 低侵入 Unity 集成：通过 Editor-only UPM package 体现。
- 启动 Editor：由 `unityctl start-editor` 覆盖。
- Play/stop/pause/resume：由 Bridge routes 和 CLI commands 覆盖。
- 打开 scene：由 `/open-scene` 和 `unityctl open-scene` 覆盖。
- Agent-friendly interface：由 JSON CLI 输出和 HTTP routes 覆盖。

占位符扫描：

- 文档中没有未解决的占位符标记。
- 每个 task 都给出了明确文件、命令、预期结果和 commit message。

类型一致性：

- Python 命名一致：`BridgeClient`、`BridgeClientError`、`build_editor_command`、`validate_project_path`、`start_editor`。
- C# 命名一致：`BridgeConfig`、`BridgeResponse`、`BridgeStatusResponse`、`EditorStateProvider`、`PlayModeController`、`SceneController`、`BridgeServer`。

## 执行交接

计划已保存到 `docs/superpowers/plans/2026-06-30-unity-editor-control.md`。有两种执行方式：

1. **Subagent-Driven（推荐）**：每个 task 派一个 fresh subagent，任务之间进行 review，迭代更快。
2. **Inline Execution**：在当前会话中使用 `superpowers:executing-plans` 执行，按 checkpoint 分批 review。

请选择执行方式。
