#!/usr/bin/env python3
"""Upgrade the fresh Steam install's 32-bit updater using Valve's x64 package."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import struct
import tempfile
from urllib.request import urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://client-update.steamstatic.com/"


def parse_manifest(text):
    """Parse the quoted-string/object subset used by Valve's client manifest."""
    tokens = []
    position = 0
    while position < len(text):
        match = re.match(r'\s+|"(?:[^"\\]|\\.)*"|[{}]', text[position:])
        if not match:
            raise ValueError("Unexpected Steam manifest syntax.")
        token = match.group()
        position += len(token)
        if not token.isspace():
            tokens.append(token)
    cursor = 0

    def object_value(nested=False, depth=0):
        nonlocal cursor
        if depth > 8:
            raise ValueError("Steam manifest is nested too deeply.")
        result = {}
        while cursor < len(tokens):
            key = tokens[cursor]
            cursor += 1
            if key == '}' and nested:
                return result
            if not key.startswith('"') or cursor == len(tokens):
                raise ValueError("Incomplete Steam manifest object.")
            key = json.loads(key)
            if key in result:
                raise ValueError("Duplicate Steam manifest key.")
            value = tokens[cursor]
            cursor += 1
            if value == '{':
                result[key] = object_value(True, depth + 1)
            elif value.startswith('"'):
                result[key] = json.loads(value)
            else:
                raise ValueError("Invalid Steam manifest value.")
        if nested:
            raise ValueError("Unclosed Steam manifest object.")
        return result

    return object_value()


def download(url, limit):
    with urlopen(url, timeout=120) as response:
        if not response.geturl().startswith('https://'):
            raise ValueError("Steam download redirected away from HTTPS.")
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Steam bootstrap download exceeded its size limit.")
        return data


def machine(data):
    if len(data) < 64 or data[:2] != b'MZ':
        raise ValueError("Steam bootstrapper is not a Windows executable.")
    offset = struct.unpack_from('<I', data, 60)[0]
    if not 64 <= offset <= len(data) - 6 or data[offset:offset + 4] != b'PE\0\0':
        raise ValueError("Invalid Steam executable header.")
    return struct.unpack_from('<H', data, offset + 4)[0]


def bootstrap_data(manifest, package):
    entry = manifest['win64']['steam_win64']
    if hashlib.sha256(package).hexdigest() != entry['sha2']:
        raise ValueError("Steam bootstrap package SHA-256 mismatch.")
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        members = archive.infolist()
        if (len(members) != 1 or members[0].filename.lower() != 'steam.exe'
                or stat.S_ISLNK(members[0].external_attr >> 16)
                or members[0].file_size > 32 * 1024 * 1024):
            raise ValueError("Unexpected Steam bootstrap package contents.")
        data = archive.read(members[0])
    if machine(data) != 0x8664:
        raise ValueError("Steam bootstrapper is not x86_64.")
    return data


def ensure_bootstrap(steam):
    target = steam / 'Steam.exe'
    if any(parent.is_symlink() for parent in (target, *target.parents)):
        raise ValueError("Refusing a symlink in the Steam bootstrap path.")
    if machine(target.read_bytes()) == 0x8664:
        return
    print("Updating Steam's initial updater to Valve's current x64 version...", flush=True)
    manifest = parse_manifest(download(BASE + 'steam_client_win64', 1024 * 1024).decode('utf-8'))
    entry = manifest['win64']['steam_win64']
    filename = entry['file']
    if (not re.fullmatch(r'steam_win64\.zip\.[0-9a-f]{40}', filename)
            or not re.fullmatch(r'[0-9a-f]{64}', entry['sha2'])
            or not 0 < int(entry['size']) < 16 * 1024 * 1024):
        raise ValueError("Unexpected Steam bootstrap manifest entry.")
    package = download(BASE + filename, int(entry['size']))
    if len(package) != int(entry['size']):
        raise ValueError("Steam bootstrap package size mismatch.")
    data = bootstrap_data(manifest, package)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=steam, prefix='.doom-bootstrap-', delete=False) as output:
            temporary = Path(output.name)
            output.write(data)
            output.flush()
            os.fchmod(output.fileno(), 0o755)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', required=True, type=Path)
    args = parser.parse_args()
    try:
        prefix = args.prefix.expanduser().resolve()
        prefix.relative_to(ROOT / 'build/prefixes')
        ensure_bootstrap(prefix / 'drive_c/Program Files (x86)/Steam')
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        parser.exit(1, f'error: {error}\n')


if __name__ == '__main__':
    main()
