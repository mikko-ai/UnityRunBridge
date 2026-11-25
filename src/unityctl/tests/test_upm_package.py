import os
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[3]


def test_upm_archive_omits_macos_metadata_and_uses_canonical_root(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "package-upm.sh"
    shutil.copyfile(ROOT / "scripts/package-upm.sh", script)
    package = tmp_path / "packages/com.mk.unity-agent-bridge"
    package.mkdir(parents=True)
    (package / "package.json").write_text('{"version":"0.6.0"}')
    subfolder = package / "Editor"
    subfolder.mkdir()
    (subfolder / "Entry.cs").write_text("class Entry {}")
    (subfolder / "Entry.cs.meta").write_text("guid: aabb")
    (subfolder / "._Entry.cs").write_bytes(b"macOS attribute data")
    (package / "._package.json").write_bytes(b"macOS attribute data")
    (package / ".DS_Store").write_bytes(b"macOS folder data")
    staging = tmp_path / "safe staging"
    staging.mkdir()
    output = tmp_path / "dist"
    subprocess.run(["bash", str(script)], check=True,
                   env={**os.environ, "TMPDIR": str(staging), "DIST_DIR": str(output)})
    archive, = output.glob("*.tgz")
    with tarfile.open(archive) as package_archive:
        assert {entry.name for entry in package_archive if entry.isfile()} == {
            "package/package.json", "package/Editor/Entry.cs", "package/Editor/Entry.cs.meta",
        }
    assert not list(staging.iterdir())
