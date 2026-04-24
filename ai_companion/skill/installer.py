"""
SkillInstaller - 技能安装器

负责从各种来源安装新的 Skills
"""

import hashlib
import json
import logging
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

import httpx

from .base import Skill, SkillContext, SkillResult
from .registry import SkillRegistry

logger = logging.getLogger(__name__)


class SkillInstaller:
    """技能安装器"""

    def __init__(self, registry: SkillRegistry = None):
        self.registry = registry or SkillRegistry()

    def install_from_path(self, skill_path: Path, name: str = None) -> Optional[dict]:
        """
        从本地路径安装 Skill

        Args:
            skill_path: Skill 包路径（目录或压缩包）
            name: 可选的强制名称

        Returns:
            Skill 元数据或 None
        """
        skill_path = Path(skill_path)

        if not skill_path.exists():
            logger.error(f"[SkillInstaller] 路径不存在: {skill_path}")
            return None

        # 处理压缩包
        if skill_path.suffix in (".zip", ".tar.gz", ".tgz"):
            return self._install_from_archive(skill_path)

        # 处理目录
        if skill_path.is_dir():
            return self._install_from_dir(skill_path, name)

        logger.error(f"[SkillInstaller] 不支持的路径类型: {skill_path}")
        return None

    def _install_from_archive(self, archive_path: Path) -> Optional[dict]:
        """从压缩包安装"""
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)

                # 解压
                if archive_path.suffix == ".zip":
                    with zipfile.ZipFile(archive_path, 'r') as zf:
                        zf.extractall(tmp_path)
                else:
                    import tarfile
                    with tarfile.open(archive_path, 'r:gz') as tf:
                        tf.extractall(tmp_path)

                # 查找 skill-* 目录
                for item in tmp_path.iterdir():
                    if item.is_dir() and item.name.startswith("skill-"):
                        return self._install_from_dir(item)

                # 如果压缩包内容没有 skill- 前缀，尝试用父目录名
                for item in tmp_path.iterdir():
                    if item.is_dir():
                        # 重命名为 skill- 前缀
                        new_name = f"skill-{item.name}"
                        new_path = tmp_path / new_name
                        item.rename(new_path)
                        return self._install_from_dir(new_path)

                logger.error(f"[SkillInstaller] 压缩包中未找到技能目录: {archive_path}")
                return None

        except Exception as e:
            logger.error(f"[SkillInstaller] 解压失败 {archive_path}: {e}")
            return None

    def _install_from_dir(self, skill_dir: Path, force_name: str = None) -> Optional[dict]:
        """从目录安装"""
        skill_json = skill_dir / "skill.json"

        if not skill_json.exists():
            logger.error(f"[SkillInstaller] skill.json 不存在: {skill_dir}")
            return None

        try:
            with open(skill_json, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

            name = force_name or metadata.get("name")
            if not name:
                name = skill_dir.name
                metadata["name"] = name

            # 验证名称格式
            if not name.startswith("skill-"):
                name = f"skill-{name}"
                metadata["name"] = name

            # 检查依赖
            requirements = metadata.get("requirements", [])
            if requirements:
                if not self._check_requirements(requirements):
                    logger.warning(f"[SkillInstaller] 依赖未满足: {requirements}")

            # 使用 registry 注册
            result = self.registry.register_skill(skill_dir)
            if result:
                logger.info(f"[SkillInstaller] 安装成功: {name}")
                return result

            return None

        except Exception as e:
            logger.error(f"[SkillInstaller] 读取元数据失败 {skill_dir}: {e}")
            return None

    def install_from_url(self, url: str, name: str = None) -> Optional[dict]:
        """
        从 URL 安装 Skill

        Args:
            url: Skill 包 URL（支持 .zip）
            name: 可选的强制名称

        Returns:
            Skill 元数据或 None
        """
        if not url.startswith(("http://", "https://")):
            logger.error(f"[SkillInstaller] 无效的 URL: {url}")
            return None

        try:
            logger.info(f"[SkillInstaller] 下载技能包: {url}")

            # 下载文件
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)

                with httpx.stream("GET", url, follow_redirects=True, timeout=60) as resp:
                    if resp.status_code != 200:
                        logger.error(f"[SkillInstaller] 下载失败: {resp.status_code}")
                        return None

                    # 获取文件名
                    content_disposition = resp.headers.get("content-disposition", "")
                    filename = self._extract_filename(content_disposition, url) or "skill.zip"

                    archive_path = tmp_path / filename
                    with open(archive_path, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=8192):
                            f.write(chunk)

                # 验证文件
                if not self._verify_archive(archive_path):
                    logger.error(f"[SkillInstaller] 验证失败: {archive_path}")
                    return None

                # 安装
                return self.install_from_path(archive_path, name)

        except Exception as e:
            logger.error(f"[SkillInstaller] 下载失败 {url}: {e}")
            return None

    def _extract_filename(self, content_disposition: str, url: str) -> Optional[str]:
        """从 content-disposition 或 URL 提取文件名"""
        if content_disposition:
            match = re.search(r'filename[^;=\n]*=((["\']).*?\2|[^;\n]*)', content_disposition)
            if match:
                return match.group(1).strip('"\'')

        # 从 URL 提取
        parsed = url.split("?")[0]
        if "/" in parsed:
            filename = parsed.rsplit("/", 1)[1]
            if "." in filename:
                return filename

        return None

    def _verify_archive(self, archive_path: Path) -> bool:
        """验证压缩包完整性"""
        try:
            if archive_path.suffix == ".zip":
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    return zf.testzip() is None
            else:
                import tarfile
                with tarfile.open(archive_path, 'r:gz') as tf:
                    return True
        except Exception as e:
            logger.error(f"[SkillInstaller] 验证失败: {e}")
            return False

    def _check_requirements(self, requirements: list[str]) -> bool:
        """检查依赖是否满足"""
        import importlib
        missing = []

        for req in requirements:
            # 解析简单的包名（忽略版本号）
            pkg_name = re.split(r'[!=<>]', req)[0].strip()
            if pkg_name:
                try:
                    importlib.import_module(pkg_name)
                except ImportError:
                    missing.append(pkg_name)

        if missing:
            logger.warning(f"[SkillInstaller] 缺少依赖: {missing}")
            return False
        return True

    def install_from_git(self, git_url: str, name: str = None) -> Optional[dict]:
        """
        从 Git 仓库安装 Skill

        Args:
            git_url: Git 仓库 URL
            name: 可选的强制名称

        Returns:
            Skill 元数据或 None
        """
        # 检查 git 是否可用
        try:
            import subprocess
            subprocess.run(["git", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("[SkillInstaller] git 命令不可用")
            return None

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)

                # 克隆仓库
                import subprocess
                result = subprocess.run(
                    ["git", "clone", "--depth", "1", git_url, str(tmp_path)],
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                if result.returncode != 0:
                    logger.error(f"[SkillInstaller] git clone 失败: {result.stderr}")
                    return None

                # 查找 skill-* 目录
                for item in tmp_path.iterdir():
                    if item.is_dir() and item.name.startswith("skill-"):
                        return self._install_from_dir(item, name)

                # 尝试直接安装
                return self._install_from_dir(tmp_path, name)

        except Exception as e:
            logger.error(f"[SkillInstaller] git 安装失败: {e}")
            return None

    def create_scaffold(self, name: str, description: str = "", author: str = "") -> Optional[Path]:
        """
        创建技能脚手架

        Args:
            name: 技能名称
            description: 技能描述
            author: 作者

        Returns:
            技能目录路径或 None
        """
        return self.registry.create_skill_package(name, description, author)
