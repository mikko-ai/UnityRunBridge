# unityctl Global Init Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `unityctl` usable as a global command with project-local initialization and configuration, so users can run it from a Unity project without repeatedly passing Unity paths, project paths, and Bridge URLs.

**Architecture:** Add a Python config/discovery layer that finds the Unity project root, reads `.unity-agent/config.json` and `.unity-agent/config.local.json`, and resolves an effective runtime configuration. Add `unityctl init`, `unityctl config`, `unityctl start`, project-aware command defaults, and `--latest` session lookup. Update the Unity Editor package so `BridgeServer` reads the project-local Bridge host/port from `.unity-agent/config.json` before starting `HttpListener`.

**Tech Stack:** Python 3.11+, `uv`, `argparse`, `urllib.request`, `pytest`, Unity Editor C#, `JsonUtility`, Unity EditMode tests.

---

## Source Design

This plan implements:

- `docs/design/unityctl-global-init-config.md`

Key decisions from the design:

- Python package / uv tool package name becomes `unity-run-bridge`.
- Installed executable command stays `unityctl`.
- Python import package stays `unityctl`.
- `unityctl init` is the project entry point.
- Project config lives at the Unity project root, for example `Game/.unity-agent/config.json`.
- Machine-local config lives at the Unity project root, for example `Game/.unity-agent/config.local.json`.
- `config.json` can be committed; `config.local.json` and `sessions/` should be ignored.
- Bridge host/port are project config, not global config.

## File Structure

Create:

- `src/unityctl/unityctl/config.py`
  Unity project discovery, config read/write, effective config resolution, Bridge URL construction, latest session lookup, and `.gitignore` append helper.

- `src/unityctl/tests/test_config.py`
  Unit tests for project discovery, config writing/loading, Unity executable normalization, Bridge URL construction, local config precedence, `.gitignore` append behavior, and latest session lookup.

- `packages/com.elex.unity-agent-bridge/Editor/BridgeProjectConfig.cs`
  Unity-side reader for `.unity-agent/config.json`, plus helpers to parse host/port and build the `HttpListener` prefix.

- `packages/com.elex.unity-agent-bridge/Editor/BridgeProjectConfig.cs.meta`
  Unity-generated meta file.

- `packages/com.elex.unity-agent-bridge/Tests/Editor/BridgeProjectConfigTests.cs`
  EditMode tests for Unity-side config parsing and prefix fallback behavior.

- `packages/com.elex.unity-agent-bridge/Tests/Editor/BridgeProjectConfigTests.cs.meta`
  Unity-generated meta file.

- `schemas/unity-agent-config.schema.json`
  JSON Schema for `.unity-agent/config.json`.

- `examples/unity-agent-config/config.json`
  Example commit-safe project config.

- `examples/unity-agent-config/config.local.json`
  Example machine-local config.

Modify:

- `src/unityctl/pyproject.toml`
  Rename Python package metadata from `unityctl` to `unity-run-bridge`; keep `[project.scripts].unityctl`.

- `src/unityctl/tests/test_cli.py`
  Tests for `init`, `config show`, `config set-local`, `start`, project-aware `play`, `stop`, `summary --latest`, `logs --latest`, and `errors --latest`.

- `src/unityctl/tests/test_editor.py`
  Tests for `.app` path normalization and command construction through resolved config.

- `src/unityctl/unityctl/editor.py`
  Add Unity executable path normalization while preserving current `start_editor` behavior.

- `src/unityctl/unityctl/cli.py`
  Add global `--project`, `init`, `config`, `start`, config-aware Bridge client creation, and `--latest` session path resolution.

- `packages/com.elex.unity-agent-bridge/Editor/BridgeConfig.cs`
  Replace hardcoded `Host`, `Port`, `Prefix` constants with defaults and runtime-loaded properties.

- `packages/com.elex.unity-agent-bridge/Editor/BridgeServer.cs`
  Use the resolved runtime prefix and log it.

- `README.md`
  Document global install, `unityctl init`, project config, and simplified daily commands.

- `scripts/run-python-tests.sh`
  Keep working after package rename.

- `scripts/run-unity-editmode-tests.sh`
  Keep working with Bridge config fallback.

## Task 1: Rename Python Package Metadata While Keeping `unityctl` Command

**Files:**
- Modify: `src/unityctl/pyproject.toml`
- Create: `src/unityctl/tests/test_packaging.py`

- [ ] **Step 1: Write the failing packaging test**

Create `src/unityctl/tests/test_packaging.py`:

```python
import tomllib
from pathlib import Path


def test_python_package_name_is_specific_but_command_stays_unityctl():
    payload = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert payload["project"]["name"] == "unity-run-bridge"
    assert payload["project"]["scripts"] == {"unityctl": "unityctl.cli:main"}
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests/test_packaging.py -v
```

Expected: fails because `payload["project"]["name"]` is currently `"unityctl"`.

- [ ] **Step 3: Update `pyproject.toml`**

Change:

```toml
[project]
name = "unityctl"
```

to:

```toml
[project]
name = "unity-run-bridge"
```

Keep:

```toml
[project.scripts]
unityctl = "unityctl.cli:main"
```

- [ ] **Step 4: Refresh lockfile**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv lock
```

Expected: `uv.lock` updates package metadata from `unityctl` to `unity-run-bridge`.

- [ ] **Step 5: Run packaging test**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests/test_packaging.py -v
```

Expected: `1 passed`.

- [ ] **Step 6: Run all Python tests**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

Run:

```bash
git add src/unityctl/pyproject.toml src/unityctl/uv.lock src/unityctl/tests/test_packaging.py
git commit -m "chore: rename python package metadata"
```

