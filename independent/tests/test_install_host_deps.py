"""Check inherited-signal handling without invoking MacPorts or root commands."""
import contextlib
import importlib.util
import io
from pathlib import Path
import signal
import subprocess
import sys
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/install-host-deps.py"
spec = importlib.util.spec_from_file_location("install_host_deps", SCRIPT)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallHostDepsTests(unittest.TestCase):
    @unittest.skipUnless(hasattr(signal, "pthread_sigmask"), "requires POSIX signal masks")
    def test_reset_unblocks_alarm_and_restores_default_handlers_in_child(self):
        # Change only this child's mask. A failed reset is killed by the timeout,
        # so the regression cannot hang the suite or alter the test runner.
        child = """
import importlib.util
import signal
import sys
import time
spec = importlib.util.spec_from_file_location("install_host_deps", sys.argv[1])
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM, signal.SIGTERM})
for signum in (signal.SIGALRM, signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
    signal.signal(signum, signal.SIG_IGN)
installer.reset_build_signals()
assert not signal.pthread_sigmask(signal.SIG_BLOCK, set())
for signum in (signal.SIGALRM, signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
    assert signal.getsignal(signum) == signal.SIG_DFL
print("alarm armed", flush=True)
signal.alarm(1)
time.sleep(30)
raise SystemExit("alarm never fired")
"""
        result = subprocess.run(
            [sys.executable, "-c", child, str(SCRIPT)],
            capture_output=True, text=True, timeout=5, check=False,
        )
        self.assertEqual(result.returncode, -signal.SIGALRM, result.stderr)
        self.assertIn("alarm armed", result.stdout)

    def test_default_only_prints_plan_without_commands_or_signal_changes(self):
        output = io.StringIO()
        with patch.object(sys, "argv", [str(SCRIPT)]), \
                patch.object(installer.subprocess, "run") as run, \
                patch.object(installer, "reset_build_signals") as reset, \
                contextlib.redirect_stdout(output):
            self.assertEqual(installer.main(), 0)
        run.assert_not_called()
        reset.assert_not_called()
        for command in installer.COMMANDS:
            self.assertIn(" ".join(command), output.getvalue())
        self.assertIn("Plan only", output.getvalue())

    def test_install_rejects_non_macos_or_unprivileged_caller(self):
        for system, effective_uid in (("Darwin", 1000), ("Linux", 0)):
            with self.subTest(system=system, effective_uid=effective_uid):
                stderr = io.StringIO()
                with patch.object(sys, "argv", [str(SCRIPT), "--install"]), \
                        patch.object(installer.platform, "system", return_value=system), \
                        patch.object(installer.os, "geteuid", return_value=effective_uid), \
                        patch.object(installer.subprocess, "run") as run, \
                        patch.object(installer, "reset_build_signals") as reset, \
                        contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
                    installer.main()
                self.assertEqual(error.exception.code, 2)
                self.assertIn("administrator privileges", stderr.getvalue())
                run.assert_not_called()
                reset.assert_not_called()


if __name__ == "__main__":
    unittest.main()
