"""Self-update support for the ``ai-companion`` command."""

from __future__ import annotations

from dataclasses import dataclass
import locale
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
from typing import Iterable
from urllib.request import urlopen


DEFAULT_ARCHIVE_URL = "https://github.com/Walker7143/ai-companion/archive/refs/heads/master.tar.gz"
MANAGED_SOURCE_DIR = Path.home() / ".ai-companion" / "source" / "ai-companion"
MANAGED_SOURCE_MARKER = ".ai-companion-managed-source"


@dataclass
class UpdateOptions:
    """Options for ``ai-companion update``."""

    restart_gateway: bool = True
    skip_ui: bool = False
    index_url: str | None = None
    archive_url: str = DEFAULT_ARCHIVE_URL


@dataclass
class SourceUpdate:
    project_dir: Path
    mode: str
    before_revision: str | None = None
    after_revision: str | None = None


class UpdateError(RuntimeError):
    """Raised when an update step cannot continue."""


def run_update(options: UpdateOptions | None = None) -> int:
    """Update the current AI Companion install and return a process exit code."""

    options = options or UpdateOptions()
    root = _current_project_root()
    gateway_was_running = False

    print("开始更新 AI Companion...")
    print(f"当前 Python: {sys.executable}")

    try:
        gateway_was_running = _stop_gateway_if_needed(options.restart_gateway)
        source = _update_source(root, options)
        _install_project(source.project_dir, options)
        _install_ui_dependencies(source.project_dir, skip=options.skip_ui)
    except UpdateError as exc:
        print(f"[ERROR] 更新失败: {exc}")
        if gateway_was_running:
            _restart_gateway_after_update()
        return 1
    except KeyboardInterrupt:
        print("\n[ERROR] 更新已取消")
        if gateway_was_running:
            _restart_gateway_after_update()
        return 130

    if gateway_was_running:
        _restart_gateway_after_update()

    print("")
    print("[OK] 更新完成")
    if source.before_revision and source.after_revision:
        if source.before_revision == source.after_revision:
            print(f"代码版本: {source.after_revision} (已是最新)")
        else:
            print(f"代码版本: {source.before_revision} -> {source.after_revision}")
    print("如当前终端仍在运行旧进程，请重新执行 ai-companion start。")
    return 0


def _current_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _stop_gateway_if_needed(enabled: bool) -> bool:
    if not enabled:
        return False

    from ai_companion.gateway import control

    if not control.is_gateway_running():
        return False

    print("检测到 Gateway 正在运行，先停止以便更新...")
    if not control.stop_gateway(silent=True):
        raise UpdateError("Gateway 停止失败，请先手动运行 ai-companion gateway stop")
    return True


def _restart_gateway_after_update() -> None:
    from ai_companion.gateway import control

    print("正在重新启动 Gateway...")
    pid = control.start_gateway(sync=False)
    if pid is None:
        print("[WARN] Gateway 未能自动重启，请手动运行 ai-companion gateway start")


def _update_source(root: Path, options: UpdateOptions) -> SourceUpdate:
    git_root = _find_git_root(root)
    if git_root is not None:
        return _update_git_checkout(git_root)

    print("当前安装不是 git 仓库，改用最新代码包更新。")
    project_dir = _refresh_managed_source(options.archive_url)
    return SourceUpdate(project_dir=project_dir, mode="archive")


def _find_git_root(root: Path) -> Path | None:
    git = shutil.which("git")
    if not git:
        return None

    try:
        result = _run_capture([git, "rev-parse", "--show-toplevel"], cwd=root)
    except OSError:
        return None

    if result.returncode != 0:
        return None

    stdout = _decode_process_output(result.stdout).strip()
    if not stdout:
        return None

    git_root = Path(stdout).resolve()
    if _looks_like_project_root(git_root):
        return git_root
    return None


def _looks_like_project_root(path: Path) -> bool:
    return (path / "ai_companion").is_dir() and (
        (path / "pyproject.toml").is_file() or (path / "setup.py").is_file()
    )


def _update_git_checkout(project_dir: Path) -> SourceUpdate:
    print(f"更新 git 仓库: {project_dir}")
    before = _git_revision(project_dir)

    dirty = _capture(["git", "status", "--porcelain"], cwd=project_dir).strip()
    if dirty:
        print("[WARN] 当前仓库有未提交修改；如与远端冲突，git pull 会停止。")

    remote, branch = _resolve_git_pull_target(project_dir)
    print(f"使用远端 {remote}/{branch} 拉取最新代码...")
    _run(["git", "fetch", "--prune", remote], cwd=project_dir, step="刷新远端引用")
    _run(["git", "pull", "--ff-only", remote, branch], cwd=project_dir, step="拉取最新代码")
    after = _git_revision(project_dir)
    return SourceUpdate(
        project_dir=project_dir,
        mode="git",
        before_revision=before,
        after_revision=after,
    )