Expected: commit succeeds.

## Task 2: Add Python Project Discovery and Config Model

**Files:**
- Create: `src/unityctl/unityctl/config.py`
- Create: `src/unityctl/tests/test_config.py`

- [ ] **Step 1: Write failing config tests**

Create `src/unityctl/tests/test_config.py`:

```python
import json
from pathlib import Path

import pytest

from unityctl.config import (
    ConfigError,
    append_gitignore_entry,
    build_bridge_url,
    find_latest_session_path,
    find_unity_project_root,
    init_project_config,
    normalize_unity_executable_path,
    resolve_effective_config,
)


def make_unity_project(path: Path) -> Path:
    (path / "Assets").mkdir(parents=True)
    (path / "Packages").mkdir()
    (path / "ProjectSettings").mkdir()
    return path


def test_find_unity_project_root_walks_up_from_child(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    child = project / "Assets" / "Scripts"
    child.mkdir(parents=True)

    assert find_unity_project_root(child) == project


def test_find_unity_project_root_raises_when_missing(tmp_path):
    with pytest.raises(ConfigError) as exc:
        find_unity_project_root(tmp_path)

    assert "Unity project" in str(exc.value)


def test_init_project_config_writes_shared_and_local_config(tmp_path):
    project = make_unity_project(tmp_path / "Game")

    result = init_project_config(
        project_path=project,
        unity_path="/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app",
        unity_version="2022.3.62f2",
        host="127.0.0.1",
        port=17891,
        default_scene="Assets/Scenes/Login.unity",
    )

    shared = json.loads((project / ".unity-agent" / "config.json").read_text())
    local = json.loads((project / ".unity-agent" / "config.local.json").read_text())
    assert result.project_path == project
    assert shared == {
        "version": 1,
        "unityVersion": "2022.3.62f2",
        "bridge": {"host": "127.0.0.1", "port": 17891},
        "defaultScene": "Assets/Scenes/Login.unity",
        "sessionDirectory": ".unity-agent/sessions",
    }
    assert local == {
        "unityAppPath": "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app"
    }


def test_append_gitignore_entry_adds_missing_line_once(tmp_path):
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("Library/\n", encoding="utf-8")

    append_gitignore_entry(gitignore, ".unity-agent/config.local.json")
    append_gitignore_entry(gitignore, ".unity-agent/config.local.json")

    assert gitignore.read_text(encoding="utf-8").splitlines() == [
        "Library/",
        ".unity-agent/config.local.json",
    ]


def test_resolve_effective_config_merges_project_and_local_config(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    init_project_config(
        project_path=project,
        unity_path="/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app",
        unity_version="2022.3.62f2",
        host="127.0.0.1",
        port=17891,
        default_scene=None,
    )

    config = resolve_effective_config(project_path=project)

    assert config.project_path == project
    assert config.bridge_url == "http://127.0.0.1:17891"
    assert config.unity_version == "2022.3.62f2"
    assert config.unity_app_path == Path(
        "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app"
    )
    assert config.unity_executable_path == Path(
        "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity"
    )


def test_resolve_effective_config_allows_cli_overrides(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    init_project_config(
        project_path=project,
        unity_path="/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app",
        unity_version="2022.3.62f2",
        host="127.0.0.1",
        port=17891,
        default_scene=None,
    )

    config = resolve_effective_config(
        project_path=project,
        unity_path="/Applications/Unity/Hub/Editor/6000.0.0f1/Unity.app",
        base_url="http://127.0.0.1:19000",
    )

    assert config.bridge_url == "http://127.0.0.1:19000"
    assert config.unity_executable_path == Path(
        "/Applications/Unity/Hub/Editor/6000.0.0f1/Unity.app/Contents/MacOS/Unity"
    )


def test_normalize_unity_executable_path_accepts_app_bundle():
    assert normalize_unity_executable_path(
        "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app"
    ) == Path("/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity")


def test_build_bridge_url_uses_host_and_port():
    assert build_bridge_url("127.0.0.1", 17891) == "http://127.0.0.1:17891"


def test_find_latest_session_path_uses_session_directory_name(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    old_session = project / ".unity-agent" / "sessions" / "2026-07-01_100000_old"
    new_session = project / ".unity-agent" / "sessions" / "2026-07-02_100000_new"
    old_session.mkdir(parents=True)
    new_session.mkdir(parents=True)

    assert find_latest_session_path(project) == new_session
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests/test_config.py -v
```

Expected: fails with `ModuleNotFoundError: No module named 'unityctl.config'`.

- [ ] **Step 3: Implement `config.py`**

Create `src/unityctl/unityctl/config.py`:

