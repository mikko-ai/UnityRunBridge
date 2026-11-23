import json
from io import StringIO

import pytest

from unityctl.build_size import analyze_build_size, parse_build_log


def block(total="12.0 mb", *, legacy=False, closed=True):
    end = "-" * 40 + "\n" if closed else ""
    complete = f"Complete size  {total}  100.0%" if legacy else f"Complete build size  {total}"
    return (
        "Build Report\nUncompressed usage by category:\n"
        "Textures  8.0 mb  80.0%\nTotal User Assets  10 mb  100.0%\n"
        f"{complete}\nUsed Assets and files from the Resources folder, sorted by uncompressed size:\n"
        "  1.0 mb  10.0% Assets/audio A.wav\n"
        "  5.0 mb  50.0% Assets/texture.png\n" + end
    )


def test_2022_and_newer_log_formats_and_largest_assets():
    report = parse_build_log(StringIO(block("24 mb", legacy=True) + block()), top=1)
    assert report == {
        "startLine": 10, "complete": True, "totalBytes": 12 * 2**20,
        "userAssetsBytes": 10 * 2**20,
        "categories": [{"name": "Textures", "bytes": 8 * 2**20, "percent": 80.0}],
        "assetCount": 2,
        "topAssets": [{"path": "Assets/texture.png", "bytes": 5 * 2**20, "percent": 50.0}],
    }


def test_truncated_latest_does_not_silently_use_older_success(tmp_path):
    (tmp_path / "build.log").write_text(block() + block("2.0 mb", closed=False))
    result = analyze_build_size(build_dir=tmp_path, report_budget_bytes=16 * 2**20)
    assert not result["ok"]
    assert result["budgets"]["report"]["status"] == "unverified"
    assert not result["logReport"]["complete"]


def test_successful_archived_report_keeps_measurements_separate(tmp_path):
    archive = tmp_path / "archive"
    output = archive / "Build" / "game.apk"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"player")
    (archive / "build.log").write_text(block())
    (archive / "build-report.json").write_text(json.dumps(
        {"result": "Succeeded", "sizeBytes": 23, "outputPath": str(output)}
    ))
    result = analyze_build_size(build_dir=archive, report_budget_bytes=2**20, artifact_budget_bytes=6)
    assert not result["ok"]
    assert result["buildSummary"]["sizeBytes"] == 23
    assert result["logReport"]["totalBytes"] == 12 * 2**20
    assert result["artifact"]["bytes"] == 6
    assert result["budgets"]["report"]["status"] == "exceeded"
    assert result["budgets"]["artifact"]["status"] == "passed"


def test_missing_or_failed_build_does_not_accept_stale_output(tmp_path):
    output = tmp_path / "game.apk"
    output.write_bytes(b"old player")
    (tmp_path / "build-report.json").write_text(json.dumps({"result": "Failed", "outputPath": str(output)}))
    result = analyze_build_size(build_dir=tmp_path, artifact=output, artifact_budget_bytes=100)
    assert not result["ok"]
    assert result["budgets"]["artifact"]["status"] == "unverified"


def test_symlink_in_delivery_folder_does_not_get_counted_as_ordinary_file(tmp_path):
    artifact = tmp_path / "Web"
    artifact.mkdir()
    (artifact / "game.data").write_bytes(b"player")
    (artifact / "linked").symlink_to(artifact / "game.data")
    result = analyze_build_size(artifact=artifact, artifact_budget_bytes=100)
    assert result["artifact"]["status"] == "unavailable"
    assert result["budgets"]["artifact"]["status"] == "unverified"


def test_explicit_artifact_does_not_require_unity_or_archived_report(tmp_path):
    artifact = tmp_path / "build.zip"
    artifact.write_bytes(b"player")
    result = analyze_build_size(artifact=artifact, artifact_budget_bytes=6)
    assert result["ok"]
    assert result["budgets"]["artifact"]["status"] == "passed"


@pytest.mark.parametrize("text", ["no build", "Build Report\nTextures 1.5 mb 90.%\n"])
def test_unrecognized_report_never_passes_budget(text, tmp_path):
    log = tmp_path / "build.log"
    log.write_text(text)
    result = analyze_build_size(log=log, report_budget_bytes=2**20)
    assert result["budgets"]["report"]["status"] == "unverified"