def _resolve_git_pull_target(project_dir: Path) -> tuple[str, str]:
    current_branch = _git_current_branch(project_dir)
    if current_branch == "HEAD":
        raise UpdateError("当前处于 detached HEAD，无法自动更新；请切换到可跟踪的分支后重试。")

    try:
        upstream = _capture(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=project_dir).strip()
    except UpdateError:
        upstream = ""

    if upstream and "/" in upstream:
        remote, branch = upstream.split("/", 1)
        return remote, branch

    remote = _primary_git_remote(project_dir)
    if _remote_branch_exists(project_dir, remote, current_branch):
        return remote, current_branch

    default_branch = _remote_default_branch(project_dir, remote)
    if default_branch and current_branch in {"master", "main", default_branch}:
        return remote, default_branch

    raise UpdateError(
        f"当前分支 {current_branch} 没有 upstream，且未找到对应的 {remote}/{current_branch}；"
        "请先切换到主分支，或手动运行 git pull <remote> <branch>"
    )


def _git_current_branch(project_dir: Path) -> str:
    return _capture(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=project_dir).strip()


def _primary_git_remote(project_dir: Path) -> str:
    remotes = [
        line.strip()
        for line in _capture(["git", "remote"], cwd=project_dir).splitlines()
        if line.strip()
    ]
    if not remotes:
        raise UpdateError("当前仓库没有配置远端，无法更新。")
    if "origin" in remotes:
        return "origin"
    if len(remotes) == 1:
        return remotes[0]
    return remotes[0]


def _remote_default_branch(project_dir: Path, remote: str) -> str | None:
    try:
        result = _run_capture(
            ["git", "symbolic-ref", "--quiet", "--short", f"refs/remotes/{remote}/HEAD"],
            cwd=project_dir,
        )
    except OSError:
        result = None
    if result is not None and result.returncode == 0:
        symbolic = _decode_process_output(result.stdout).strip()
        if symbolic:
            return symbolic.split("/", 1)[1] if "/" in symbolic else symbolic

    try:
        result = _run_capture(["git", "ls-remote", "--symref", remote, "HEAD"], cwd=project_dir)
    except OSError:
        return None
    if result.returncode != 0:
        return None

    output = _decode_process_output(result.stdout).splitlines()
    for line in output:
        line = line.strip()
        if line.startswith("ref:") and "\tHEAD" in line:
            ref = line.split(None, 1)[1].split("\t", 1)[0].strip()
            if ref.startswith("refs/heads/"):
                return ref.removeprefix("refs/heads/")
    return None


def _remote_branch_exists(project_dir: Path, remote: str, branch: str) -> bool:
    try:
        result = _run_capture(["git", "ls-remote", "--heads", remote, branch], cwd=project_dir)
    except OSError:
        return False
    if result.returncode != 0:
        return False
    stdout = _decode_process_output(result.stdout).strip()
    return bool(stdout)


def _git_revision(project_dir: Path) -> str | None:
    try:
        return _capture(["git", "rev-parse", "--short", "HEAD"], cwd=project_dir).strip() or None
    except UpdateError:
        return None


def _refresh_managed_source(archive_url: str) -> Path:
    target = MANAGED_SOURCE_DIR
    target.parent.mkdir(parents=True, exist_ok=True)
    _leave_directory_if_inside(target)

    with tempfile.TemporaryDirectory(prefix="ai-companion-update-") as temp_name:
        temp_dir = Path(temp_name)
        archive_path = temp_dir / "source.tar.gz"

        print("下载最新代码包...")
        _download_file(archive_url, archive_path)

        extracted_dir = temp_dir / "extracted"
        extracted_dir.mkdir()
        project_dir = _extract_project_archive(archive_path, extracted_dir)

        backup_dir = target.with_name(f"{target.name}.previous")
        if target.exists():
            if not (target / MANAGED_SOURCE_MARKER).exists():
                raise UpdateError(
                    f"更新缓存目录已存在但不是自动更新创建的目录: {target}\n"
                    "请改用 git 克隆安装，或手动处理该目录后重试。"
                )
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            target.rename(backup_dir)

        try:
            shutil.copytree(
                project_dir,
                target,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
            )
            (target / MANAGED_SOURCE_MARKER).write_text(
                "Managed by ai-companion update. Do not store user data here.\n",
                encoding="utf-8",
            )
            _restore_node_modules(backup_dir, target)
        except Exception as exc:
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            if backup_dir.exists():
                backup_dir.rename(target)
            raise UpdateError(f"刷新本地代码缓存失败: {exc}") from exc
        finally:
            if backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)

    print(f"最新代码已准备: {target}")
    return target