```python
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_BRIDGE_HOST = "127.0.0.1"
DEFAULT_BRIDGE_PORT = 17890
DEFAULT_SESSION_DIRECTORY = ".unity-agent/sessions"


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class InitResult:
    project_path: Path
    config_path: Path
    local_config_path: Path
    bridge_url: str
    package_installed: bool


@dataclass(frozen=True)
class EffectiveConfig:
    project_path: Path
    project_config_path: Path
    local_config_path: Path
    bridge_url: str
    bridge_host: str
    bridge_port: int
    unity_version: str | None
    unity_app_path: Path | None
    unity_executable_path: Path | None
    default_scene: str | None
    session_directory: Path


def find_unity_project_root(start: str | Path) -> Path:
    current = Path(start).expanduser().resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if is_unity_project_root(candidate):
            return candidate
    raise ConfigError(f"Could not find Unity project root from {current}")


def is_unity_project_root(path: Path) -> bool:
    return all((path / name).is_dir() for name in ["Assets", "Packages", "ProjectSettings"])


def build_bridge_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def normalize_unity_executable_path(unity_path: str | Path | None) -> Path | None:
    if unity_path is None:
        return None
    path = Path(unity_path).expanduser()
    if path.suffix == ".app":
        return path / "Contents" / "MacOS" / "Unity"
    return path


def normalize_unity_app_path(unity_path: str | Path | None) -> Path | None:
    if unity_path is None:
        return None
    path = Path(unity_path).expanduser()
    if path.name == "Unity" and path.parent.name == "MacOS":
        return path.parents[2]
    return path


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def init_project_config(
    project_path: str | Path,
    unity_path: str | Path | None,
    unity_version: str | None,
    host: str = DEFAULT_BRIDGE_HOST,
    port: int = DEFAULT_BRIDGE_PORT,
    default_scene: str | None = None,
) -> InitResult:
    project = find_unity_project_root(project_path)
    agent_dir = project / ".unity-agent"
    config_path = agent_dir / "config.json"
    local_config_path = agent_dir / "config.local.json"
    existing = read_json(config_path)
    local_existing = read_json(local_config_path)

    payload = {
        "version": 1,
        "unityVersion": unity_version or existing.get("unityVersion"),
        "bridge": {
            "host": host,
            "port": port,
        },
        "defaultScene": default_scene,
        "sessionDirectory": existing.get("sessionDirectory", DEFAULT_SESSION_DIRECTORY),
    }
    write_json(config_path, payload)

    unity_app_path = normalize_unity_app_path(unity_path)
    local_payload = dict(local_existing)
    if unity_app_path is not None:
        local_payload["unityAppPath"] = str(unity_app_path)
    write_json(local_config_path, local_payload)

    gitignore_path = project / ".gitignore"
    append_gitignore_entry(gitignore_path, ".unity-agent/config.local.json")
    append_gitignore_entry(gitignore_path, ".unity-agent/sessions/")

    return InitResult(
        project_path=project,
        config_path=config_path,
        local_config_path=local_config_path,
        bridge_url=build_bridge_url(host, port),
        package_installed=is_bridge_package_installed(project),
    )


def resolve_effective_config(
    start_path: str | Path | None = None,
    project_path: str | Path | None = None,
    unity_path: str | Path | None = None,
    base_url: str | None = None,
) -> EffectiveConfig:
    project = find_unity_project_root(project_path or start_path or Path.cwd())
    config_path = project / ".unity-agent" / "config.json"
    local_config_path = project / ".unity-agent" / "config.local.json"
    shared = read_json(config_path)
    local = read_json(local_config_path)
    bridge = shared.get("bridge", {})
    host = str(bridge.get("host", DEFAULT_BRIDGE_HOST))
    port = int(bridge.get("port", DEFAULT_BRIDGE_PORT))
    unity_version = shared.get("unityVersion")
    selected_unity_path = unity_path or local.get("unityExecutablePath") or local.get("unityAppPath")
    unity_app_path = normalize_unity_app_path(selected_unity_path)
    unity_executable_path = normalize_unity_executable_path(selected_unity_path)
    session_directory = project / str(shared.get("sessionDirectory", DEFAULT_SESSION_DIRECTORY))

    return EffectiveConfig(
        project_path=project,
        project_config_path=config_path,
        local_config_path=local_config_path,
        bridge_url=base_url or build_bridge_url(host, port),
        bridge_host=host,
        bridge_port=port,
        unity_version=unity_version,
        unity_app_path=unity_app_path,
        unity_executable_path=unity_executable_path,
        default_scene=shared.get("defaultScene"),
        session_directory=session_directory,
    )


def append_gitignore_entry(gitignore_path: str | Path, entry: str) -> None:
    path = Path(gitignore_path)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    if entry not in lines:
        lines.append(entry)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def is_bridge_package_installed(project_path: str | Path) -> bool:
    manifest = Path(project_path) / "Packages" / "manifest.json"
    if not manifest.exists():
        return False
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    dependencies = payload.get("dependencies", {})
    return "com.elex.unity-agent-bridge" in dependencies


def find_latest_session_path(project_path: str | Path) -> Path:
    project = find_unity_project_root(project_path)
    sessions = project / DEFAULT_SESSION_DIRECTORY
    candidates = sorted(path for path in sessions.iterdir() if path.is_dir()) if sessions.exists() else []
    if not candidates:
        raise ConfigError(f"No sessions found under {sessions}")
    return candidates[-1]
```

- [ ] **Step 4: Run config tests**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests/test_config.py -v
```

Expected: all `test_config.py` tests pass.

- [ ] **Step 5: Run all Python tests**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/unityctl/unityctl/config.py src/unityctl/tests/test_config.py
git commit -m "feat: add unity project config model"
```

Expected: commit succeeds.

## Task 3: Add `unityctl init` and `unityctl config`

**Files:**
- Modify: `src/unityctl/unityctl/cli.py`
- Modify: `src/unityctl/tests/test_cli.py`

- [ ] **Step 1: Add failing CLI tests**

Append to `src/unityctl/tests/test_cli.py`:

```python
from pathlib import Path


def make_unity_project(path: Path) -> Path:
    (path / "Assets").mkdir(parents=True)
    (path / "Packages").mkdir()
    (path / "ProjectSettings").mkdir()
    return path


def test_init_command_writes_project_and_local_config(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")

    exit_code = cli.main(
        [
            "--project",
            str(project),
            "init",
            "--unity",
            "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app",
            "--unity-version",
            "2022.3.62f2",
            "--port",
            "17891",
            "--scene",
            "Assets/Scenes/Login.unity",
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["projectPath"] == str(project)
    assert output["bridgeUrl"] == "http://127.0.0.1:17891"
    assert (project / ".unity-agent" / "config.json").exists()
    assert (project / ".unity-agent" / "config.local.json").exists()
    assert ".unity-agent/config.local.json" in (project / ".gitignore").read_text()


def test_config_show_prints_effective_config(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    cli.main(
        [
            "--project",
            str(project),
            "init",
            "--unity",
            "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app",
            "--unity-version",
            "2022.3.62f2",
            "--port",
            "17891",
        ]
    )
    capsys.readouterr()

    exit_code = cli.main(["--project", str(project), "config", "show"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["bridgeUrl"] == "http://127.0.0.1:17891"
    assert output["unityVersion"] == "2022.3.62f2"
    assert output["unityExecutablePath"].endswith("Unity.app/Contents/MacOS/Unity")


def test_config_set_local_updates_local_config(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    cli.main(["--project", str(project), "init", "--unity-version", "2022.3.62f2"])
    capsys.readouterr()

    exit_code = cli.main(
        [
            "--project",
            str(project),
            "config",
            "set-local",
            "unityAppPath",
            "/Applications/Unity/Hub/Editor/6000.0.0f1/Unity.app",
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["unityAppPath"] == "/Applications/Unity/Hub/Editor/6000.0.0f1/Unity.app"
```

- [ ] **Step 2: Run CLI tests and verify they fail**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests/test_cli.py -v
```

Expected: failures because `--project`, `init`, and `config` are not implemented.

- [ ] **Step 3: Update CLI imports**

In `src/unityctl/unityctl/cli.py`, add:

```python
from unityctl.config import (
    ConfigError,
    init_project_config,
    read_json,
    resolve_effective_config,
    write_json,
)
```

- [ ] **Step 4: Add global `--project` and init/config parsers**

In `build_parser()`, change:

```python
parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
```

to:

```python
parser.add_argument("--base-url")
parser.add_argument("--project", dest="project_path")
```

Then add subcommands before `return parser`:

```python
init = subparsers.add_parser("init")
init.add_argument("--unity", dest="unity_path")
init.add_argument("--unity-version")
init.add_argument("--host", default="127.0.0.1")
init.add_argument("--port", type=int, default=17890)
init.add_argument("--scene", dest="default_scene")
init.add_argument("--install-package", action="store_true")

config = subparsers.add_parser("config")
config_subparsers = config.add_subparsers(dest="config_command", required=True)
config_subparsers.add_parser("show")
set_local = config_subparsers.add_parser("set-local")
set_local.add_argument("key")
set_local.add_argument("value")
```

- [ ] **Step 5: Implement `init` and `config` handling**

In `main()`, add these branches before creating a `BridgeClient`:

```python
        if args.command == "init":
            result = init_project_config(
                project_path=args.project_path or Path.cwd(),
                unity_path=args.unity_path,
                unity_version=args.unity_version,
                host=args.host,
                port=args.port,
                default_scene=args.default_scene,
            )
            print_json(
                {
                    "ok": True,
                    "projectPath": str(result.project_path),
                    "configPath": str(result.config_path),
                    "localConfigPath": str(result.local_config_path),
                    "bridgeUrl": result.bridge_url,
                    "packageInstalled": result.package_installed,
                    "nextSteps": [
                        "Add com.elex.unity-agent-bridge to Packages/manifest.json",
                        "Run unityctl start",
                        "Run unityctl status",
                    ],
                }
            )
            return 0

        if args.command == "config":
            effective = resolve_effective_config(
                project_path=args.project_path,
                base_url=args.base_url,
            )
            if args.config_command == "show":
                print_json(
                    {
                        "ok": True,
                        "projectPath": str(effective.project_path),
                        "bridgeUrl": effective.bridge_url,
                        "unityVersion": effective.unity_version,
                        "unityExecutablePath": (
                            str(effective.unity_executable_path)
                            if effective.unity_executable_path
                            else None
                        ),
                        "sources": {
                            "projectConfig": str(effective.project_config_path),
                            "localConfig": str(effective.local_config_path),
                        },
                    }
                )
                return 0
            if args.config_command == "set-local":
                payload = read_json(effective.local_config_path)
                payload[args.key] = args.value
                write_json(effective.local_config_path, payload)
                print_json({"ok": True, args.key: args.value})
                return 0
```

- [ ] **Step 6: Extend exception handling**

Change:

```python
    except (BridgeClientError, ValueError) as exc:
```

to:

```python
    except (BridgeClientError, ConfigError, ValueError) as exc:
```

- [ ] **Step 7: Run CLI tests**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests/test_cli.py -v
```

Expected: all CLI tests pass.

