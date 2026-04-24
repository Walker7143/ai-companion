"""
TTSSkill - 文字转语音技能

支持多种 TTS 模型：MiniMax, Edge TTS, Azure TTS 等
"""

import os
import logging
from pathlib import Path
from typing import Optional

from .base import Skill, SkillContext, SkillResult

logger = logging.getLogger(__name__)


class TTSSkill(Skill):
    """文字转语音技能"""

    name = "tts"
    description = "将文字转换为语音"
    capabilities = ["tts"]
    supported_models = ["minimax", "edge_tts", "azure_tts"]

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.output_dir = Path(self.config.get("output_dir", "data/bots/_audio"))
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _check_config(self) -> bool:
        return True  # 暂时允许无配置

    async def execute(self, params: dict, context: SkillContext) -> SkillResult:
        """执行 TTS

        支持通过配置自定义模型，提供 model_type 和对应的 API 配置即可
        """
        text = params.get("text")
        if not text:
            return SkillResult(success=False, content="缺少 text 参数")

        model_type = params.get("model", self.default_model or "edge_tts")

        try:
            # 根据 model_type 路由到不同的实现
            # 支持自定义模型：只需在 config 中配置对应类型并实现即可
            if model_type == "edge_tts":
                return await self._generate_edge_tts(text, params)
            elif model_type == "minimax":
                return await self._generate_minimax_tts(text, params)
            elif model_type == "azure_tts":
                return await self._generate_azure_tts(text, params)
            elif model_type == "openai_tts":
                return await self._generate_openai_tts(text, params)
            else:
                # 默认尝试通用 HTTP API 调用（可用于 minimax 或其他兼容 API）
                return await self._generate_custom_tts(text, params, model_type)
        except Exception as e:
            logger.error(f"[TTSSkill] 生成失败: {e}")
            return SkillResult(success=False, content=str(e))

    async def _generate_edge_tts(self, text: str, params: dict) -> SkillResult:
        """Edge TTS 生成"""
        try:
            import edge_tts
            output_file = self.output_dir / f"tts_{id(text)}.mp3"

            # 从 params 或 config 获取 voice
            voice = params.get("voice") or self.config.get("edge_tts", {}).get("voice", "zh-CN-XiaoxiaoNeural")
            rate = params.get("rate") or self.config.get("edge_tts", {}).get("rate", "+0%")
            volume = params.get("volume") or self.config.get("edge_tts", {}).get("volume", "+0%")

            # Edge TTS 支持中文语音
            communicate = edge_tts.Communicate(text, voice)
            if rate != "+0%":
                communicate._rate = rate
            if volume != "+0%":
                communicate._volume = volume

            await communicate.save(str(output_file))

            logger.info(f"[TTSSkill] Edge TTS 生成成功: {output_file}")
            return SkillResult(
                success=True,
                content=str(output_file),
                content_type="voice",
                metadata={"model": "edge_tts", "voice": voice}
            )
        except ImportError:
            logger.warning("[TTSSkill] edge-tts 未安装")
            return SkillResult(success=False, content="edge-tts 未安装，请运行: pip install edge-tts")
        except Exception as e:
            logger.error(f"[TTSSkill] Edge TTS 失败: {e}")
            return SkillResult(success=False, content=str(e))

    async def _generate_minimax_tts(self, text: str, params: dict) -> SkillResult:
        """MiniMax TTS 生成 API - POST /v1/t2a_v2"""
        try:
            import aiohttp
            import uuid

            # 优先从 params 获取（调用者传入），其次从环境变量，再次从 adapter
            api_key = params.get("api_key") or os.environ.get("MINIMAX_API_KEY")
            if not api_key:
                model = params.get("model_adapter")
                if model and hasattr(model, 'api_key'):
                    api_key = model.api_key
                    base_url = model.base_url

            if not api_key:
                return SkillResult(success=False, content="MiniMax API Key 未配置")

            # base_url 同样优先从 adapter 获取，其次从环境变量
            if 'base_url' not in dir():
                base_url = os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.chat/v1")
            url = f"{base_url}/t2a_v2"

            # 获取配置
            model_name = self.config.get("minimax_model", "speech-2.8-hd")
            voice_id = self.config.get("minimax_voice", "male-qn-qingse")
            speed = self.config.get("speed", 1)
            vol = self.config.get("vol", 1)
            pitch = self.config.get("pitch", 0)
            sample_rate = self.config.get("sample_rate", 32000)
            bitrate = self.config.get("bitrate", 128000)
            output_format = self.config.get("output_format", "hex")  # url | hex

            payload = {
                "model": model_name,
                "text": text,
                "voice_setting": {
                    "voice_id": voice_id,
                    "speed": speed,
                    "vol": vol,
                    "pitch": pitch,
                },
                "audio_setting": {
                    "sample_rate": sample_rate,
                    "bitrate": bitrate,
                    "format": "mp3",
                    "channel": 1,
                },
                "output_format": output_format,
                "stream": False,
            }

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise RuntimeError(f"MiniMax TTS API error {resp.status}: {error_text}")

                    data = await resp.json()

                    output_file = self.output_dir / f"minimax_tts_{uuid.uuid4().hex[:8]}.mp3"

                    if output_format == "hex":
                        # hex 编码的音频数据
                        audio_hex = data.get("data", {}).get("audio")
                        if audio_hex:
                            import binascii
                            audio_data = binascii.unhexlify(audio_hex)
                            with open(output_file, 'wb') as f:
                                f.write(audio_data)
                        else:
                            return SkillResult(success=False, content="未获取到音频数据")
                    else:
                        # URL 模式
                        audio_url = data.get("data", {}).get("audio_url")
                        if audio_url:
                            async with session.get(audio_url) as audio_resp:
                                if audio_resp.status == 200:
                                    content = await audio_resp.read()
                                    with open(output_file, 'wb') as f:
                                        f.write(content)
                                else:
                                    return SkillResult(success=False, content=f"下载音频失败: {audio_resp.status}")
                        else:
                            return SkillResult(success=False, content="未获取到音频URL")

                    logger.info(f"[TTSSkill] MiniMax TTS 生成成功: {output_file}")
                    return SkillResult(
                        success=True,
                        content=str(output_file),
                        content_type="voice",
                        metadata={
                            "model": "minimax",
                            "voice": voice_id,
                            "model_name": model_name,
                        }
                    )
        except ImportError:
            return SkillResult(success=False, content="需要安装 aiohttp: pip install aiohttp")
        except Exception as e:
            logger.error(f"[TTSSkill] MiniMax TTS 失败: {e}")
            return SkillResult(success=False, content=str(e))

    async def _generate_azure_tts(self, text: str, params: dict) -> SkillResult:
        """Azure TTS 生成（通过通用 HTTP API）"""
        logger.info(f"[TTSSkill] Azure TTS")
        return await self._generate_custom_tts(text, params, "azure_tts")

    async def _generate_openai_tts(self, text: str, params: dict) -> SkillResult:
        """OpenAI TTS 生成（通过通用 HTTP API）"""
        logger.info(f"[TTSSkill] OpenAI TTS")
        return await self._generate_custom_tts(text, params, "openai_tts")

    async def _generate_custom_tts(self, text: str, params: dict, model_type: str) -> SkillResult:
        """通用 HTTP TTS 调用，支持自定义模型配置

        配置示例（config/models.yaml）：
        ```yaml
        skills:
          tts:
            model: "custom"
            custom:
              api_url: "https://api.example.com/tts"
              model: "my-tts-model"
              method: "POST"
              headers:
                Authorization: "Bearer xxx"
              body_template:
                text: "{{text}}"
                voice: "{{voice}}"
              response_type: "url"  # url | hex | base64
              audio_field: "data.audio_url"  # JSON path to audio URL/hex
        ```
        """
        try:
            import aiohttp
            import uuid
            import json

            # 获取模型配置
            model_config = self.config.get(model_type, {})
            api_url = model_config.get("api_url") or params.get("api_url")
            model_name = model_config.get("model") or params.get("model", model_type)
            headers_config = model_config.get("headers", {})
            method = model_config.get("method", "POST")
            response_type = model_config.get("response_type", "hex")
            audio_field = model_config.get("audio_field", "data.audio")

            # 构建请求头
            headers = {
                "Content-Type": "application/json",
            }
            # 获取 API key：优先从 params → 环境变量 → adapter
            api_key = params.get("api_key") or os.environ.get("MINIMAX_API_KEY")
            if not api_key:
                model_adapter = params.get("model_adapter")
                if model_adapter and hasattr(model_adapter, 'api_key'):
                    api_key = model_adapter.api_key
            if api_key:
                auth_type = model_config.get("auth_type", "bearer")
                if auth_type == "bearer":
                    headers["Authorization"] = f"Bearer {api_key}"
                elif auth_type == "api_key":
                    headers["x-api-key"] = api_key

            # 合并自定义 headers
            for k, v in headers_config.items():
                headers[k] = v

            if not api_url:
                return SkillResult(success=False, content=f"{model_type} API URL 未配置")

            # 构建请求体
            body_template = model_config.get("body_template", {})
            body = {}
            for k, v in body_template.items():
                if isinstance(v, str) and "{{text}}" in v:
                    body[k] = v.replace("{{text}}", text)
                elif isinstance(v, str) and "{{voice}}" in v:
                    voice = params.get("voice") or model_config.get("voice", "default")
                    body[k] = v.replace("{{voice}}", voice)
                elif isinstance(v, str) and "{{model}}" in v:
                    body[k] = v.replace("{{model}}", model_name)
                else:
                    body[k] = v

            # 确保 text 字段存在
            if "text" not in body:
                body["text"] = text
            if "model" not in body and "model" in body_template:
                body["model"] = model_name
            elif "model" not in body:
                body["model"] = model_name

            output_file = self.output_dir / f"tts_{uuid.uuid4().hex[:8]}.mp3"

            async with aiohttp.ClientSession() as session:
                if method == "POST":
                    async with session.post(api_url, headers=headers, json=body) as resp:
                        if resp.status != 200:
                            error_text = await resp.text()
                            raise RuntimeError(f"{model_type} TTS API error {resp.status}: {error_text}")
                        data = await resp.json()
                else:
                    async with session.get(api_url, headers=headers) as resp:
                        if resp.status != 200:
                            error_text = await resp.text()
                            raise RuntimeError(f"{model_type} TTS API error {resp.status}: {error_text}")
                        data = await resp.json()

                # 解析音频数据
                audio_data = None
                if response_type == "hex":
                    # 从 JSON path 获取 hex 数据
                    audio_hex = self._get_nested_value(data, audio_field)
                    if audio_hex:
                        import binascii
                        audio_data = binascii.unhexlify(audio_hex)
                elif response_type == "url":
                    audio_url = self._get_nested_value(data, audio_field)
                    if audio_url:
                        async with session.get(audio_url) as audio_resp:
                            if audio_resp.status == 200:
                                audio_data = await audio_resp.read()
                elif response_type == "base64":
                    audio_b64 = self._get_nested_value(data, audio_field)
                    if audio_b64:
                        import base64
                        audio_data = base64.b64decode(audio_b64)
                elif response_type == "binary":
                    audio_data = await resp.read()

                if not audio_data:
                    return SkillResult(success=False, content=f"未获取到音频数据，response_type={response_type}")

                with open(output_file, 'wb') as f:
                    f.write(audio_data)

                logger.info(f"[TTSSkill] {model_type} TTS 生成成功: {output_file}")
                return SkillResult(
                    success=True,
                    content=str(output_file),
                    content_type="voice",
                    metadata={
                        "model": model_type,
                        "model_name": model_name,
                    }
                )

        except ImportError:
            return SkillResult(success=False, content="需要安装 aiohttp: pip install aiohttp")
        except Exception as e:
            logger.error(f"[TTSSkill] {model_type} TTS 失败: {e}")
            return SkillResult(success=False, content=str(e))

    def _get_nested_value(self, data: dict, path: str):
        """从嵌套 dict 中获取值，支持点号路径如 'data.audio_url'"""
        keys = path.split(".")
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value