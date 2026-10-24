"""Relocation tests use tiny native libraries, without a game or Wine prefix."""
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

spec = importlib.util.spec_from_file_location(
    "package_runner", Path(__file__).resolve().parents[1] / "scripts/package-runner.py")
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


def test_java_class_magic_is_not_a_native_library(tmp_path):
    path = tmp_path / "Example.class"
    path.write_bytes(b"\xca\xfe\xba\xbe\x00\x00\x00\x34" + b"\x00" * 1024)
    assert not packager.macho(path)


def test_dependency_filename_collisions_are_rejected(tmp_path):
    package = tmp_path / "package"
    libraries = packager.Libraries(package)
    for folder in ("first", "second"):
        source = tmp_path / folder / "libexample.dylib"
        source.parent.mkdir()
        source.write_bytes(folder.encode())
    libraries.collect(tmp_path / "first/libexample.dylib")
    with pytest.raises(ValueError, match="collision"):
        libraries.collect(tmp_path / "second/libexample.dylib")


def test_package_cannot_contain_external_symlinks(tmp_path):
    package = tmp_path / "package"
    package.mkdir()
    (package / "escape").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="External package symlink"):
        packager.check_package(package)


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires macOS Mach-O tools")
def test_recursive_relocation_survives_missing_build_tree_and_spaces(tmp_path):
    build = tmp_path / "builder"
    build.mkdir()
    (build / "b.c").write_text("int answer(void) { return 42; }\n")
    (build / "a.c").write_text("extern int answer(void); int result(void) { return answer(); }\n")
    library_b = build / "libb.dylib"
    library_a = build / "liba.dylib"
    subprocess.run(["/usr/bin/clang", "-dynamiclib", str(build / "b.c"), "-o", str(library_b),
                    "-Wl,-headerpad_max_install_names", "-install_name", str(library_b)], check=True)
    subprocess.run(["/usr/bin/clang", "-dynamiclib", str(build / "a.c"), str(library_b),
                    "-o", str(library_a), "-Wl,-headerpad_max_install_names",
                    "-install_name", str(library_a)], check=True)
    package = tmp_path / "package with spaces"
    libraries = packager.Libraries(package)
    copied = libraries.collect(library_a)
    libraries.relocate()
    assert packager.check_package(package) == 2
    build.rename(tmp_path / "unavailable-builder")
    moved = tmp_path / "moved package"
    package.rename(moved)
    relocated = moved / copied.relative_to(package)
    output = subprocess.check_output([
        sys.executable, "-c", "import ctypes,sys; print(ctypes.CDLL(sys.argv[1]).result())",
        str(relocated)], text=True)
    assert output.strip() == "42"