- [ ] **Step 8: Run all Python tests**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests -v
```

Expected: all tests pass.

- [ ] **Step 9: Commit**

Run:

```bash
git add src/unityctl/unityctl/cli.py src/unityctl/tests/test_cli.py
git commit -m "feat: add unityctl init config commands"
```

Expected: commit succeeds.

## Task 4: Make Existing CLI Commands Use Project Config

**Files:**
- Modify: `src/unityctl/unityctl/cli.py`
- Modify: `src/unityctl/tests/test_cli.py`
- Modify: `src/unityctl/unityctl/editor.py`
- Modify: `src/unityctl/tests/test_editor.py`

- [ ] **Step 1: Add failing CLI tests for config-aware commands**

Append to `src/unityctl/tests/test_cli.py`:

```python
def test_play_with_session_uses_project_config_when_project_flag_is_global(
    monkeypatch, tmp_path, capsys
):
    clients = []
    project = make_unity_project(tmp_path / "Game")
    cli.main(
        [
            "--project",
            str(project),
            "init",
            "--unity-version",
            "2022.3.62f2",
            "--port",
            "17891",
        ]
    )
    capsys.readouterr()

    def fake_client(base_url):
        client = FakeClient(base_url)
        client.start_session = (
            lambda session_id, session_path: client.calls.append(
                ("session/start", {"sessionId": session_id, "sessionPath": session_path})
            )
            or {"ok": True}
        )
        clients.append(client)
        return client

    monkeypatch.setattr(cli, "BridgeClient", fake_client)
    monkeypatch.setattr(
        cli,
        "utc_now",
        lambda: cli.datetime.fromisoformat("2026-06-30T18:30:12+00:00"),
    )

    exit_code = cli.main(["--project", str(project), "play", "--session", "login-flow"])

    assert exit_code == 0
    assert clients[0].base_url == "http://127.0.0.1:17891"
    output = json.loads(capsys.readouterr().out)
    assert output["sessionPath"].startswith(str(project / ".unity-agent" / "sessions"))