def test_scan_importer_overrides_audio_streaming_and_gltfast(tmp_path):
    import struct

    from unityctl.build_size_scan import scan_build_assets

    def write(name, data):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            path.write_bytes(data)
        else:
            path.write_text(data)
        return path

    png = b"\x89PNG\r\n\x1a\n" + struct.pack(">I4sII", 13, b"IHDR", 4096, 2048)
    write("Packages/manifest.json", '{"dependencies":{"com.unity.cloud.gltfast":"6.0.0"}}')
    write("Assets/Hud.png", png)
    write("Assets/Hud.png.meta", """TextureImporter:
  platformSettings:
  - serializedVersion: 3
    buildTarget: DefaultTexturePlatform
    maxTextureSize: 2048
    textureFormat: -1
    textureCompression: 1
    overridden: 0
  - serializedVersion: 3
    buildTarget: Android
    maxTextureSize: 4096
    textureFormat: 4
    textureCompression: 1
    overridden: 1
""")
    write("Assets/audio.wav", b"RIFF").open("ab").close()
    with (tmp_path / "Assets/audio.wav").open("r+b") as stream:
        stream.truncate(2**20)
    write("Assets/audio.wav.meta", "AudioImporter:\n  defaultSettings:\n    compressionFormat: 0\n  platformSettingOverrides: {}\n")
    with write("Assets/StreamingAssets/raw.gltf", b"not a model").open("r+b") as stream:
        stream.truncate(8 * 2**20)
    document = json.dumps({"images": [{"bufferView": 0}], "bufferViews": [
        {"buffer": 0, "byteLength": len(png)}
    ], "buffers": [{"byteLength": len(png)}]}).encode()
    document += b" " * (-len(document) % 4)
    body = struct.pack("<I4s", len(document), b"JSON") + document + struct.pack("<I4s", len(png), b"BIN\0") + png
    write("Assets/Model.glb", struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body)

    report = scan_build_assets(tmp_path, "Android", 2048)
    by_code = {issue["code"]: issue for issue in report["issues"]}
    assert set(by_code) == {"uncompressed-texture", "texture-max-size", "pcm-audio",
                            "large-streaming-asset", "gltf-embedded-texture"}
    assert by_code["gltf-embedded-texture"]["file"] == "Assets/Model.glb"
    assert by_code["large-streaming-asset"]["bytes"] == 8 * 2**20
    assert by_code["uncompressed-texture"]["bytes"] >= 4096 * 2048 * 4
    standalone = scan_build_assets(tmp_path, "Standalone", 2048)
    assert not any(issue["code"].startswith(("uncompressed-", "texture-")) for issue in standalone["issues"])


def test_scan_documents_unknown_importer_and_malformed_models(tmp_path):
    from unityctl.build_size_scan import scan_build_assets

    (tmp_path / "Assets").mkdir()
    (tmp_path / "Packages").mkdir()
    (tmp_path / "Assets/Invalid.glb").write_bytes(b"bad")
    manifest = tmp_path / "Packages/manifest.json"
    manifest.write_text('{"dependencies": {}}')
    report = scan_build_assets(tmp_path, "Standalone", 2048)
    assert report["unchecked"] == {"gltf_importer_unknown": 1}
    assert report["issues"] == []
    manifest.write_text('{"dependencies": {"com.atteneder.gltfast":"5.0.0"}}')
    report = scan_build_assets(tmp_path, "Standalone", 2048)
    assert report["unchecked"] == {"gltf_unreadable": 1}
    assert report["issues"][0]["code"] == "gltf-unreadable"


def test_build_size_cli_is_offline_and_can_fail_a_budget(tmp_path, capsys):
    from unityctl.cli import main

    path = tmp_path / "delivery.zip"
    path.write_bytes(b"too long")
    assert main(["build-size", "--artifact", str(path), "--artifact-budget-mib", "0.000005"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["code"] == "build_size_budget_exceeded"
    assert result["budgets"]["artifact"]["measuredBytes"] == 8


def test_build_size_cli_rejects_non_finite_budget(tmp_path, capsys):
    from unityctl.cli import main

    assert main(["build-size", "--artifact", str(tmp_path), "--artifact-budget-mib", "NaN"]) == 1
    assert json.loads(capsys.readouterr().err)["code"] == "invalid_request"


def test_build_size_cli_can_run_static_scan_without_build(tmp_path, capsys):
    from unityctl.cli import main

    for directory in ("Assets", "Packages", "ProjectSettings"):
        (tmp_path / directory).mkdir()
    args = ["build-size", "--project", str(tmp_path), "--scan-platform", "Standalone"]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["assetScan"]["filesChecked"] == 0
    assert result["budgets"] == {}
    assert main(args + ["--report-budget-mib", "1"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["budgets"]["report"]["status"] == "unverified"


def test_archive_cannot_use_parent_or_old_output_implicitly(tmp_path):
    archive = tmp_path / "copied"
    archive.mkdir()
    outside = tmp_path / "game.apk"
    outside.write_bytes(b"player")
    (archive / "build.log").write_text(block())
    for output in (str(outside), "../game.apk", "."):
        (archive / "build-report.json").write_text(json.dumps(
            {"result": "Succeeded", "outputPath": output}
        ))
        result = analyze_build_size(build_dir=archive, artifact_budget_bytes=50)
        assert result["artifact"] is None
        assert result["budgets"]["artifact"]["status"] == "unverified"


def test_explicit_missing_artifact_is_not_masked_by_valid_log(tmp_path):
    log = tmp_path / "build.log"
    log.write_text(block())
    result = analyze_build_size(log=log, artifact=tmp_path / "missing")
    assert not result["ok"]
    assert result["logReport"]["complete"]


def test_incremental_unity_log_has_actionable_unavailability(tmp_path):
    log = tmp_path / "build.log"
    log.write_text(
        "-------------------------------------------------------------------------------\n"
        "Build Report\nInformation on used Assets is not available, since player data was not rebuilt.\n"
        "Do a clean build to view the Asset build report information.\n"
        "-------------------------------------------------------------------------------\n"
    )
    result = analyze_build_size(log=log, report_budget_bytes=2**20)
    assert result["logReport"]["reason"] == "player_data_not_rebuilt"
    assert "unityctl build --clean" in result["notes"][0]
    assert result["budgets"]["report"]["status"] == "unverified"
