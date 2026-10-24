import importlib.util
import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location(
    "install_host_deps", Path(__file__).resolve().parents[1] / "scripts/install-host-deps.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

FIXTURE = r'''# Reviewed muniversal 1.1 binary-to-text fallback.
                    if { ! [catch {system "/usr/bin/lipo -create \"${dir1}/${fl}\" \"${dir2}/${fl}\" -output \"${dir}/${fl}\""}] } {
                        # lipo worked
                    } elseif { ! [catch {system "/usr/bin/libtool \"${dir1}/${fl}\" \"${dir2}/${fl}\" -o \"${dir}/${fl}\""}] } {
                        # libtool worked
                    } else {
                        # existing text merge
                    }
'''


class HeaderMergeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="doom-header-tests.")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()

    def test_guards_both_binary_tools_and_preserves_text_fallback(self):
        patched = helper.patch_header_merge(FIXTURE)
        self.assertEqual(patched.count('![string match "*.h" $fl] &&'), 2)
        self.assertEqual(patched.replace('![string match "*.h" $fl] && ', ''), FIXTURE)
        self.assertEqual(helper.patch_header_merge(patched), patched)

    def test_unknown_or_partial_source_is_rejected(self):
        for changed in (
            FIXTURE.replace("lipo -create", "lipo -changed"), FIXTURE + FIXTURE,
            FIXTURE.replace('{ ! [catch', '{ ![string match "*.h" $fl] && ! [catch', 1),
            "unrecognized source",
        ):
            with self.subTest(source=changed), self.assertRaisesRegex(ValueError, "Unrecognized"):
                helper.patch_header_merge(changed)

    @unittest.skipUnless(Path("/usr/bin/tclsh").is_file(), "Tcl interpreter unavailable")
    def test_tcl_short_circuits_both_tools_for_headers(self):
        merge = helper.patch_header_merge(FIXTURE).replace(
            "# lipo worked", "set chosen lipo").replace(
            "# libtool worked", "set chosen libtool").replace(
            "# existing text merge", "set chosen text")
        program = r'''
proc system {command} {
    global calls
    incr calls
    if {[string match "/usr/bin/lipo*" $command]} {error "not a binary"}
}
set dir1 /unused/a
set dir2 /unused/b
set dir /unused/output
foreach fl {gmp.h libgmp.a} {
    set calls 0
''' + merge + '\nputs "$fl:$chosen:$calls"\n}\n'
        result = subprocess.run(["/usr/bin/tclsh"], input=program, text=True,
                                capture_output=True, check=True)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines(), ["gmp.h:text:0", "libgmp.a:libtool:2"])

    def test_atomic_replacement_keeps_original_backup_and_mode(self):
        path = self.directory / "muniversal-1.1.tcl"
        path.write_text(FIXTURE)
        path.chmod(0o644)
        helper.repair_header_merge(path)
        backup = path.with_name(path.name + ".doom-runner-original")
        self.assertEqual(backup.read_text(), FIXTURE)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.read_text(), helper.patch_header_merge(FIXTURE))
        self.assertEqual(path.stat().st_mode & 0o777, 0o644)
        helper.repair_header_merge(path)
        self.assertEqual(backup.read_text(), FIXTURE)
        self.assertEqual(sorted(p.name for p in self.directory.iterdir()), [path.name, backup.name])

    def test_symlinks_are_refused(self):
        for target in ("source", "backup", "parent"):
            with self.subTest(target=target):
                directory = self.directory / target
                directory.mkdir()
                original = directory / "original"
                original.write_text(FIXTURE)
                path = directory / "muniversal-1.1.tcl"
                if target == "source":
                    path.symlink_to(original)
                elif target == "backup":
                    path.write_text(FIXTURE)
                    path.with_name(path.name + ".doom-runner-original").symlink_to(original)
                else:
                    actual = directory / "actual"
                    actual.mkdir()
                    (actual / path.name).write_text(FIXTURE)
                    link = directory / "linked"
                    link.symlink_to(actual, target_is_directory=True)
                    path = link / path.name
                with self.assertRaisesRegex(ValueError, "symlinks"):
                    helper.repair_header_merge(path)
                self.assertEqual(original.read_text(), FIXTURE)

    def test_mismatched_backup_is_preserved(self):
        path = self.directory / "muniversal-1.1.tcl"
        path.write_text(FIXTURE)
        backup = path.with_name(path.name + ".doom-runner-original")
        backup.write_text("previous source")
        with self.assertRaisesRegex(ValueError, "backup differs"):
            helper.repair_header_merge(path)
        self.assertEqual(path.read_text(), FIXTURE)
        self.assertEqual(backup.read_text(), "previous source")

    def test_repair_plan_does_not_mutate_or_run_commands(self):
        output = io.StringIO()
        with mock.patch("sys.argv", ["install-host-deps.py", "--repair-gmp"]), \
                mock.patch.object(helper, "repair_header_merge") as repair, \
                mock.patch.object(helper.subprocess, "run") as command, contextlib.redirect_stdout(output):
            self.assertEqual(helper.main(), 0)
        repair.assert_not_called()
        command.assert_not_called()
        plan = output.getvalue()
        uninstall = f"{helper.PORT} -N uninstall gmp"
        install = f"{helper.PORT} -N -s install gmp +universal"
        self.assertIn(uninstall, plan)
        self.assertIn(install, plan)
        self.assertLess(plan.index(uninstall), plan.index(install))
        self.assertLess(plan.index(install), plan.index(f"{helper.PORT} -N install pkgconfig bison"))
        self.assertNotIn(" -f ", plan)
        self.assertNotIn(" upgrade ", plan)
        self.assertIn("Plan only", plan)
        self.assertIn("-N clean gmp", plan)
        self.assertIn("-N clean nettle", plan)

    def test_older_portgroup_indentation_is_preserved(self):
        old_style = FIXTURE.replace("                    ", "                            ")
        patched = helper.patch_header_merge(old_style)
        self.assertEqual(patched.replace('![string match "*.h" $fl] && ', ''), old_style)
        self.assertEqual(helper.patch_header_merge(patched), patched)

    def test_libffi_plan_preserves_gmp_and_reconfigures_python(self):
        output = io.StringIO()
        with mock.patch("sys.argv", ["install-host-deps.py", "--repair-libffi"]), \
                mock.patch.object(helper, "repair_header_merge") as repair, \
                mock.patch.object(helper.subprocess, "run") as command, contextlib.redirect_stdout(output):
            self.assertEqual(helper.main(), 0)
        repair.assert_not_called()
        command.assert_not_called()
        plan = output.getvalue()
        self.assertIn("muniversal-1.0.tcl", plan)
        self.assertIn("-N uninstall libffi", plan)
        self.assertIn("-N -s install libffi +universal", plan)
        self.assertIn("-N clean python314", plan)
        self.assertNotIn("uninstall gmp", plan)
        self.assertNotIn(" -f ", plan)

    def test_detects_damaged_headers_and_requires_the_matching_repair(self):
        (self.directory / "gmp.h").write_bytes(b"!<arch>\n" + b"invalid C header")
        with self.assertRaisesRegex(ValueError, "--repair-gmp"):
            helper.check_headers(self.directory)
        helper.check_headers(self.directory, repair_gmp=True)
        (self.directory / "gmp.h").write_text("#define GMP_NUMB_BITS 64\n")
        (self.directory / "ffi.h").write_bytes(b"!<arch>\n")
        with self.assertRaisesRegex(ValueError, "--repair-libffi"):
            helper.check_headers(self.directory)
        helper.check_headers(self.directory, repair_libffi=True)

    def test_clean_and_normal_headers_need_no_reinstallation(self):
        helper.check_headers(self.directory)
        (self.directory / "gmp.h").write_text("#define GMP_NUMB_BITS 64\n")
        helper.check_headers(self.directory)

    def test_install_protects_both_mergers_before_macports_and_reports_failure(self):
        paths = [self.directory / f"muniversal-{version}.tcl" for version in ("1.1", "1.0")]
        for path in paths:
            path.write_text(FIXTURE)
        events = []

        def repair(path):
            events.append(("repair", path))

        def run(command, **kwargs):
            self.assertEqual(events[:2], [("repair", path) for path in paths])
            events.append(("command", command))
            if "gnutls" in command:
                raise subprocess.CalledProcessError(1, command)

        errors = io.StringIO()
        with mock.patch("sys.argv", ["install-host-deps.py", "--install"]), \
                mock.patch.object(helper, "PORT", str(paths[0])), \
                mock.patch.object(helper, "PORTGROUP", paths[0]), \
                mock.patch.object(helper, "LIBFFI_PORTGROUP", paths[1]), \
                mock.patch.object(helper.platform, "system", return_value="Darwin"), \
                mock.patch.object(helper.os, "geteuid", return_value=0), \
                mock.patch.object(helper, "reset_build_signals"), \
                mock.patch.object(helper, "check_headers"), \
                mock.patch.object(helper, "repair_header_merge", side_effect=repair), \
                mock.patch.object(helper.subprocess, "run", side_effect=run), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(errors):
            self.assertEqual(helper.main(), 1)
        self.assertIn("MacPorts command failed", errors.getvalue())
        self.assertIn("--repair-gmp", errors.getvalue())
        self.assertIn("config.log", errors.getvalue())

    def test_unknown_second_merger_prevents_all_system_mutations(self):
        first = self.directory / "muniversal-1.1.tcl"
        second = self.directory / "muniversal-1.0.tcl"
        first.write_text(FIXTURE)
        second.write_text("changed upstream source")
        with mock.patch("sys.argv", ["install-host-deps.py", "--install"]), \
                mock.patch.object(helper, "PORT", str(first)), \
                mock.patch.object(helper, "PORTGROUP", first), \
                mock.patch.object(helper, "LIBFFI_PORTGROUP", second), \
                mock.patch.object(helper.platform, "system", return_value="Darwin"), \
                mock.patch.object(helper.os, "geteuid", return_value=0), \
                mock.patch.object(helper, "reset_build_signals"), \
                mock.patch.object(helper, "check_headers"), \
                mock.patch.object(helper, "repair_header_merge") as repair, \
                mock.patch.object(helper.subprocess, "run") as run, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit):
            helper.main()
        repair.assert_not_called()
        run.assert_not_called()
