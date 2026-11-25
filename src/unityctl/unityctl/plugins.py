import json
import os
from pathlib import Path


MIDSCENE_TEMPLATE = {
    "baseUrl": "",
    "modelName": "",
    "modelFamily": "",
    "apiKeyEnv": "UNITY_BRIDGE_MIDSCENE_API_KEY",
}


def init_midscene_config(home: Path) -> tuple[Path, bool]:
    config_home = home / ".unity-agent-bridge"
    plugin_dir = config_home / "plugins"
    for directory in (config_home, plugin_dir):
        directory.mkdir(mode=0o700, exist_ok=True)
        if directory.is_symlink() or not directory.is_dir():
            raise OSError(f"插件目录必须是实际目录：{directory}")

    path = plugin_dir / "midscene.json"
    try:
        handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.is_file():
            return path, False
        raise OSError(f"配置路径已被非文件占用：{path}") from None

    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(MIDSCENE_TEMPLATE, indent=2) + "\n")
    return path, True
