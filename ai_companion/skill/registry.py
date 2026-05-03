"""
SkillRegistry - 技能注册中心

维护已安装 Skills 的元数据，提供 Skills 的发现、加载和管理功能
"""

import json
import logging
import re
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Optional
import importlib.util
import os
import sys

from ..paths import get_user_skills_dir
from .base import Skill
from .instruction import InstructionSkill

logger = logging.getLogger(__name__)

_VALID_SKILL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class SkillRegistry:
    """技能注册中心"""

    def __init__(self, skills_dir: Path = None):
        default_dir = skills_dir is None
        if skills_dir is None:
            skills_dir = get_user_skills_dir()

        self.skills_dir = Path(skills_dir).expanduser()
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._legacy_dirs = self._get_legacy_skill_dirs() if default_dir and not os.environ.get("AI_COMPANION_HOME") else []

        # 已安装的 Skills 元数据缓存
        self._installed: dict[str, dict] = {}
        # 已加载的 Skill 实例缓存
        self._cache: dict[str, Skill] = {}

        # 加载已安装的 Skills 元数据
        self._load_installed()

    def _load_installed(self):
        """从 skills_dir 加载已安装的 Skills 元数据"""
        for root in self._iter_discovery_dirs():
            if not root.exists():
                continue
            for skill_path in root.iterdir():
                self._load_skill_metadata(skill_path, migrate_to_user=(root != self.skills_dir))

    def _iter_discovery_dirs(self) -> list[Path]:
        """Return discovery dirs, with user dir scanned last so it wins."""
        dirs: list[Path] = []
        seen: set[Path] = set()
        for path in [*self._legacy_dirs, self.skills_dir]:
            resolved = path.expanduser().resolve()
            if resolved not in seen:
                seen.add(resolved)
                dirs.append(path)
        return dirs

    def _get_legacy_skill_dirs(self) -> list[Path]:
        project_root = Path(__file__).resolve().parents[2]
        package_root = Path(__file__).resolve().parents[1]
        return [
            project_root / "data" / "bots" / "_skills",
            package_root / "data" / "bots" / "_skills",
        ]

    def _load_skill_metadata(self, skill_path: Path, migrate_to_user: bool = False):
        """Load one skill directory into the installed index."""
        try:
            if not skill_path.is_dir():
                return
            if not skill_path.name.startswith("skill-"):
                return

            skill_json = skill_path / "skill.json"
            if not skill_json.exists():
                return

            with open(skill_json, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

            normalized = self._normalize_metadata(metadata, skill_path)
            if not normalized:
                return
            name = normalized["name"]
            if migrate_to_user:
                dest_dir = self.skills_dir / self._directory_name_for(name)
                if not dest_dir.exists():
                    shutil.copytree(skill_path, dest_dir, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                    self._write_metadata(dest_dir / "skill.json", normalized)
                skill_path = dest_dir
            normalized["path"] = str(skill_path)
            self._installed[name] = normalized
            logger.info(f"[SkillRegistry] 加载技能: {name}")
        except Exception as e:
            logger.warning(f"[SkillRegistry] 加载技能失败 {skill_path}: {e}")

    def list_installed(self) -> list[dict]:
        """列出所有已安装的 Skills"""
        return list(self._installed.values())

    def get_info(self, name: str) -> Optional[dict]:
        """获取指定 Skill 的元数据"""
        return self._installed.get(self._resolve_name(name))

    def is_enabled(self, name: str) -> bool:
        """检查 Skill 是否启用"""
        info = self._installed.get(self._resolve_name(name))
        return info.get("enabled", True) if info else False

    def enable(self, name: str):
        """启用指定 Skill"""
        name = self._resolve_name(name)
        if name not in self._installed:
            return False

        self._installed[name]["enabled"] = True
        self._save_skill_json(name)
        logger.info(f"[SkillRegistry] 启用技能: {name}")
        return True

    def disable(self, name: str):
        """禁用指定 Skill"""
        name = self._resolve_name(name)
        if name not in self._installed:
            return False

        self._installed[name]["enabled"] = False
        self._save_skill_json(name)
        logger.info(f"[SkillRegistry] 禁用技能: {name}")
        return True

    def load_skill(self, name: str) -> Optional[Skill]:
        """加载 Skill 实例"""
        name = self._resolve_name(name)
        if name in self._cache:
            return self._cache[name]

        info = self._installed.get(name)
        if not info:
            return None

        skill_path = Path(info["path"])
        entry_file = self._resolve_entry_file(skill_path, info.get("entry", ""))
        if entry_file is None:
            logger.error(f"[SkillRegistry] 技能入口文件非法: {name}")
            return None
        if info.get("type") == "instruction" and entry_file.name == "SKILL.md":
            skill_instance = InstructionSkill(self._runtime_config_for(name, info))
            self._cache[name] = skill_instance
            logger.info(f"[SkillRegistry] 加载指令型技能实例: {name}")
            return skill_instance
        if not entry_file.exists():
            logger.error(f"[SkillRegistry] 技能入口文件不存在: {entry_file}")
            return None

        try:
            # 动态导入模块
            module_name = f"ai_companion_skill_{self._module_safe_name(name)}"
            spec = importlib.util.spec_from_file_location(module_name, entry_file)
            if not spec or not spec.loader:
                logger.error(f"[SkillRegistry] 无法加载模块: {entry_file}")
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # 查找 Skill 类
            skill_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, Skill) and attr != Skill:
                    skill_class = attr
                    break

            if not skill_class:
                logger.error(f"[SkillRegistry] 未找到 Skill 类: {name}")
                return None

            # 创建实例
            skill_instance = skill_class(self._runtime_config_for(name, info))
            self._cache[name] = skill_instance
            logger.info(f"[SkillRegistry] 加载技能实例: {name}")
            return skill_instance

        except Exception as e:
            logger.error(f"[SkillRegistry] 加载技能失败 {name}: {e}")
            return None

    def register_skill(self, skill_path: Path, force: bool = False, name: str = None) -> Optional[dict]:
        """注册一个新 Skill（从路径）"""
        skill_path = Path(skill_path).expanduser()
        if not skill_path.exists():
            return None

        # 如果是压缩包，先解压
        if self._is_archive(skill_path):
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                self._extract_archive_safely(skill_path, Path(tmpdir))
                # 假设解压后是 skill-name 目录
                extracted = Path(tmpdir)
                for item in extracted.iterdir():
                    if item.is_dir() and item.name.startswith("skill-"):
                        return self._register_from_dir(item, force=force, force_name=name)
                if (extracted / "skill.json").exists():
                    return self._register_from_dir(extracted, force=force, force_name=name)

        # 如果是目录，直接注册
        if skill_path.is_dir():
            return self._register_from_dir(skill_path, force=force, force_name=name)

        return None

    def _register_from_dir(self, skill_dir: Path, force: bool = False, force_name: str = None) -> Optional[dict]:
        """从目录注册 Skill"""
        skill_json = skill_dir / "skill.json"

        try:
            if skill_json.exists():
                with open(skill_json, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            else:
                metadata = self._metadata_from_skill_md(skill_dir)
                if metadata is None:
                    logger.error(f"[SkillRegistry] skill.json 或 SKILL.md 不存在: {skill_dir}")
                    return None

            if force_name:
                metadata["name"] = force_name

            normalized = self._normalize_metadata(metadata, skill_dir)
            if not normalized:
                return None

            name = normalized["name"]
            dest_dir = self.skills_dir / self._directory_name_for(name)
            if dest_dir.exists():
                if not force and skill_dir.resolve() != dest_dir.resolve():
                    logger.warning(f"[SkillRegistry] 技能已存在: {name}")
                    return None

            if dest_dir.exists() and skill_dir.resolve() != dest_dir.resolve():
                shutil.rmtree(dest_dir)
            if skill_dir.resolve() != dest_dir.resolve():
                shutil.copytree(skill_dir, dest_dir)

            # 更新元数据
            normalized["path"] = str(dest_dir)
            self._write_metadata(dest_dir / "skill.json", normalized)
            self._installed[name] = normalized
            self._cache.pop(name, None)

            logger.info(f"[SkillRegistry] 注册技能: {name}")
            return normalized

        except Exception as e:
            logger.error(f"[SkillRegistry] 注册技能失败 {skill_dir}: {e}")
        return None

    def _metadata_from_skill_md(self, skill_dir: Path) -> Optional[dict]:
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            return None
        try:
            content = skill_md.read_text(encoding="utf-8")
        except OSError as e:
            logger.error(f"[SkillRegistry] 读取 SKILL.md 失败 {skill_md}: {e}")
            return None
        frontmatter = self._parse_skill_md_frontmatter(content)
        name = str(frontmatter.get("name") or skill_dir.name.removeprefix("skill-")).strip()
        description = str(frontmatter.get("description") or "").strip()
        return {
            "name": name,
            "version": str(frontmatter.get("version", "1.0.0")),
            "description": description,
            "author": str(frontmatter.get("author", "")),
            "entry": "SKILL.md",
            "enabled": True,
            "requirements": [],
            "type": "instruction",
            "config": {"instruction_file": "SKILL.md"},
        }

    def _parse_skill_md_frontmatter(self, content: str) -> dict:
        if not content.startswith("---"):
            return {}
        match = re.search(r"\n---\s*\n", content[3:])
        if not match:
            return {}
        block = content[3:match.start() + 3]
        data: dict[str, str] = {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().strip("\"'")
            if key:
                data[key] = value
        return data

    def uninstall(self, name: str) -> bool:
        """卸载指定 Skill"""
        name = self._resolve_name(name)
        if name not in self._installed:
            return False

        info = self._installed[name]
        skill_path = Path(info["path"])

        try:
            # 从缓存移除
            if name in self._cache:
                del self._cache[name]

            # 删除目录
            if skill_path.exists():
                shutil.rmtree(skill_path)

            # 从元数据移除
            del self._installed[name]
            logger.info(f"[SkillRegistry] 卸载技能: {name}")
            return True

        except Exception as e:
            logger.error(f"[SkillRegistry] 卸载技能失败 {name}: {e}")
            return False

    def save_skill_secrets(self, name: str, secrets: dict) -> bool:
        """Save per-skill sensitive config outside skill.json."""
        name = self._resolve_name(name or "")
        if name not in self._installed:
            return False
        cleaned = {str(k): str(v) for k, v in (secrets or {}).items() if k and v}
        if not cleaned:
            return False

        info = self._installed[name]
        existing = self._load_secret_config(info)
        existing.update(cleaned)
        path = self._secret_config_path(info)

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            self._cache.pop(name, None)
            logger.info(f"[SkillRegistry] 保存技能敏感配置: {name}")
            return True
        except Exception as e:
            logger.error(f"[SkillRegistry] 保存技能敏感配置失败 {name}: {e}")
            return False

    def create_skill_package(self, name: str, description: str = "", author: str = "", version: str = "1.0.0") -> Path:
        """创建一个新的 Skill 包骨架"""
        name = name.strip().removeprefix("skill-")
        if not _VALID_SKILL_NAME.match(name):
            raise ValueError(f"技能名称非法: {name!r}")

        skill_dir = self.skills_dir / f"skill-{name}"
        skill_dir.mkdir(parents=True, exist_ok=True)

        # 创建 skill.json
        skill_json = skill_dir / "skill.json"
        with open(skill_json, 'w', encoding='utf-8') as f:
            json.dump({
                "name": name,
                "version": version,
                "description": description,
                "author": author,
                "entry": f"{name}_skill.py",
                "enabled": True,
                "requirements": [],
            }, f, indent=2, ensure_ascii=False)

        # 创建示例 Skill 文件
        example_file = skill_dir / f"{name}_skill.py"
        with open(example_file, 'w', encoding='utf-8') as f:
            f.write(f'''"""Skill: {name}"""

from ai_companion.skill.base import Skill, SkillContext, SkillResult


class {name.replace("-", "").title().replace("_", "")}Skill(Skill):
    """自定义技能"""

    name = "{name}"
    description = "{description or name}"
    capabilities = ["{name}"]

    def __init__(self, config: dict = None):
        super().__init__(config)

    async def execute(self, params: dict, context: SkillContext) -> SkillResult:
        """执行技能"""
        # TODO: 实现技能逻辑
        return SkillResult(
            success=True,
            content=f"Skill {name} executed successfully",
            content_type="text",
            metadata={{"skill": self.name}}
        )


# 快捷函数：返回 Skill 实例供注册使用
def create_skill():
    return {name.replace("-", "").title().replace("_", "")}Skill()
''')

        logger.info(f"[SkillRegistry] 创建技能包: {skill_dir}")
        return skill_dir

    def _resolve_name(self, name: str) -> str:
        if name in self._installed:
            return name
        if name.startswith("skill-"):
            stripped = name[len("skill-"):]
            if stripped in self._installed:
                return stripped
        prefixed = f"skill-{name}"
        if prefixed in self._installed:
            return prefixed
        return name

    def _normalize_metadata(self, metadata: dict, skill_dir: Path) -> Optional[dict]:
        if not isinstance(metadata, dict):
            logger.error(f"[SkillRegistry] skill.json 必须是对象: {skill_dir}")
            return None

        name = str(metadata.get("name") or skill_dir.name.removeprefix("skill-")).strip()
        if not name or not _VALID_SKILL_NAME.match(name):
            logger.error(f"[SkillRegistry] 技能名称非法: {name!r}")
            return None

        entry = str(metadata.get("entry") or "").strip()
        if not entry:
            logger.error(f"[SkillRegistry] 技能缺少 entry: {name}")
            return None

        if self._resolve_entry_file(skill_dir, entry) is None:
            logger.error(f"[SkillRegistry] 技能 entry 越界: {name} -> {entry}")
            return None

        requirements = metadata.get("requirements", [])
        if requirements is None:
            requirements = []
        if not isinstance(requirements, list) or not all(isinstance(x, str) for x in requirements):
            logger.error(f"[SkillRegistry] requirements 必须是字符串数组: {name}")
            return None

        normalized = dict(metadata)
        normalized.update({
            "name": name,
            "version": str(metadata.get("version", "1.0.0")),
            "description": str(metadata.get("description", "")),
            "author": str(metadata.get("author", "")),
            "entry": entry,
            "enabled": bool(metadata.get("enabled", True)),
            "requirements": requirements,
        })
        return normalized

    def _write_metadata(self, skill_json: Path, metadata: dict):
        data = dict(metadata)
        data.pop("path", None)
        with open(skill_json, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _save_skill_json(self, name: str):
        """保存 Skill 元数据到 skill.json"""
        info = self._installed.get(name)
        if not info:
            return

        skill_path = Path(info["path"])
        skill_json = skill_path / "skill.json"

        try:
            self._write_metadata(skill_json, info)
        except Exception as e:
            logger.error(f"[SkillRegistry] 保存技能元数据失败 {name}: {e}")

    def _runtime_config_for(self, name: str, info: dict) -> dict:
        config = dict(info.get("config", {}) or {})
        config["_metadata"] = {
            key: value
            for key, value in info.items()
            if key not in {"config"}
        }
        secrets = self._load_secret_config(info)
        if secrets:
            config.update(secrets)
        return config

    def _secret_config_path(self, info: dict) -> Path:
        return Path(info["path"]) / ".skill-secrets.json"

    def _load_secret_config(self, info: dict) -> dict:
        path = self._secret_config_path(info)
        if not path.exists():
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning(f"[SkillRegistry] 读取技能敏感配置失败 {path}: {e}")
            return {}

    def _resolve_entry_file(self, skill_path: Path, entry: str) -> Optional[Path]:
        if not entry:
            return None
        root = skill_path.resolve()
        try:
            target = (skill_path / entry).resolve()
            target.relative_to(root)
        except ValueError:
            return None
        return target

    def _directory_name_for(self, name: str) -> str:
        return name if name.startswith("skill-") else f"skill-{name}"

    def _module_safe_name(self, name: str) -> str:
        return re.sub(r"\W+", "_", name)

    def _is_archive(self, path: Path) -> bool:
        return path.suffix == ".zip" or path.name.endswith((".tar.gz", ".tgz"))

    def _extract_archive_safely(self, archive_path: Path, dest_dir: Path):
        dest_root = dest_dir.resolve()

        def validate_target(member_name: str):
            target = (dest_dir / member_name).resolve()
            try:
                target.relative_to(dest_root)
            except ValueError as exc:
                raise ValueError(f"压缩包包含越界路径: {member_name}") from exc

        if archive_path.suffix == ".zip":
            with zipfile.ZipFile(archive_path, 'r') as zf:
                for member in zf.infolist():
                    validate_target(member.filename)
                zf.extractall(dest_dir)
            return

        with tarfile.open(archive_path, 'r:gz') as tf:
            for member in tf.getmembers():
                validate_target(member.name)
                if member.issym() or member.islnk():
                    raise ValueError(f"压缩包不允许包含链接: {member.name}")
            tf.extractall(dest_dir)
