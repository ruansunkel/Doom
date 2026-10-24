import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile

import pytest

spec = importlib.util.spec_from_file_location(
    "moltenvk_source", Path(__file__).resolve().parents[1] / "scripts/moltenvk-source.py")
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


def archive(monkeypatch, entries):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as output:
        for name, link in entries:
            entry = tarfile.TarInfo(f"{source.ARCHIVE_ROOT}/{name}")
            if link:
                entry.type = tarfile.SYMTYPE
                entry.linkname = link
            output.addfile(entry)
    result = data.getvalue()
    monkeypatch.setattr(source, "SHA256", hashlib.sha256(result).hexdigest())
    return result


def test_checksum_failure_leaves_no_destination(tmp_path):
    destination = tmp_path / "source"
    with pytest.raises(ValueError, match="SHA-256"):
        source.extract(b"corrupted download", destination)
    assert not destination.exists()


@pytest.mark.parametrize("entry", [("../escape", None), ("link", "../../escape")])
def test_unsafe_archive_rejected(monkeypatch, tmp_path, entry):
    data = archive(monkeypatch, [entry])
    with pytest.raises(ValueError):
        source.extract(data, tmp_path / "source")
    assert not (tmp_path / "source").exists()


def test_internal_link_and_existing_destination(monkeypatch, tmp_path):
    data = archive(monkeypatch, [("file", None), ("link", "file")])
    destination = tmp_path / "source"
    source.extract(data, destination)
    assert (destination / "link").is_symlink()
    assert (destination / "link").read_bytes() == b""
    with pytest.raises(ValueError, match="already exists"):
        source.extract(data, destination)
