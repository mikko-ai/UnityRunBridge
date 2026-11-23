"""Read-only triage for Unity build size (not a list of shipped assets).

Adapted from awesome-gamedev-agent-skills (Apache-2.0), c6ca6c4,
skills/unity/unity-build-size/scripts/check_unity_build_size.py.
See licenses/ for attribution. This adapter does not emit edit commands.
"""

import base64
import binascii
import json
import os
import re
import struct
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

TEXTURE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tga", ".psd", ".tif", ".tiff", ".exr", ".hdr", ".bmp", ".gif"}
AUDIO_EXTENSIONS = {".wav", ".aif", ".aiff", ".mp3", ".ogg", ".flac", ".mod", ".it", ".s3m", ".xm"}
GLTFAST_PACKAGES = {"com.unity.cloud.gltfast", "com.atteneder.gltfast"}
SUPPORTED_PLATFORMS = ("Standalone", "Android", "iPhone", "WebGL", "tvOS")
MAX_TEXTURE_EDGE = 16384
HEADER_READ_BYTES = 512 * 1024
_MAX_JSON = 16 * 1024 * 1024
_MAX_META = 2 * 1024 * 1024
_MIB = 1024 * 1024
JPEG_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
JPEG_NO_LENGTH = {0x01, *range(0xD0, 0xDA)}
_TEXTURE_ENTRY = re.compile(r"^  -(?: serializedVersion:| buildTarget:)")
_TEXTURE_KEY = re.compile(r"^    (buildTarget|maxTextureSize|textureFormat|textureCompression|overridden):[ \t]*(\S+)\s*$")

UNCOMPRESSED_FORMATS = {
    1: ("Alpha8", 1),
    2: ("ARGB16", 2),
    3: ("RGB24", 3),
    4: ("RGBA32", 4),
    5: ("ARGB32", 4),
    7: ("RGB16", 2),
    9: ("R16", 2),
    13: ("RGBA16", 2),
    15: ("RHalf", 2),
    16: ("RGHalf", 4),
    17: ("RGBAHalf", 8),
    18: ("RFloat", 4),
    19: ("RGFloat", 8),
    20: ("RGBAFloat", 16),
    22: ("RGB9E5", 4),
    62: ("RG16", 2),
    63: ("R8", 1),
    72: ("RG32", 4),
    73: ("RGB48", 6),
    74: ("RGBA64", 8),
    75: ("R8_SIGNED", 1),
    76: ("RG16_SIGNED", 2),
    77: ("RGB24_SIGNED", 3),
    78: ("RGBA32_SIGNED", 4),
    79: ("R16_SIGNED", 2),
    80: ("RG32_SIGNED", 4),
    81: ("RGB48_SIGNED", 6),
    82: ("RGBA64_SIGNED", 8),
}


def image_kind(head: bytes) -> str | None:
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8"):
        return "jpeg"
    return None


