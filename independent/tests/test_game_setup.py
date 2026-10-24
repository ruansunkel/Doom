"""Fresh-install safety checks use synthetic installers and no Wine processes."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess

import pytest

spec = importlib.util.spec_from_file_location(
    "game_setup", Path(__file__).resolve().parents[1] / "scripts/setup-game.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def executable():
    data = bytearray(2048)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 128)
    data[128:132] = b"PE\0\0"
    return bytes(data)


@pytest.fixture
def workspace(monkeypatch, tmp_path):
    root = tmp_path.resolve() / "workspace"
    root.mkdir()
    monkeypatch.setattr(setup, "ROOT", root)
    return root


def test_prefix_rejects_external_and_symlink_targets(workspace):
    inside = workspace / "build/prefixes"
    inside.mkdir(parents=True)
    assert setup.prefix_path(inside / "new") == inside / "new"
    with pytest.raises(ValueError, match="below"):
        setup.prefix_path(inside)
    with pytest.raises(ValueError, match="inside"):
        setup.prefix_path(workspace.parent / "outside")
    (inside / "linked").symlink_to(workspace.parent, target_is_directory=True)
    with pytest.raises(ValueError, match="inside"):
        setup.prefix_path(inside / "linked/outside")


@pytest.mark.parametrize("payload", [b"<html>error</html>", b"MZ" + b"\0" * 2048])
def test_non_installer_download_is_rejected(tmp_path, payload):
    path = tmp_path / "installer.exe"
    path.write_bytes(payload)
    with pytest.raises(ValueError, match="installer"):
        setup.check_installer(path)


def response(payload, url="https://official.example/installer.exe"):
    class Response(io.BytesIO):
        def geturl(self):
            return url
    return Response(payload)


def test_download_receipt_detects_modified_cache(workspace, monkeypatch):
    payload = executable()
    monkeypatch.setattr(setup, "urlopen", lambda *a, **k: response(payload))
    path = setup.installer("SteamSetup.exe")
    receipt = json.loads(path.with_name(path.name + ".download.json").read_text())
    assert receipt["sha256"] == hashlib.sha256(payload).hexdigest()

    def no_network(*args, **kwargs):
        pytest.fail("a valid cached installer must not be downloaded again")

    monkeypatch.setattr(setup, "urlopen", no_network)
    assert setup.installer("SteamSetup.exe") == path
    path.write_bytes(payload + b"modified")
    with pytest.raises(ValueError, match="differs"):
        setup.installer("SteamSetup.exe")


@pytest.mark.parametrize("payload,url", [
    (b"download error", "https://official.example/installer.exe"),
    (executable(), "http://insecure.example/installer.exe"),
])
def test_failed_download_never_publishes_cache(workspace, monkeypatch, payload, url):
    monkeypatch.setattr(setup, "urlopen", lambda *a, **k: response(payload, url))
    with pytest.raises(ValueError):
        setup.installer("SteamSetup.exe")
    assert list((workspace / ".cache/host-tools").iterdir()) == []


def test_installer_symlink_is_refused(workspace):
    cache = workspace / ".cache/host-tools"
    cache.mkdir(parents=True)
    outside = workspace / "external.exe"
    outside.write_bytes(executable())
    (cache / "SteamSetup.exe").symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        setup.installer("SteamSetup.exe")


def test_client_requires_complete_update_files(workspace):
    steam = workspace / "Steam"
    paths = setup.client_files(steam)
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * (1024 * 1024 + 1))
    assert setup.client_ready(steam)
    paths[-1].write_bytes(b"partial")
    assert not setup.client_ready(steam)


def test_small_tracked_wrapper_counts_as_complete_client(workspace):
    steam = workspace / "Steam"
    for path in setup.client_files(steam):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * (1024 * 1024 + 1))
    cef = steam / "bin/cef/cef.win64"
    helper = cef / "steamwebhelper.exe"
    original = cef / "steamwebhelper_real.exe"
    helper.rename(original)
    helper.write_bytes(b"small own wrapper")
    (cef / ".doom-runner-wrapper.json").write_text(json.dumps({
        "wrapper_sha256": setup.digest(helper), "original_sha256": setup.digest(original),
    }))
    assert setup.client_ready(steam)
    original.write_bytes(b"damaged")
    assert not setup.client_ready(steam)


@pytest.mark.parametrize("state,expected", [("4", True), ("1026", False), ("0", False)])
def test_game_cannot_launch_during_download(workspace, state, expected):
    prefix = workspace / "build/prefixes/game"
    steamapps = prefix / "drive_c/Program Files (x86)/Steam/steamapps"
    game = steamapps / "common/DOOM/DOOMx64vk.exe"
    game.parent.mkdir(parents=True)
    game.write_bytes(b"partial executable")
    assert not setup.game_ready(prefix)
    (steamapps / "appmanifest_379720.acf").write_text(f'"AppState" {{ "StateFlags" "{state}" }}')
    assert setup.game_ready(prefix) is expected
    game.unlink()
    assert not setup.game_ready(prefix)


def test_existing_setup_preserves_installation_and_never_stops_prefix(workspace, monkeypatch):
    prefix = workspace / "build/prefixes/existing"
    steam = prefix / "drive_c/Program Files (x86)/Steam"
    retained = [workspace / "artifacts/wine-upstream/bin/wine",
                workspace / "build/moltenvk-doom2016/MoltenVK/libMoltenVK.dylib",
                workspace / "build/steam-ui/steamwebhelper.exe",
                prefix / "system.reg", prefix / "drive_c/windows/system32/mfc140u.dll",
                steam / "Steam.exe", steam / "steamapps/common/DOOM/DOOMx64vk.exe"]
    for path in retained:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"keep")
    monkeypatch.setattr(setup, "client_ready", lambda *args: True)

    def forbidden(*args, **kwargs):
        pytest.fail("an existing complete installation must not be downloaded or reset")

    monkeypatch.setattr(setup, "installer", forbidden)
    monkeypatch.setattr(setup, "stop_prefix", forbidden)
    monkeypatch.setattr(setup, "bootstrap_client", forbidden)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(setup.subprocess, "run", run)
    setup.setup(prefix)
    assert all(path.read_bytes() == b"keep" for path in retained)
    registry_calls = [call for call in calls if "reg" in call]
    assert len(registry_calls) == 1
    assert registry_calls[0][-3:] == ["/v", "Steam", "/f"]


def test_bootstrap_failure_stops_only_setup_prefix(workspace, monkeypatch):
    prefix = workspace / "build/prefixes/fresh"
    steam = prefix / "Steam"
    steam.mkdir(parents=True)

    class Process:
        def poll(self):
            return 7

        def wait(self, **kwargs):
            return 7

    stopped = []
    commands = []

    def popen(command, **kwargs):
        commands.append(command)
        return Process()

    monkeypatch.setattr(setup.subprocess, "Popen", popen)
    monkeypatch.setattr(setup, "stop_prefix", stopped.append)
    with pytest.raises(ValueError, match="update exited"):
        setup.bootstrap_client(prefix, steam, {}, io.StringIO(), 60)
    assert stopped == [prefix]
    assert "-noverifyfiles" not in commands[0]


def test_completed_update_allows_parent_restart_exit_status(workspace, monkeypatch):
    prefix = workspace / "build/prefixes/fresh"
    steam = prefix / "Steam"
    steam.mkdir(parents=True)
    for path in setup.client_files(steam):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * (1024 * 1024 + 1))
    (steam / "package").mkdir()
    (steam / "package/steam_client_win64.installed").write_text("installed")

    class Process:
        def poll(self):
            return 42

        def wait(self, **kwargs):
            return 42

    stopped, disabled = [], []
    monkeypatch.setattr(setup.subprocess, "Popen", lambda *a, **k: Process())
    monkeypatch.setattr(setup, "stop_prefix", stopped.append)
    monkeypatch.setattr(setup, "disable_autostart", lambda p, *a: disabled.append(p))
    monkeypatch.setattr(setup.time, "sleep", lambda *a: None)
    setup.bootstrap_client(prefix, steam, {}, io.StringIO(), 60)
    assert stopped == disabled == [prefix]
