import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

import psutil

from ai_companion.gateway import control


class GatewayControlTest(unittest.TestCase):
    def test_start_gateway_does_not_redirect_stdio_to_managed_log(self):
        old_pid_file = control.GATEWAY_PID_FILE
        old_log_file = control.GATEWAY_LOG_FILE

        with tempfile.TemporaryDirectory(prefix="gateway-control-") as td:
            root = Path(td)
            control.GATEWAY_PID_FILE = root / "gateway.pid"
            control.GATEWAY_LOG_FILE = root / "gateway.log"
            try:
                with (
                    patch.object(control, "_find_gateway_pids", return_value=[]),
                    patch.object(control.subprocess, "Popen", return_value=SimpleNamespace(pid=12345)) as popen,
                ):
                    self.assertEqual(control.start_gateway(sync=False), 12345)

                _, kwargs = popen.call_args
                self.assertIs(kwargs["stdout"], subprocess.DEVNULL)
                self.assertIs(kwargs["stderr"], subprocess.DEVNULL)
                self.assertEqual(control.GATEWAY_PID_FILE.read_text(encoding="utf-8"), "12345")
            finally:
                control.GATEWAY_PID_FILE = old_pid_file
                control.GATEWAY_LOG_FILE = old_log_file

    def test_stop_finds_gateway_process_without_pid_file(self):
        marker = "ai_companion_gateway_test_marker_stop_scan"
        old_patterns = control._GATEWAY_PROCESS_PATTERNS
        old_pid_file = control.GATEWAY_PID_FILE
        old_log_file = control.GATEWAY_LOG_FILE
        proc = None

        with tempfile.TemporaryDirectory(prefix="gateway-control-") as td:
            root = Path(td)
            control._GATEWAY_PROCESS_PATTERNS = (marker,)
            control.GATEWAY_PID_FILE = root / "missing.pid"
            control.GATEWAY_LOG_FILE = root / "gateway.log"
            with patch.dict("os.environ", {"AI_COMPANION_GATEWAY_PID_FILE": str(control.GATEWAY_PID_FILE)}):
                proc = subprocess.Popen(
                    [sys.executable, "-c", "import time; time.sleep(60)", marker],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                try:
                    deadline = time.time() + 5
                    while time.time() < deadline and proc.poll() is not None:
                        time.sleep(0.1)
                    self.assertIsNone(proc.poll())
                    self.assertIn(proc.pid, control._find_gateway_pids())

                    self.assertTrue(control.stop_gateway(silent=True))

                    proc.wait(timeout=10)
                    self.assertFalse(psutil.pid_exists(proc.pid))
                    self.assertFalse(control.GATEWAY_PID_FILE.exists())
                finally:
                    control._GATEWAY_PROCESS_PATTERNS = old_patterns
                    control.GATEWAY_PID_FILE = old_pid_file
                    control.GATEWAY_LOG_FILE = old_log_file
                    if proc and proc.poll() is None:
                        proc.kill()
                        proc.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
