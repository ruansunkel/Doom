"""Archive integrity and extraction checks for the retained Wine source fetcher."""
import hashlib
import importlib.util
import io
from pathlib import Path
import sys
import tarfile

import pytest

spec = importlib.util.spec_from_file_location(
    "upstream_wine_source", Path(__file__).resolve().parents[1] / "scripts/upstream-wine-source.py")
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


def member(name, content=b"", mode=0o644, kind=tarfile.REGTYPE):
    entry = tarfile.TarInfo(name)
    entry.type, entry.mode = kind, mode
    entry.size = len(content) if entry.isfile() else 0
    if entry.issym() or entry.islnk():
        entry.linkname = "../../escape"
    return entry, io.BytesIO(content)


def archive(monkeypatch, tmp_path, extras=(), omit=()):
    archive_path = tmp_path / f"{source.NAME}.tar.xz"
    with tarfile.open(archive_path, mode="w:xz") as output:
        for name in ("configure", "COPYING.LIB", "VERSION"):
            if name not in omit:
                output.addfile(*member(f"{source.NAME}/{name}", name.encode(), mode=0o755))
        for entry in extras:
            output.addfile(*entry)
    monkeypatch.setattr(source, "SHA256", hashlib.sha256(archive_path.read_bytes()).hexdigest())
    return archive_path


def test_checksum_failure_leaves_no_destination(tmp_path):
    path = tmp_path / "corrupt.tar.xz"
    path.write_bytes(b"corrupted download")
    with pytest.raises(ValueError, match="SHA-256"):
        source.extract(path, tmp_path / "wine")
    assert not (tmp_path / "wine").exists()


@pytest.mark.parametrize("unsafe", [
    member(f"{source.NAME}/../escape"),
    member(f"/{source.NAME}/absolute"),
    member(f"{source.NAME}/link", kind=tarfile.SYMTYPE),
    member(f"{source.NAME}/hardlink", kind=tarfile.LNKTYPE),
    member(f"{source.NAME}/pipe", kind=tarfile.FIFOTYPE),
    member("unrelated/file"),
])
def test_unsafe_entry_rejected_without_partial_tree(monkeypatch, tmp_path, unsafe):
    path = archive(monkeypatch, tmp_path, [unsafe])
    with pytest.raises(ValueError, match="Unsupported source archive entry"):
        source.extract(path, tmp_path / "wine")
    assert sorted(tmp_path.iterdir()) == [path]


def test_extracts_source_and_preserves_executable_bits(monkeypatch, tmp_path):
    path = archive(monkeypatch, tmp_path, [
        member(f"{source.NAME}/dlls/example.c", b"wine source\n"),
    ])
    destination = tmp_path / "wine"
    source.extract(path, destination)
    assert (destination / "configure").read_bytes() == b"configure"
    assert (destination / "configure").stat().st_mode & 0o777 == 0o755
    assert (destination / "dlls/example.c").read_bytes() == b"wine source\n"


@pytest.mark.parametrize("missing", ["configure", "COPYING.LIB", "VERSION"])
def test_missing_required_source_leaves_no_destination(monkeypatch, tmp_path, missing):
    path = archive(monkeypatch, tmp_path, omit=[missing])
    with pytest.raises(ValueError, match="Missing Wine source file"):
        source.extract(path, tmp_path / "wine")
    assert sorted(tmp_path.iterdir()) == [path]


def test_existing_destination_is_preserved(monkeypatch, tmp_path):
    path = archive(monkeypatch, tmp_path)
    destination = tmp_path / "wine"
    destination.mkdir()
    (destination / "file").write_bytes(b"existing")
    with pytest.raises(ValueError, match="already exists"):
        source.extract(path, destination)
    assert (destination / "file").read_bytes() == b"existing"


def test_symlink_parent_cannot_redirect_extraction(monkeypatch, tmp_path):
    path = archive(monkeypatch, tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink parent"):
        source.extract(path, tmp_path / "link/wine")
    assert list(outside.iterdir()) == []


def test_verify_only_uses_cached_archive_without_network(monkeypatch, tmp_path, capsys):
    path = archive(monkeypatch, tmp_path)
    cache = tmp_path / "third_party" / path.name
    cache.parent.mkdir()
    path.rename(cache)
    monkeypatch.setattr(source, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["upstream-wine-source.py", "--verify-only"])

    def no_network(*args, **kwargs):
        pytest.fail("cached archive should not require network access")

    monkeypatch.setattr(source, "urlopen", no_network)
    source.main()
    assert "Verified upstream Wine 11.20" in capsys.readouterr().out
    assert not (cache.parent / source.NAME).exists()
