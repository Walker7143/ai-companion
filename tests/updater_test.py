import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_companion import updater


class UpdaterGitTargetTest(unittest.TestCase):
    def test_run_update_registers_gateway_autostart_after_install(self):
        calls: list[str] = []

        with patch.object(updater, "_current_project_root", return_value=Path("project")), patch.object(
            updater, "_stop_gateway_if_needed", return_value=False
        ), patch.object(
            updater,
            "_update_source",
            return_value=updater.SourceUpdate(project_dir=Path("project"), mode="git"),
        ), patch.object(
            updater, "_install_project", side_effect=lambda *_: calls.append("install")
        ), patch.object(
            updater, "_register_gateway_autostart", side_effect=lambda *_: calls.append("autostart")
        ), patch.object(
            updater, "_install_ui_dependencies", side_effect=lambda *_, **__: calls.append("ui")
        ):
            code = updater.run_update(updater.UpdateOptions(restart_gateway=True))

        self.assertEqual(code, 0)
        self.assertEqual(calls, ["install", "autostart", "ui"])

    def test_resolve_git_pull_target_uses_origin_default_when_master_has_no_upstream(self):
        commands: list[tuple[str, ...]] = []

        def fake_run_capture(command, cwd):
            command = tuple(command)
            commands.append(command)
            if command == ("git", "rev-parse", "--abbrev-ref", "HEAD"):
                return subprocess.CompletedProcess(command, 0, b"master\n", b"")
            if command == ("git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"):
                return subprocess.CompletedProcess(command, 1, b"", b"no upstream")
            if command == ("git", "remote"):
                return subprocess.CompletedProcess(command, 0, b"origin\n", b"")
            if command == ("git", "ls-remote", "--heads", "origin", "master"):
                return subprocess.CompletedProcess(command, 0, b"abc\trefs/heads/master\n", b"")
            raise AssertionError(f"Unexpected command: {command}")

        with tempfile.TemporaryDirectory(prefix="updater-git-target-") as td, patch.object(
            updater, "_run_capture", side_effect=fake_run_capture
        ):
            target = updater._resolve_git_pull_target(Path(td))

        self.assertEqual(target, ("origin", "master"))
        self.assertIn(("git", "ls-remote", "--heads", "origin", "master"), commands)

    def test_resolve_git_pull_target_keeps_configured_upstream(self):
        def fake_run_capture(command, cwd):
            command = tuple(command)
            if command == ("git", "rev-parse", "--abbrev-ref", "HEAD"):
                return subprocess.CompletedProcess(command, 0, b"master\n", b"")
            if command == ("git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"):
                return subprocess.CompletedProcess(command, 0, b"origin/main\n", b"")
            raise AssertionError(f"Unexpected command: {command}")

        with tempfile.TemporaryDirectory(prefix="updater-git-target-") as td, patch.object(
            updater, "_run_capture", side_effect=fake_run_capture
        ):
            target = updater._resolve_git_pull_target(Path(td))

        self.assertEqual(target, ("origin", "main"))

    def test_resolve_git_pull_target_rejects_feature_branch_without_remote_match(self):
        def fake_run_capture(command, cwd):
            command = tuple(command)
            if command == ("git", "rev-parse", "--abbrev-ref", "HEAD"):
                return subprocess.CompletedProcess(command, 0, b"feature/local\n", b"")
            if command == ("git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"):
                return subprocess.CompletedProcess(command, 1, b"", b"no upstream")
            if command == ("git", "remote"):
                return subprocess.CompletedProcess(command, 0, b"origin\n", b"")
            if command == ("git", "ls-remote", "--heads", "origin", "feature/local"):
                return subprocess.CompletedProcess(command, 0, b"", b"")
            if command == ("git", "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"):
                return subprocess.CompletedProcess(command, 0, b"origin/master\n", b"")
            raise AssertionError(f"Unexpected command: {command}")

        with tempfile.TemporaryDirectory(prefix="updater-git-target-") as td, patch.object(
            updater, "_run_capture", side_effect=fake_run_capture
        ):
            with self.assertRaises(updater.UpdateError):
                updater._resolve_git_pull_target(Path(td))


if __name__ == "__main__":
    unittest.main()
