"""Reject corrupted or unsafe native development-tool archives."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile

import pytest

spec = importlib.util.spec_from_file_location(
    "host_dev_setup", Path(__file__).resolve().parents[1] / "scripts/setup-host-dev.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def archive(tmp_path, replacement=None):
    path = tmp_path / "shellcheck.tar.xz"
    with tarfile.open(path, "w:xz") as output:
        for name in ("shellcheck", "LICENSE.txt", "README.txt"):
            entry = tarfile.TarInfo(f"shellcheck-v{setup.VERSION}/{name}")
            entry.size = 4
            if name == "shellcheck" and replacement:
                entry = replacement
            output.addfile(entry, io.BytesIO(b"test") if entry.isfile() else None)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_valid_package_preserves_license_and_executable(tmp_path):
    path, digest = archive(tmp_path)
    destination = tmp_path / "installed"
    setup.extract_shellcheck(path, destination, digest)
    assert (destination / "shellcheck").read_bytes() == b"test"
    assert (destination / "shellcheck").stat().st_mode & 0o777 == 0o755
    assert (destination / "LICENSE.txt").is_file()


def test_checksum_failure_leaves_no_installation(tmp_path):
    path, _ = archive(tmp_path)
    with pytest.raises(ValueError, match="SHA-256"):
        setup.extract_shellcheck(path, tmp_path / "installed", "0" * 64)
    assert not (tmp_path / "installed").exists()


@pytest.mark.parametrize("kind,name", [
    (tarfile.REGTYPE, "../escape"),
    (tarfile.REGTYPE, "/absolute"),
    (tarfile.SYMTYPE, "shellcheck"),
    (tarfile.LNKTYPE, "shellcheck"),
])
def test_unsafe_package_is_not_extracted(tmp_path, kind, name):
    entry = tarfile.TarInfo(f"shellcheck-v{setup.VERSION}/{name}" if not name.startswith('/') else name)
    entry.type, entry.linkname = kind, "../../escape"
    entry.size = 4 if entry.isfile() else 0
    path, digest = archive(tmp_path, entry)
    with pytest.raises(ValueError, match="Unsafe or unexpected"):
        setup.extract_shellcheck(path, tmp_path / "installed", digest)
    assert not (tmp_path / "installed").exists()
    assert not (tmp_path / "escape").exists()


def test_existing_destination_and_symlink_are_preserved(tmp_path):
    path, digest = archive(tmp_path)
    destination = tmp_path / "installed"
    destination.mkdir()
    (destination / "user-file").write_text("keep")
    with pytest.raises(ValueError, match="already exists"):
        setup.extract_shellcheck(path, destination, digest)
    assert (destination / "user-file").read_text() == "keep"
    link = tmp_path / "link"
    link.symlink_to(destination, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        setup.extract_shellcheck(path, link / "redirected", digest)
    assert not (destination / "redirected").exists()
