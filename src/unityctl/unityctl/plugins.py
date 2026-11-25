import os
from pathlib import Path


MIDSCENE_TEMPLATE = """{
  // API 前缀，例如 https://gateway.example/v1；不要加 /chat/completions 或 /responses。
  "baseUrl": "",
  // 服务商实际提供的模型 ID。
  "modelName": "",
  // Midscene 模型类型，不一定与模型 ID 相同。
  "modelFamily": "",
  // openai-chat（默认）或 openai-responses（当前仅 gpt-5 / gpt-6）。
  "protocol": "openai-chat",
  // API Key 的环境变量名，不要在这里填写密钥值。
  "apiKeyEnv": "UNITY_BRIDGE_MIDSCENE_API_KEY"
}
"""


def _existing_midscene_config(plugin_dir: Path) -> Path | None:
    existing = []
    for name in ("midscene.jsonc", "midscene.json"):
        path = plugin_dir / name
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        existing.append(path)
    if len(existing) > 1:
        raise OSError("midscene.jsonc 与 midscene.json 同时存在，请手动只保留其中一份")
    if existing and not existing[0].is_file():
        raise OSError(f"配置路径已被非文件占用：{existing[0]}")
    return existing[0] if existing else None


def init_midscene_config(home: Path) -> tuple[Path, bool]:
    config_home = home / ".unity-agent-bridge"
    plugin_dir = config_home / "plugins"
    for directory in (config_home, plugin_dir):
        directory.mkdir(mode=0o700, exist_ok=True)
        if directory.is_symlink() or not directory.is_dir():
            raise OSError(f"插件目录必须是实际目录：{directory}")

    existing = _existing_midscene_config(plugin_dir)
    if existing:
        return existing, False

    path = plugin_dir / "midscene.jsonc"
    try:
        handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        existing = _existing_midscene_config(plugin_dir)
        if existing:
            return existing, False
        raise

    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(MIDSCENE_TEMPLATE)
    return path, True
