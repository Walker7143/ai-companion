"""
ImageGenerationSkill - 图片生成技能

支持 MiniMax 图片生成；其他 provider 需在实现后再声明。
"""

import os
import logging
from pathlib import Path
from typing import Optional

from .base import Skill, SkillContext, SkillResult

logger = logging.getLogger(__name__)


class ImageGenerationSkill(Skill):
    """图片生成技能"""

    name = "image_generation"
    description = "根据文字描述生成图片"
    capabilities = ["image_generation"]
    supported_models = ["minimax"]

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.output_dir = Path(self.config.get("output_dir", "data/bots/_images"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if not self.default_model:
            self.default_model = self.config.get("model", "minimax")

    def _check_config(self) -> bool:
        """检查配置是否完整"""
        model = self.default_model or self.config.get("model")
        if model and model not in self.supported_models:
            return False
        return bool(os.environ.get("MINIMAX_API_KEY") or self.config.get("api_key"))

    async def execute(self, params: dict, context: SkillContext) -> SkillResult:
        """执行图片生成"""
        prompt = params.get("prompt")
        if not prompt:
            return SkillResult(success=False, content="缺少 prompt 参数")

        model = params.get("model") or self.default_model or self.config.get("model", "minimax")
        if not model:
            return SkillResult(success=False, content="未指定模型且未配置默认模型")

        try:
            if model == "minimax":
                return await self._generate_minimax(prompt, params)
            else:
                return SkillResult(success=False, content=f"不支持的模型: {model}")
        except Exception as e:
            logger.error(f"[ImageGenerationSkill] 生成失败: {e}")
            return SkillResult(success=False, content=str(e))

    async def _generate_minimax(self, prompt: str, params: dict) -> SkillResult:
        """MiniMax 图片生成 API - text_to_image"""
        try:
            import aiohttp
            import json
            import uuid
            from pathlib import Path

            # 优先从 params 获取（调用者传入），其次从环境变量，再次从配置
            api_key = params.get("api_key") or os.environ.get("MINIMAX_API_KEY")
            base_url = "https://api.minimax.chat/v1"  # 默认值

            if not api_key:
                # 尝试从 MiniMaxAdapter 获取
                model = params.get("model_adapter")
                if model and hasattr(model, 'api_key'):
                    api_key = model.api_key
                    base_url = model.base_url

            if not api_key:
                return SkillResult(success=False, content="MiniMax API Key 未配置")

            # base_url 已经是 https://api.minimax.chat/v1
            # 直接拼接路径即可
            url = f"{base_url}/image_generation"

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": self.config.get("minimax_model", "image-01"),
                "prompt": prompt,
                "image_size": params.get("size", "1:1"),
                "image_num": params.get("num", 1),
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise RuntimeError(f"MiniMax image API error {resp.status}: {error_text}")

                    data = await resp.json()

                    # MiniMax 返回的是 base64 图片或图片URL
                    images = data.get("data", {}).get("image_urls", [])
                    if not images:
                        return SkillResult(success=False, content="未获取到图片URL")

                    # 保存第一张图片
                    image_url = images[0]
                    output_file = self.output_dir / f"minimax_{uuid.uuid4().hex[:8]}.png"

                    # 下载图片
                    async with session.get(image_url) as img_resp:
                        if img_resp.status != 200:
                            return SkillResult(success=False, content=f"下载图片失败: {img_resp.status}")
                        content = await img_resp.read()
                        with open(output_file, 'wb') as f:
                            f.write(content)

                    logger.info(f"[ImageGenerationSkill] MiniMax 生成成功: {output_file}")
                    return SkillResult(
                        success=True,
                        content=str(output_file),
                        content_type="image",
                        metadata={
                            "model": "minimax",
                            "prompt": prompt,
                            "image_url": image_url,
                        }
                    )
        except ImportError:
            return SkillResult(success=False, content="需要安装 aiohttp: pip install aiohttp")
        except Exception as e:
            logger.error(f"[ImageGenerationSkill] MiniMax 生成失败: {e}")
            return SkillResult(success=False, content=str(e))