def _restore_node_modules(backup_dir: Path, target: Path) -> None:
    old_node_modules = backup_dir / "ai-companion-ui" / "node_modules"
    new_ui_dir = target / "ai-companion-ui"
    if old_node_modules.exists() and new_ui_dir.exists():
        try:
            shutil.move(str(old_node_modules), str(new_ui_dir / "node_modules"))
        except OSError as exc:
            print(f"[WARN] 复用旧 UI 依赖失败，将重新安装: {exc}")


def _download_file(url: str, destination: Path) -> None:
    try:
        with urlopen(url, timeout=120) as response:
            with open(destination, "wb") as output:
                shutil.copyfileobj(response, output)
    except Exception as exc:
        raise UpdateError(f"下载失败: {exc}") from exc


def _extract_project_archive(archive_path: Path, destination: Path) -> Path:
    try:
        with tarfile.open(archive_path, "r:*") as archive:
            _safe_extract(archive, destination)
    except tarfile.TarError as exc:
        raise UpdateError(f"解压代码包失败: {exc}") from exc

    candidates = [
        path
        for path in destination.iterdir()
        if path.is_dir() and _looks_like_project_root(path)
    ]
    if not candidates:
        raise UpdateError("代码包结构异常，未找到 AI Companion 项目目录")
    return candidates[0]


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if not _is_relative_to(target, destination):
            raise UpdateError(f"代码包包含不安全路径: {member.name}")
        if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
            raise UpdateError(f"代码包包含不支持的文件类型: {member.name}")
        if member.issym() or member.islnk():
            _validate_archive_link(member, destination, target)
    archive.extractall(destination)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _validate_archive_link(member: tarfile.TarInfo, destination: Path, target: Path) -> None:
    link_name = Path(member.linkname)
    if link_name.is_absolute():
        raise UpdateError(f"代码包包含不安全链接: {member.name}")

    if member.issym():
        link_target = (target.parent / link_name).resolve()
    else:
        link_target = (destination / link_name).resolve()

    if not _is_relative_to(link_target, destination):
        raise UpdateError(f"代码包包含不安全链接: {member.name}")


def _leave_directory_if_inside(path: Path) -> None:
    try:
        cwd = Path.cwd().resolve()
        resolved = path.resolve()
    except OSError:
        return

    if _is_relative_to(cwd, resolved):
        os.chdir(Path.home())


def _install_project(project_dir: Path, options: UpdateOptions) -> None:
    print("同步 Python 包和依赖...")
    cmd = [sys.executable, "-m", "pip", "install", "--no-build-isolation"]
    if options.index_url:
        cmd.extend(["-i", options.index_url])
    cmd.extend(["-e", str(project_dir)])
    _run(cmd, cwd=project_dir, step="安装当前项目")


def _install_ui_dependencies(project_dir: Path, skip: bool = False) -> None:
    if skip:
        return

    ui_dir = project_dir / "ai-companion-ui"
    if not (ui_dir / "package.json").exists():
        return

    npm = shutil.which("npm")
    if not npm:
        print("[WARN] npm 未找到，跳过管理后台 UI 依赖同步")
        return

    print("同步管理后台 UI 依赖...")
    result = subprocess.run([npm, "install"], cwd=str(ui_dir))
    if result.returncode != 0:
        print("[WARN] UI 依赖同步失败；如管理后台无法启动，请在 ai-companion-ui 目录手动运行 npm install")


def _run(command: Iterable[str], cwd: Path, step: str) -> None:
    result = subprocess.run(list(command), cwd=str(cwd))
    if result.returncode != 0:
        raise UpdateError(f"{step}失败，退出码 {result.returncode}")


def _capture(command: Iterable[str], cwd: Path) -> str:
    try:
        result = _run_capture(command, cwd=cwd)
    except OSError as exc:
        raise UpdateError(str(exc)) from exc
    stdout = _decode_process_output(result.stdout)
    stderr = _decode_process_output(result.stderr)
    if result.returncode != 0:
        message = stderr.strip() or stdout.strip() or f"退出码 {result.returncode}"
        raise UpdateError(message)
    return stdout


def _run_capture(command: Iterable[str], cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        list(command),
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _decode_process_output(data: bytes | None) -> str:
    if not data:
        return ""

    encodings = ["utf-8-sig", locale.getpreferredencoding(False), sys.getfilesystemencoding()]
    if sys.platform == "win32":
        encodings.extend(["mbcs", "gbk"])

    seen: set[str] = set()
    for encoding in encodings:
        if not encoding or encoding in seen:
            continue
        seen.add(encoding)
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue

    return data.decode("utf-8", errors="replace")
