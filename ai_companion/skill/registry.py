"""
SkillRegistry - 技能注册中心

维护已安装 Skills 的元数据，提供 Skills 的发现、加载和管理功能
"""

import json
import logging
from pathlib import Path
from typing import Optional
import importlib.util
import sys

from .base import Skill, SkillInfo

logger = logging.getLogger(__name__)


class SkillRegistry:
    """技能注册中心"""

    def __init__(self, skills_dir: Path = None):
        if skills_dir is None:
            # 默认使用 data/bots/_skills 目录
            skills_dir = Path(__file__).parent.parent.parent / "data" / "bots" / "_skills"

        self.skills_dir = skills_dir
        self.skills_dir.mkdir(parents=True, exist_ok=True)

        # 已安装的 Skills 元数据缓存
        self._installed: dict[str, dict] = {}
        # 已加载的 Skill 实例缓存
        self._cache: dict[str, Skill] = {}

        # 加载已安装的 Skills 元数据
        self._load_installed()

    def _load_installed(self):
        """从 skills_dir 加载已安装的 Skills 元数据"""
        if not self.skills_dir.exists():
            return

        for skill_path in self.skills_dir.iterdir():
            if not skill_path.is_dir():
                continue
            if not skill_path.name.startswith("skill-"):
                continue

            skill_json = skill_path / "skill.json"
            if not skill_json.exists():
                continue

            try:
                with open(skill_json, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)

                name = metadata.get("name", skill_path.name)
                self._installed[name] = {
                    "name": name,
                    "version": metadata.get("version", "1.0.0"),
                    "description": metadata.get("description", ""),
                    "author": metadata.get("author", ""),
                    "path": str(skill_path),
                    "entry": metadata.get("entry", ""),
                    "enabled": metadata.get("enabled", True),
                    "requirements": metadata.get("requirements", []),
                }
                logger.info(f"[SkillRegistry] 加载技能: {name}")
            except Exception as e:
                logger.warning(f"[SkillRegistry] 加载技能失败 {skill_path}: {e}")

    def list_installed(self) -> list[dict]:
        """列出所有已安装的 Skills"""
        return list(self._installed.values())

    def get_info(self, name: str) -> Optional[dict]:
        """获取指定 Skill 的元数据"""
        return self._installed.get(name)

    def is_enabled(self, name: str) -> bool:
        """检查 Skill 是否启用"""
        info = self._installed.get(name)
        return info.get("enabled", True) if info else False

    def enable(self, name: str):
        """启用指定 Skill"""
        if name not in self._installed:
            return False

        self._installed[name]["enabled"] = True
        self._save_skill_json(name)
        logger.info(f"[SkillRegistry] 启用技能: {name}")
        return True

    def disable(self, name: str):
        """禁用指定 Skill"""
        if name not in self._installed:
            return False

        self._installed[name]["enabled"] = False
        self._save_skill_json(name)
        logger.info(f"[SkillRegistry] 禁用技能: {name}")
        return True

    def _save_skill_json(self, name: str):
        """保存 Skill 元数据到 skill.json"""
        info = self._installed.get(name)
        if not info:
            return

        skill_path = Path(info["path"])
        skill_json = skill_path / "skill.json"

        try:
            with open(skill_json, 'w', encoding='utf-8') as f:
                json.dump({
                    "name": info["name"],
                    "version": info["version"],
                    "description": info["description"],
                    "author": info["author"],
                    "entry": info["entry"],
                    "enabled": info["enabled"],
                    "requirements": info.get("requirements", []),
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[SkillRegistry] 保存技能元数据失败 {name}: {e}")

    def load_skill(self, name: str) -> Optional[Skill]:
        """加载 Skill 实例"""
        if name in self._cache:
            return self._cache[name]

        info = self._installed.get(name)
        if not info:
            return None

        skill_path = Path(info["path"])
        entry_file = skill_path / info.get("entry", "")
        if not entry_file.exists():
            logger.error(f"[SkillRegistry] 技能入口文件不存在: {entry_file}")
            return None

        try:
            # 动态导入模块
            module_name = f"skill_{name}"
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
            skill_instance = skill_class()
            self._cache[name] = skill_instance
            logger.info(f"[SkillRegistry] 加载技能实例: {name}")
            return skill_instance

        except Exception as e:
            logger.error(f"[SkillRegistry] 加载技能失败 {name}: {e}")
            return None

    def register_skill(self, skill_path: Path) -> Optional[dict]:
        """注册一个新 Skill（从路径）"""
        if not skill_path.exists():
            return None

        # 如果是压缩包，先解压
        if skill_path.suffix in (".zip", ".tar.gz", ".tgz"):
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                import shutil
                shutil.extractall(tmpdir, skill_path)
                # 假设解压后是 skill-name 目录
                extracted = Path(tmpdir)
                for item in extracted.iterdir():
                    if item.is_dir() and item.name.startswith("skill-"):
                        return self._register_from_dir(item)

        # 如果是目录，直接注册
        if skill_path.is_dir():
            return self._register_from_dir(skill_path)

        return None

    def _register_from_dir(self, skill_dir: Path) -> Optional[dict]:
        """从目录注册 Skill"""
        skill_json = skill_dir / "skill.json"
        if not skill_json.exists():
            logger.error(f"[SkillRegistry] skill.json 不存在: {skill_dir}")
            return None

        try:
            with open(skill_json, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

            name = metadata.get("name")
            if not name:
                name = skill_dir.name
                metadata["name"] = name

            # 复制到 skills_dir
            dest_dir = self.skills_dir / skill_dir.name
            if dest_dir.exists():
                logger.warning(f"[SkillRegistry] 技能已存在: {name}")

            import shutil
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            shutil.copytree(skill_dir, dest_dir)

            # 更新元数据
            metadata["path"] = str(dest_dir)
            self._installed[name] = metadata

            logger.info(f"[SkillRegistry] 注册技能: {name}")
            return metadata

        except Exception as e:
            logger.error(f"[SkillRegistry] 注册技能失败 {skill_dir}: {e}")
            return None

    def uninstall(self, name: str) -> bool:
        """卸载指定 Skill"""
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
                import shutil
                shutil.rmtree(skill_path)

            # 从元数据移除
            del self._installed[name]
            logger.info(f"[SkillRegistry] 卸载技能: {name}")
            return True

        except Exception as e:
            logger.error(f"[SkillRegistry] 卸载技能失败 {name}: {e}")
            return False

    def create_skill_package(self, name: str, description: str = "", author: str = "", version: str = "1.0.0") -> Path:
        """创建一个新的 Skill 包骨架"""
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