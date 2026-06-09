from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InstallScriptsStaticTest(unittest.TestCase):
    def read_script(self, name: str) -> str:
        return (ROOT / "scripts" / name).read_text(encoding="utf-8")

    def test_macos_linux_global_installer_supports_pipe_execution(self):
        script = self.read_script("install.sh")
        self.assertIn("prepare_project_dir", script)
        self.assertIn("ARCHIVE_URL=", script)
        self.assertIn("PROJECT_DIR=", script)
        self.assertNotIn('readlink -f "$0"', script)
        self.assertNotIn("cp config/", script)
        self.assertIn('docker build -t ai-companion "$PROJECT_DIR"', script)

    def test_shell_installers_do_not_require_bc_for_python_version_check(self):
        for name in ("install.sh", "install-cn.sh"):
            with self.subTest(name=name):
                script = self.read_script(name)
                self.assertNotIn("| bc", script)
                self.assertIn("sys.version_info >= (3, 11)", script)

    def test_windows_installers_define_venv_python_before_using_it(self):
        for name in ("install.ps1", "install-global.ps1", "install-cn.ps1"):
            with self.subTest(name=name):
                script = self.read_script(name)
                assignment = '$venvPython = "$venvDir\\Scripts\\python.exe"'
                use = "& $venvPython -m ai_companion.embedding_setup"
                self.assertIn(assignment, script)
                self.assertIn(use, script)
                self.assertLess(script.index(assignment), script.index(use))


if __name__ == "__main__":
    unittest.main()