def test_summary_latest_reads_latest_session(tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    old_session = project / ".unity-agent" / "sessions" / "2026-07-01_100000_old"
    new_session = project / ".unity-agent" / "sessions" / "2026-07-02_100000_new"
    old_session.mkdir(parents=True)
    new_session.mkdir(parents=True)
    (old_session / "summary.json").write_text('{"status":"failed"}', encoding="utf-8")
    (new_session / "summary.json").write_text('{"status":"passed"}', encoding="utf-8")

    exit_code = cli.main(["--project", str(project), "summary", "--latest"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"status": "passed"}


def test_start_command_uses_resolved_config(monkeypatch, tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    cli.main(
        [
            "--project",
            str(project),
            "init",
            "--unity",
            "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app",
            "--unity-version",
            "2022.3.62f2",
        ]
    )
    capsys.readouterr()

    class FakeProcess:
        pid = 12345

    calls = []

    def fake_start_editor(unity_path, project_path, log_file):
        calls.append((unity_path, project_path, log_file))
        return FakeProcess()

    monkeypatch.setattr(cli, "start_editor", fake_start_editor)

    exit_code = cli.main(["--project", str(project), "start", "--no-wait"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["pid"] == 12345
    assert calls[0][0].endswith("Unity.app/Contents/MacOS/Unity")
    assert calls[0][1] == project


def test_start_command_waits_for_bridge_by_default(monkeypatch, tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    cli.main(
        [
            "--project",
            str(project),
            "init",
            "--unity",
            "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app",
            "--unity-version",
            "2022.3.62f2",
            "--port",
            "17891",
        ]
    )
    capsys.readouterr()

    class FakeProcess:
        pid = 12345

    waited = []

    monkeypatch.setattr(cli, "start_editor", lambda *_args: FakeProcess())
    monkeypatch.setattr(
        cli,
        "wait_for_bridge",
        lambda base_url: waited.append(base_url) or {"ok": True},
    )

    exit_code = cli.main(["--project", str(project), "start"])

    assert exit_code == 0
    assert waited == ["http://127.0.0.1:17891"]


def test_stop_latest_updates_latest_session_summary(monkeypatch, tmp_path, capsys):
    project = make_unity_project(tmp_path / "Game")
    cli.main(
        [
            "--project",
            str(project),
            "init",
            "--unity-version",
            "2022.3.62f2",
        ]
    )
    capsys.readouterr()
    old_session = project / ".unity-agent" / "sessions" / "2026-07-01_100000_old"
    new_session = project / ".unity-agent" / "sessions" / "2026-07-02_100000_new"
    old_session.mkdir(parents=True)
    new_session.mkdir(parents=True)
    (new_session / "unity-console.jsonl").write_text("", encoding="utf-8")

    class FakeClient:
        def __init__(self, base_url):
            self.base_url = base_url

        def post(self, route):
            assert route == "stop"
            return {"ok": True}

        def end_session(self):
            return {"ok": True}

    monkeypatch.setattr(cli, "BridgeClient", FakeClient)

    exit_code = cli.main(["--project", str(project), "stop", "--latest"])

    assert exit_code == 0
    assert (new_session / "summary.json").is_file()
```

- [ ] **Step 2: Run CLI tests and verify they fail**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests/test_cli.py -v
```

Expected: failures because existing commands do not use resolved project config, `start` is missing, `start` does not wait for Bridge readiness, and `--latest` is missing.

- [ ] **Step 3: Update `editor.py` path normalization**

Modify `src/unityctl/unityctl/editor.py`:

```python
import subprocess
from pathlib import Path

from unityctl.config import normalize_unity_executable_path


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
    executable = normalize_unity_executable_path(unity_path)
    if executable is None:
        raise ValueError("Unity executable path is required")
    project = str(Path(project_path).expanduser())
    log_path = str(Path(log_file).expanduser())
    return [
        str(executable),
        "-projectPath",
        project,
        "-logFile",
        log_path,
    ]
```

- [ ] **Step 4: Add `start` parser and `--latest` flags**

In `build_parser()`:

```python
start = subparsers.add_parser("start")
start.add_argument("--unity", dest="unity_path")
start.add_argument("--log-file")
start.add_argument("--no-wait", action="store_true")

stop.add_argument("--latest", action="store_true")
```

Change `logs`, `errors`, and `summary` parser args:

```python
logs.add_argument("--session-path")
logs.add_argument("--latest", action="store_true")

errors.add_argument("--session-path")
errors.add_argument("--latest", action="store_true")

summary.add_argument("--session-path")
summary.add_argument("--latest", action="store_true")
```

- [ ] **Step 5: Resolve effective config once in `main()`**

After handling `init` and `config`, replace:

```python
        client = BridgeClient(args.base_url)
```

with:

```python
        effective = resolve_effective_config(
            project_path=args.project_path,
            base_url=args.base_url,
        )
        client = BridgeClient(effective.bridge_url)
```

- [ ] **Step 6: Add Bridge readiness waiting**

Add `time` import:

```python
import time
```

Add helper in `cli.py`:

```python
def wait_for_bridge(base_url: str, timeout_seconds: int = 60) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            status = BridgeClient(base_url).get_status()
            if status.get("ok", False):
                return status
        except BridgeClientError as exc:
            last_error = exc
        time.sleep(1)
    detail = f": {last_error}" if last_error else ""
    raise ValueError(f"Bridge did not become ready at {base_url}{detail}")
```

- [ ] **Step 7: Add `start` command handling**

Before `status` handling:

```python
        if args.command == "start":
            unity_executable = args.unity_path or effective.unity_executable_path
            if unity_executable is None:
                raise ValueError(
                    "Unity path is required. Run unityctl config set-local unityAppPath "
                    "\"/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app\""
                )
            log_file = args.log_file or effective.project_path / ".unity-agent" / "unity-editor.log"
            Path(log_file).expanduser().parent.mkdir(parents=True, exist_ok=True)
            process = start_editor(
                str(unity_executable),
                effective.project_path,
                log_file,
            )
            ready_payload = None if args.no_wait else wait_for_bridge(effective.bridge_url)
            payload = {
                "ok": True,
                "pid": process.pid,
                "projectPath": str(effective.project_path),
                "unityExecutablePath": str(unity_executable),
                "bridgeUrl": effective.bridge_url,
                "bridgeReady": ready_payload is not None,
                "logFile": str(log_file),
            }
            if ready_payload is not None:
                payload["status"] = ready_payload
            print_json(payload)
            return 0
```

The first implementation waits for Bridge readiness by default. `--no-wait` returns immediately after launching Unity.

- [ ] **Step 8: Make `play --session` use resolved config**

In the `play` branch, replace the project requirement:

```python
                if not args.project_path:
                    raise ValueError("--project is required when --session is used")
```

with using `effective.project_path`:

```python
                project_path = effective.project_path
```

Then change the existing `create_session` call so its `project_path` keyword uses:

```python
                    project_path=project_path,
```

- [ ] **Step 9: Resolve latest session paths**

Import:

```python
from unityctl.config import find_latest_session_path
```

Add helper in `cli.py`:

```python
def resolve_session_path(args, project_path: Path) -> Path:
    if getattr(args, "latest", False):
        return find_latest_session_path(project_path)
    if args.session_path:
        return Path(args.session_path).expanduser().resolve()
    raise ValueError("--session-path or --latest is required")
```

Use it in `logs`, `errors`, `summary`, and `stop`:

```python
            session_path = resolve_session_path(args, effective.project_path)
            rows = read_jsonl(session_path / "unity-console.jsonl")
```

and:

```python
            session_path = resolve_session_path(args, effective.project_path)
            summary_path = session_path / "summary.json"
```

- [ ] **Step 10: Make `stop --latest` update the latest session**

In the `stop` branch, resolve a session path when either `--session-path` or `--latest` is passed:

```python
            session_path = None
            if args.session_path or getattr(args, "latest", False):
                session_path = resolve_session_path(args, effective.project_path)
```

Then replace the current `if args.session_path:` block with:

```python
            if session_path:
                ended_at = format_time(utc_now())
                update_session_status(session_path, "stopped", ended_at=ended_at)
                summary_payload = build_summary(
                    session_path,
                    load_log_rules(effective.project_path),
                )
                write_summary(session_path, summary_payload)
                payload["summary"] = summary_payload
```

If neither `--session-path` nor `--latest` is passed, `stop` keeps the current Bridge-only behavior and does not guess a local session.

- [ ] **Step 11: Run CLI and editor tests**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests/test_cli.py tests/test_editor.py -v
```

Expected: all selected tests pass.

- [ ] **Step 12: Run all Python tests**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge/src/unityctl
uv run pytest tests -v
```

Expected: all tests pass.

- [ ] **Step 13: Commit**

Run:

```bash
git add src/unityctl/unityctl/cli.py src/unityctl/unityctl/editor.py src/unityctl/tests/test_cli.py src/unityctl/tests/test_editor.py
git commit -m "feat: use project config in unityctl commands"
```

Expected: commit succeeds.

## Task 5: Make Unity Bridge Read Project Config Host and Port

**Files:**
- Create: `packages/com.elex.unity-agent-bridge/Editor/BridgeProjectConfig.cs`
- Create: `packages/com.elex.unity-agent-bridge/Tests/Editor/BridgeProjectConfigTests.cs`
- Modify: `packages/com.elex.unity-agent-bridge/Editor/BridgeConfig.cs`
- Modify: `packages/com.elex.unity-agent-bridge/Editor/BridgeServer.cs`

- [ ] **Step 1: Add failing Unity tests**

Create `packages/com.elex.unity-agent-bridge/Tests/Editor/BridgeProjectConfigTests.cs`:

```csharp
using NUnit.Framework;

namespace Elex.UnityAgentBridge.Editor.Tests
{
    public sealed class BridgeProjectConfigTests
    {
        [Test]
        public void FromJson_ReadsBridgeHostAndPort()
        {
            string json = "{\"bridge\":{\"host\":\"127.0.0.1\",\"port\":17891}}";

            BridgeProjectConfig.Settings settings = BridgeProjectConfig.FromJson(json);

            Assert.AreEqual("127.0.0.1", settings.host);
            Assert.AreEqual(17891, settings.port);
        }

        [Test]
        public void FromJson_UsesDefaultsWhenBridgeIsMissing()
        {
            BridgeProjectConfig.Settings settings = BridgeProjectConfig.FromJson("{}");

            Assert.AreEqual("127.0.0.1", settings.host);
            Assert.AreEqual(17890, settings.port);
        }

        [Test]
        public void BuildPrefix_UsesHostAndPort()
        {
            Assert.AreEqual(
                "http://127.0.0.1:17891/",
                BridgeProjectConfig.BuildPrefix("127.0.0.1", 17891)
            );
        }
    }
}
```

- [ ] **Step 2: Run Unity EditMode tests and verify they fail**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge
UNITY_BIN="/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity" scripts/run-unity-editmode-tests.sh
```

Expected: compile fails because `BridgeProjectConfig` is missing.

- [ ] **Step 3: Create `BridgeProjectConfig.cs`**

Create `packages/com.elex.unity-agent-bridge/Editor/BridgeProjectConfig.cs`:

```csharp
using System;
using System.IO;
using UnityEngine;

namespace Elex.UnityAgentBridge.Editor
{
    internal static class BridgeProjectConfig
    {
        public const string DefaultHost = "127.0.0.1";
        public const int DefaultPort = 17890;

        public static Settings Load()
        {
            string path = GetConfigPath();
            if (!File.Exists(path))
            {
                return Settings.Default();
            }

            return FromJson(File.ReadAllText(path));
        }

        public static Settings FromJson(string json)
        {
            if (string.IsNullOrWhiteSpace(json))
            {
                return Settings.Default();
            }

            ConfigPayload payload = JsonUtility.FromJson<ConfigPayload>(json);
            if (payload == null || payload.bridge == null)
            {
                return Settings.Default();
            }

            string host = string.IsNullOrWhiteSpace(payload.bridge.host) ? DefaultHost : payload.bridge.host;
            int port = payload.bridge.port <= 0 ? DefaultPort : payload.bridge.port;
            return new Settings { host = host, port = port };
        }

        public static string BuildPrefix(string host, int port)
        {
            return $"http://{host}:{port}/";
        }

        public static string GetConfigPath()
        {
            DirectoryInfo assetsDirectory = new DirectoryInfo(Application.dataPath);
            string projectRoot = assetsDirectory.Parent == null ? string.Empty : assetsDirectory.Parent.FullName;
            return Path.Combine(projectRoot, ".unity-agent", "config.json");
        }

        [Serializable]
        private sealed class ConfigPayload
        {
            public BridgePayload bridge;
        }

        [Serializable]
        private sealed class BridgePayload
        {
            public string host;
            public int port;
        }

        [Serializable]
        public sealed class Settings
        {
            public string host;
            public int port;

            public static Settings Default()
            {
                return new Settings { host = DefaultHost, port = DefaultPort };
            }
        }
    }
}
```

- [ ] **Step 4: Modify `BridgeConfig.cs`**

Replace `BridgeConfig.cs` with:

```csharp
namespace Elex.UnityAgentBridge.Editor
{
    internal static class BridgeConfig
    {
        public const string Version = "0.1.0";

        public static string Host
        {
            get
            {
                return BridgeProjectConfig.Load().host;
            }
        }

        public static int Port
        {
            get
            {
                return BridgeProjectConfig.Load().port;
            }
        }

        public static string Prefix
        {
            get
            {
                BridgeProjectConfig.Settings settings = BridgeProjectConfig.Load();
                return BridgeProjectConfig.BuildPrefix(settings.host, settings.port);
            }
        }
    }
}
```

- [ ] **Step 5: Keep `BridgeServer.cs` using `BridgeConfig.Prefix`**

No route changes are required. Confirm the existing line still reads:

```csharp
listener.Prefixes.Add(BridgeConfig.Prefix);
```

and the startup log still uses:

```csharp
Debug.Log($"Unity Agent Bridge listening on {BridgeConfig.Prefix}");
```

- [ ] **Step 6: Run Unity EditMode tests**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge
UNITY_BIN="/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity" scripts/run-unity-editmode-tests.sh
```

Expected: all Unity EditMode tests pass.

- [ ] **Step 7: Commit**

Run:

```bash
git add packages/com.elex.unity-agent-bridge/Editor/BridgeProjectConfig.cs packages/com.elex.unity-agent-bridge/Editor/BridgeProjectConfig.cs.meta packages/com.elex.unity-agent-bridge/Editor/BridgeConfig.cs packages/com.elex.unity-agent-bridge/Tests/Editor/BridgeProjectConfigTests.cs packages/com.elex.unity-agent-bridge/Tests/Editor/BridgeProjectConfigTests.cs.meta
git commit -m "feat: load unity bridge port from project config"
```

Expected: commit succeeds.

## Task 6: Add Config Schema, Examples, and README Updates

**Files:**
- Create: `schemas/unity-agent-config.schema.json`
- Create: `examples/unity-agent-config/config.json`
- Create: `examples/unity-agent-config/config.local.json`
- Modify: `README.md`

- [ ] **Step 1: Add config schema**

Create `schemas/unity-agent-config.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://elex.example/schemas/unity-agent-bridge/unity-agent-config.schema.json",
  "title": "Unity Agent Bridge Project Config",
  "type": "object",
  "additionalProperties": false,
  "required": ["version", "unityVersion", "bridge", "defaultScene", "sessionDirectory"],
  "properties": {
    "version": {
      "type": "integer",
      "const": 1
    },
    "unityVersion": {
      "type": ["string", "null"]
    },
    "bridge": {
      "type": "object",
      "additionalProperties": false,
      "required": ["host", "port"],
      "properties": {
        "host": {
          "type": "string",
          "minLength": 1
        },
        "port": {
          "type": "integer",
          "minimum": 1,
          "maximum": 65535
        }
      }
    },
    "defaultScene": {
      "type": ["string", "null"]
    },
    "sessionDirectory": {
      "type": "string",
      "minLength": 1
    }
  }
}
```

- [ ] **Step 2: Add config examples**

Create `examples/unity-agent-config/config.json`:

```json
{
  "version": 1,
  "unityVersion": "2022.3.62f2",
  "bridge": {
    "host": "127.0.0.1",
    "port": 17890
  },
  "defaultScene": null,
  "sessionDirectory": ".unity-agent/sessions"
}
```

Create `examples/unity-agent-config/config.local.json`:

```json
{
  "unityAppPath": "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app"
}
```

- [ ] **Step 3: Update README install and init sections**

Update `README.md` so the CLI section says:

```markdown
## 安装 CLI

本地开发安装：

```bash
uv tool install --editable ./src/unityctl
```

安装后可以在任意目录运行：

```bash
unityctl --help
```

初始化 Unity project：

```bash
cd /path/to/UnityProject
unityctl init \
  --unity "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app" \
  --unity-version "2022.3.62f2" \
  --port 17890
```

日常命令：

```bash
unityctl start
unityctl status
unityctl play --session login-flow
unityctl stop --latest
unityctl summary --latest
```
```

Keep the existing `uv run unityctl` examples as a lower-level development workflow, but mark them as development commands.

- [ ] **Step 4: Validate JSON artifacts**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge
python3 - <<'PY'
import json
from pathlib import Path

for path in sorted(list(Path("schemas").glob("*.json")) + list(Path("examples").rglob("*.json"))):
    json.loads(path.read_text(encoding="utf-8"))
    print(f"json ok: {path}")
PY
```

Expected: every schema and example JSON prints `json ok`.

- [ ] **Step 5: Run Python tests**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge
scripts/run-python-tests.sh
```

Expected: all Python tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add README.md schemas/unity-agent-config.schema.json examples/unity-agent-config/config.json examples/unity-agent-config/config.local.json
git commit -m "docs: add unityctl init config usage"
```

Expected: commit succeeds.

## Task 7: End-to-End Verification

**Files:**
- No source changes expected.

- [ ] **Step 1: Run all Python tests**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge
scripts/run-python-tests.sh
```

Expected: all Python tests pass.

- [ ] **Step 2: Run Unity EditMode tests**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge
UNITY_BIN="/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity" scripts/run-unity-editmode-tests.sh
```

Expected: XML result has `failed="0"` and all tests pass.

- [ ] **Step 3: Smoke test `unityctl init` against local temporary Unity project**

Run:

```bash
cd /Users/elex-mb0203/MyWork/my_github/UnityRunBridge
TEST_PROJECT="$PWD/.tmp/unity-test-project"
cd src/unityctl
uv run unityctl --project "$TEST_PROJECT" init \
  --unity "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app" \
  --unity-version "2022.3.62f2" \
  --port 17891
uv run unityctl --project "$TEST_PROJECT" config show
test -f "$TEST_PROJECT/.unity-agent/config.json"
test -f "$TEST_PROJECT/.unity-agent/config.local.json"
```

Expected:

- `init` exits `0` and prints `"ok": true`.
- `config show` exits `0` and prints `"bridgeUrl": "http://127.0.0.1:17891"`.
- both config files exist.

- [ ] **Step 4: Smoke test Bridge starts on configured port**

Run a short Python smoke script from repository root:

```bash
python3 - <<'PY'
import json
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

repo = Path.cwd()
unity = "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity"
project = repo / ".tmp" / "unity-test-project"
log = repo / ".tmp" / "logs" / "configured-port-smoke.log"
process = subprocess.Popen(
    [unity, "-batchmode", "-projectPath", str(project), "-logFile", str(log)],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
try:
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            with urlopen("http://127.0.0.1:17891/status", timeout=1) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("ok"):
                print(json.dumps(payload, sort_keys=True))
                break
        except Exception:
            time.sleep(1)
    else:
        raise SystemExit("Bridge did not start on configured port 17891")
finally:
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=15)
PY
```

Expected: prints a status payload from `http://127.0.0.1:17891/status`.

- [ ] **Step 5: Verify git status**

Run:

```bash
git status --short
```

Expected: no output.

## Self-Review

Spec coverage:

- Global `unityctl` command naming is covered by Task 1.
- `unityctl init` and project-local `.unity-agent/` config are covered by Tasks 2 and 3.
- `config.json` vs `config.local.json` split is covered by Task 2.
- Unity version vs Unity install path split is covered by Task 2.
- Bridge host/port in project config is covered by Tasks 2 and 5.
- CLI project discovery and command defaults are covered by Task 4.
- `--latest` session lookup is covered by Task 4.
- Schemas/examples/docs are covered by Task 6.
- End-to-end verification is covered by Task 7.

Placeholder scan:

- The plan contains no unfinished markers or unspecified implementation steps.
- Every task lists exact files, test commands, expected results, and commit commands.

Type consistency:

- Python config APIs are consistently named `find_unity_project_root`, `init_project_config`, `resolve_effective_config`, and `find_latest_session_path`.
- Unity-side config APIs are consistently named `BridgeProjectConfig`, `Settings`, `FromJson`, and `BuildPrefix`.
- Package metadata uses `unity-run-bridge`; executable command remains `unityctl`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-02-unityctl-global-init-config.md`. Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints

Which approach?