def png_size(head: bytes) -> tuple[int, int] | None:
    if len(head) < 24 or head[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", head[16:24])


def jpeg_size(head: bytes) -> tuple[int, int] | None:
    pos = 2
    while pos + 4 <= len(head):
        if head[pos] != 0xFF:
            return None
        marker = head[pos + 1]
        if marker == 0xFF:  # fill byte
            pos += 1
            continue
        if marker in JPEG_NO_LENGTH:
            pos += 2
            continue
        (length,) = struct.unpack(">H", head[pos + 2 : pos + 4])
        if marker in JPEG_SOF:
            if pos + 9 > len(head):
                return None
            height, width = struct.unpack(">HH", head[pos + 5 : pos + 9])
            return width, height
        pos += 2 + length
    return None


def header_size(head: bytes, suffix: str) -> tuple[int, int] | None:
    kind = image_kind(head)
    if kind == "png":
        return png_size(head)
    if kind == "jpeg":
        return jpeg_size(head)
    if head.startswith(b"8BPS") and len(head) >= 22:
        height, width = struct.unpack(">II", head[14:22])
        return width, height
    if suffix == ".tga" and len(head) >= 18:
        return struct.unpack("<HH", head[12:16])
    return None


def image_size(head: bytes, suffix: str = "") -> tuple[int, int] | None:
    """Width and height from the first bytes of a PNG, JPEG, TGA or PSD file.

    None when the header is unknown or claims a size Unity cannot import (0, or above 16384).
    """
    size = header_size(head, suffix)
    if size is None or min(size) < 1 or max(size) > MAX_TEXTURE_EDGE:
        return None
    return size


def mip_chain_bytes(width: int, height: int, bpp: int, mips: bool = True) -> int:
    """Bytes of an uncompressed texture as Unity stores it: one level, or a full mip chain."""
    total = 0
    while True:
        total += width * height * bpp
        if not mips or (width == 1 and height == 1):
            return total
        width, height = max(1, width // 2), max(1, height // 2)


def read_head(path: Path, limit: int = HEADER_READ_BYTES) -> bytes:
    with path.open("rb") as handle:
        return handle.read(limit)



def _read_limited(path: Path, limit: int) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise OSError("不是普通文件")
    with path.open("rb") as stream:
        result = stream.read(limit + 1)
    if len(result) > limit:
        raise ValueError("数据超过扫描上限")
    return result


def _texture_settings(lines: list[str], platform: str) -> dict[str, str]:
    entries: list[dict[str, str]] = []
    inside = False
    for line in lines:
        if line == "  platformSettings:":
            inside = True
        elif inside:
            if _TEXTURE_ENTRY.match(line):
                entries.append({})
                if line.startswith("  - buildTarget:"):
                    entries[-1]["buildTarget"] = line.split(":", 1)[1].strip()
            elif line.startswith("  ") and not line.startswith(("    ", "  -")):
                break
            elif entries and (match := _TEXTURE_KEY.fullmatch(line)):
                entries[-1][match[1]] = match[2]
    return next((e for e in entries if e.get("buildTarget") == platform and e.get("overridden") == "1"),
                next((e for e in entries if e.get("buildTarget") == "DefaultTexturePlatform"), {}))


def _number(value: str | None) -> int | None:
    return int(value) if value and re.fullmatch(r"-?[0-9]{1,9}", value) else None


def _model_json(path: Path) -> tuple[dict, tuple[int, int] | None]:
    location = None
    if path.suffix.lower() == ".glb":
        with path.open("rb") as stream:
            magic, version, length = struct.unpack("<4sII", stream.read(12))
            if magic != b"glTF" or version != 2 or length != os.fstat(stream.fileno()).st_size:
                raise ValueError("无效的 GLB 2.0 文件头")
            size, kind = struct.unpack("<I4s", stream.read(8))
            if kind != b"JSON" or size > _MAX_JSON or size > length - 20:
                raise ValueError("无效或过大的 GLB JSON 块")
            raw = stream.read(size)
            if stream.tell() != length:
                size, kind = struct.unpack("<I4s", stream.read(8))
                if kind == b"BIN\0" and size <= length - stream.tell():
                    location = (stream.tell(), size)
    else:
        raw = _read_limited(path, _MAX_JSON)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("glTF 的 JSON 根不是对象")
    return data, location


def _data_uri(uri: str) -> bytes | None:
    header, sep, encoded = uri.partition(",")
    if not sep or not header.startswith("data:"):
        return None
    if not header.endswith(";base64"):
        raise ValueError("嵌入图像/缓冲区不是 base64 编码")
    # The model JSON bounds input length; image decoding only needs a header.
    return base64.b64decode(encoded, validate=True)


def _view_head(path: Path, project: Path, view: dict, buffers: list, location: tuple[int, int] | None) -> bytes:
    index, offset, size = view["buffer"], view.get("byteOffset", 0), view["byteLength"]
    if any(type(n) is not int or n < 0 for n in (index, offset, size)) or index >= len(buffers):
        raise ValueError("无效的图像 bufferView")
    uri = buffers[index].get("uri")
    read_size = min(size, HEADER_READ_BYTES)
    if uri is None:
        if location is None or index != 0 or offset + size > location[1]:
            raise ValueError("bufferView 超出 GLB 二进制块")
        offset += location[0]
        target = path
    elif (raw := _data_uri(uri)) is not None:
        if offset + size > len(raw):
            raise ValueError("bufferView 超出 data URI 缓冲区")
        return raw[offset:offset + read_size]
    else:
        target = (path.parent / unquote(uri)).resolve()
        if "://" in uri or Path(uri).is_absolute() or not target.is_relative_to(project) or not target.is_file():
            raise ValueError("无法读取项目内的 glTF 缓冲区")
    with target.open("rb") as stream:
        if offset + size > os.fstat(stream.fileno()).st_size:
            raise ValueError("bufferView 超出文件")
        stream.seek(offset)
        return stream.read(read_size)


def _embedded_images(path: Path, project: Path) -> tuple[list[tuple[int, int, int]], int]:
    data, location = _model_json(path)
    results = []
    unchecked = 0
    for image in data.get("images", []):
        if "bufferView" in image:
            index = image["bufferView"]
            views = data["bufferViews"]
            if type(index) is not int or not 0 <= index < len(views):
                raise ValueError("无效的图像 bufferView 索引")
            head = _view_head(path, project, views[index], data["buffers"], location)
        elif (head := _data_uri(image["uri"])) is None:
            continue  # external image, not an embedded texture
        if (dimensions := image_size(head)) is None:
            unchecked += 1
        else:
            results.append((*dimensions, 4 if image_kind(head) == "png" else 3))
    return results, unchecked


def scan_build_assets(project: Path, platform: str, max_texture_size: int) -> dict:
    if platform not in SUPPORTED_PLATFORMS or not 1 <= max_texture_size <= MAX_TEXTURE_EDGE:
        raise ValueError("扫描平台无效或纹理尺寸上限不在有效范围内")
    project = project.resolve()
    root = project / "Assets"
    unchecked: Counter[str] = Counter()
    issues = []
    has_gltfast = False
    for name in ("manifest.json", "packages-lock.json"):
        path = project / "Packages" / name
        if not path.exists():
            continue
        try:
            payload = json.loads(_read_limited(path, _MAX_JSON))
            deps = payload.get("dependencies")
            if not isinstance(deps, dict):
                raise ValueError("缺少 dependencies")
            has_gltfast |= bool(GLTFAST_PACKAGES.intersection(deps))
        except (OSError, ValueError, AttributeError, RecursionError):
            unchecked["package_metadata"] += 1

    def add(code, asset, message, size=None, *, level="warning"):
        issues.append({"code": code, "file": asset.relative_to(project).as_posix(), "level": level,
                       "message": message, "bytes": size})

    def on_error(_error):
        unchecked["unreadable_path"] += 1

    checked = 0
    if root.is_symlink():
        unchecked["symlinks"] += 1
    walker = () if root.is_symlink() else os.walk(root, onerror=on_error)
    for folder, dirs, files in walker:
        directory = Path(folder)
        streaming = directory.is_relative_to(root / "StreamingAssets")
        def visible(name):
            return (streaming or name == "StreamingAssets" or not name.startswith(".")) and (
                not name.endswith(("~", ".tmp")) and name.lower() != "cvs"
            )

        visible_dirs = [name for name in sorted(dirs) if visible(name)]
        dirs[:] = [name for name in visible_dirs if not (directory / name).is_symlink()]
        if len(visible_dirs) != len(dirs):
            unchecked["symlinks"] += len(visible_dirs) - len(dirs)
        for name in sorted(files):
            asset = directory / name
            suffix = asset.suffix.lower()
            if suffix == ".meta" or not visible(name):
                continue
            if asset.is_symlink():
                unchecked["symlinks"] += 1
                continue
            if not asset.is_file():
                continue
            try:
                checked += 1
                size = asset.stat().st_size
                if streaming:
                    if size >= 8 * _MIB:
                        add("large-streaming-asset", asset, "StreamingAssets 中的大文件，比较实际交付包确认影响",
                            size, level="note")
                    continue
                if "Resources" in directory.relative_to(root).parts and size >= 8 * _MIB:
                    add("large-resources-asset", asset, "Resources 下的大资源，核对构建报告确认成本", size)
                if suffix in (".gltf", ".glb"):
                    if not has_gltfast:
                        unchecked["gltf_importer_unknown"] += 1
                        continue
                    try:
                        images, unsupported = _embedded_images(asset, root)
                        if unsupported:
                            unchecked["gltf_image_format"] += unsupported
                    except (OSError, TypeError, ValueError, KeyError, IndexError, AttributeError,
                            RecursionError, struct.error, binascii.Error):
                        unchecked["gltf_unreadable"] += 1
                        add("gltf-unreadable", asset, "无法完整读取嵌入纹理；请在 Editor 中确认")
                        continue
                    estimate = sum(w * h * bpp for w, h, bpp in images)
                    if any(max(w, h) > max_texture_size for w, h, _ in images):
                        add("gltf-embedded-texture", asset,
                            f"glTFast 嵌入纹理超过 {max_texture_size}px；bytes 为解码像素估算", estimate)
                    elif estimate >= _MIB:
                        add("gltf-embedded-images", asset, "嵌入纹理解码像素大小估算", estimate, level="note")
                    continue
                if suffix not in TEXTURE_EXTENSIONS | AUDIO_EXTENSIONS:
                    continue
                meta = asset.with_name(asset.name + ".meta")
                if not meta.is_file() or meta.is_symlink():
                    unchecked["texture_or_audio_meta"] += 1
                    continue
                lines = _read_limited(meta, _MAX_META).decode("utf-8-sig", errors="replace").splitlines()
                if suffix in TEXTURE_EXTENSIONS and "TextureImporter:" in lines:
                    setting = _texture_settings(lines, platform)
                    dimensions = image_size(read_head(asset), suffix)
                    limit = _number(setting.get("maxTextureSize"))
                    if not dimensions or not limit or limit < 1:
                        unchecked["texture_format_or_settings"] += 1
                        continue
                    edge = max(dimensions)
                    fmt = _number(setting.get("textureFormat"))
                    compression = _number(setting.get("textureCompression"))
                    bpp = (UNCOMPRESSED_FORMATS.get(fmt, ("", 0))[1] if fmt is not None and fmt >= 0
                           else 4 if compression == 0 else 0)
                    if bpp and min(edge, limit) >= 1024:
                        scale = min(edge, limit) / edge
                        width, height = (max(1, round(n * scale)) for n in dimensions)
                        estimate = mip_chain_bytes(width, height, bpp, "    enableMipMap: 0" not in lines)
                        add("uncompressed-texture", meta, "当前平台设置未压缩；bytes 为纹理层大小估算", estimate)
                    if min(edge, limit) > max_texture_size:
                        add("texture-max-size", meta, f"当前平台导入上限与原图尺寸都超过 {max_texture_size}px")
                elif suffix in AUDIO_EXTENSIONS and "AudioImporter:" in lines:
                    if size >= _MIB and "    compressionFormat: 0" in lines:
                        override = next((line.strip() for line in lines if line.startswith("  platformSettingOverrides:")), None)
                        if override == "platformSettingOverrides: {}":
                            add("pcm-audio", meta, "默认格式为 PCM；bytes 是源文件大小，并非包内体积", size)
                        else:
                            add("audio-platform-override", meta, "存在或无法确定平台覆盖，请在 Editor 中确认",
                                level="note")
            except (OSError, ValueError):
                unchecked["unreadable_path"] += 1

    issues.sort(key=lambda issue: (issue["level"] != "warning", issue["file"], issue["code"]))
    return {"platform": platform, "maxTextureSize": max_texture_size, "filesChecked": checked,
            "issues": issues[:200], "issueCount": len(issues), "unchecked": dict(unchecked),
            "truncated": len(issues) > 200}
