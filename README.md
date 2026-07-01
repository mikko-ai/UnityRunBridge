# UnityRunBridge

UnityRunBridge provides a small Editor-only Unity package and a Python CLI for
controlling a local Unity Editor instance from scripts or agents.

Current scope:

- Start a Unity Editor process.
- Query Editor status through a local HTTP bridge.
- Enter, stop, pause, and resume Play Mode.
- Open a scene inside the Unity project.

The bridge listens on `http://127.0.0.1:17890` inside the Unity Editor.

## Requirements

- Unity Editor `2022.3` or newer.
- Python `3.11` or newer.
- `uv` for Python dependency and command execution.

## Add the Unity Package

Add the package to the Unity project's `Packages/manifest.json`:

```json
{
  "dependencies": {
    "com.elex.unity-agent-bridge": "file:/absolute/path/to/UnityRunBridge/packages/com.elex.unity-agent-bridge"
  }
}
```

Use the absolute path of this repository on your machine. The package is
Editor-only and starts the local bridge when the Unity Editor loads it.

## Install the CLI

From this repository:

```bash
cd src/unityctl
uv sync
```

Run commands with `uv run unityctl ...`.

## Configure Local Paths

`UNITY_BIN` and `UNITY_PROJECT` are not hardcoded project settings. They are
regular shell variables used by the examples below so each machine can provide
its own Unity installation and Unity project.

`UNITY_BIN` should point to the Unity command-line executable:

```bash
export UNITY_BIN="/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity"
```

If you start from a `.app` path such as
`/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app`, append
`/Contents/MacOS/Unity`.

`UNITY_PROJECT` should point to the Unity project root, the directory that
contains `Assets`, `Packages`, and `ProjectSettings`:

```bash
export UNITY_PROJECT="/absolute/path/to/your/unity-project"
```

For repeatable local runs, keep logs under this repository:

```bash
cd /absolute/path/to/UnityRunBridge
export REPO_ROOT="$(pwd)"
mkdir -p "$REPO_ROOT/.tmp/logs"
```

## Start Unity

From `src/unityctl`:

```bash
cd "$REPO_ROOT/src/unityctl"
uv run unityctl start-editor \
  --unity "$UNITY_BIN" \
  --project "$UNITY_PROJECT" \
  --log-file "$REPO_ROOT/.tmp/logs/unity-editor.log"
```

Wait until the Unity log contains:

```text
Unity Agent Bridge listening on http://127.0.0.1:17890/
```

## Control the Editor

From `src/unityctl`:

```bash
uv run unityctl status
uv run unityctl play
uv run unityctl pause
uv run unityctl resume
uv run unityctl stop
uv run unityctl open-scene "Assets/Scenes/Login.unity"
```

All commands print JSON. A successful response includes `"ok": true`.

## Run Tests

Python tests:

```bash
cd src/unityctl
uv run pytest tests -v
```

Unity EditMode tests, from the repository root:

```bash
cd "$REPO_ROOT"
mkdir -p "$REPO_ROOT/.tmp/logs" "$REPO_ROOT/.tmp/test-results"

"$UNITY_BIN" \
  -batchmode \
  -projectPath "$REPO_ROOT/.tmp/unity-test-project" \
  -runTests \
  -testPlatform EditMode \
  -testResults "$REPO_ROOT/.tmp/test-results/editmode.xml" \
  -logFile "$REPO_ROOT/.tmp/logs/editmode.log"
```

The Unity test command intentionally does not pass `-quit`; Unity exits after
the test run writes the result XML.
