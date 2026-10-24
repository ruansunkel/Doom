"""Verify manifest parsing and package integrity before replacing Steam.exe."""
import hashlib
import importlib.util
import io
from pathlib import Path
import struct
import zipfile

import pytest

spec = importlib.util.spec_from_file_location(
    "steam_bootstrap", Path(__file__).resolve().parents[1] / "scripts/steam-bootstrap.py")
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


def executable(architecture=0x8664):
    data = bytearray(2048)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 128)
    data[128:132] = b'PE\0\0'
    struct.pack_into('<H', data, 132, architecture)
    return bytes(data)


def package(name='steam.exe', architecture=0x8664):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr(name, executable(architecture))
    data = output.getvalue()
    return {'win64': {'steam_win64': {'sha2': hashlib.sha256(data).hexdigest()}}}, data


def test_manifest_preserves_nested_branch_and_signature():
    text = '"win64" { "version" "1" "steam_win64" { "file" "package" } } "kvsign2" { "signature" "abc" }'
    result = bootstrap.parse_manifest(text)
    assert result['win64']['steam_win64']['file'] == 'package'
    assert result['kvsign2']['signature'] == 'abc'


@pytest.mark.parametrize('text', [
    '"win64" { "key" "value"',
    '"win64" { "key" "one" "key" "two" }',
    '"win64" { } unexpected',
    '"win64" }',
])
def test_malformed_manifest_is_rejected(text):
    with pytest.raises(ValueError):
        bootstrap.parse_manifest(text)


def test_validated_package_returns_only_x64_executable():
    manifest, data = package()
    result = bootstrap.bootstrap_data(manifest, data)
    assert bootstrap.machine(result) == 0x8664


def test_tampered_package_is_rejected():
    manifest, data = package()
    with pytest.raises(ValueError, match='SHA-256'):
        bootstrap.bootstrap_data(manifest, data + b'modified')


@pytest.mark.parametrize('name', ['../steam.exe', '/steam.exe', 'bin/steam.exe'])
def test_archive_path_cannot_escape_target(name):
    manifest, data = package(name)
    with pytest.raises(ValueError, match='package contents'):
        bootstrap.bootstrap_data(manifest, data)


def test_32_bit_bootstrapper_is_rejected():
    manifest, data = package(architecture=0x14c)
    with pytest.raises(ValueError, match='not x86_64'):
        bootstrap.bootstrap_data(manifest, data)


def test_existing_x64_client_does_not_download_or_change(tmp_path, monkeypatch):
    target = tmp_path / 'Steam.exe'
    target.write_bytes(executable())

    def forbidden(*args, **kwargs):
        pytest.fail('an existing x64 bootstrapper must remain unchanged')

    monkeypatch.setattr(bootstrap, 'download', forbidden)
    bootstrap.ensure_bootstrap(tmp_path)
    assert target.read_bytes() == executable()
