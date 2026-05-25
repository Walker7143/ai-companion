"""
Model Factory - 模型适配器工厂

根据 provider 和配置创建对应的模型适配器实例
"""

import logging
from typing import Optional, Type

import aiohttp

from .adapters import (
    ModelAdapter,
    MiniMaxAdapter,
    OpenAIAdapter,
    ClaudeAdapter,
    MimoAdapter,
    DeepSeekAdapter,
    TeleAdapter,
    OllamaAdapter,
    CustomAdapter,
)

logger = logging.getLogger(__name__)


def _coerce_timeout(value) -> aiohttp.ClientTimeout:
    """Accept config-friendly timeout values while adapters keep aiohttp types."""
    if isinstance(value, aiohttp.ClientTimeout):
        return value
    if isinstance(value, dict):
        allowed = {"total", "connect", "sock_connect", "sock_read"}
        kwargs = {k: float(v) for k, v in value.items() if k in allowed and v is not None}
        return aiohttp.ClientTimeout(**kwargs)
    return aiohttp.ClientTimeout(total=float(value))


class ModelFactory:
    """模型适配器工厂"""

    _ADAPTERS: dict[str, Type[ModelAdapter]] = {
        "minimax": MiniMaxAdapter,
        "openai": OpenAIAdapter,
        "claude": ClaudeAdapter,
        "mimo": MimoAdapter,
        "deepseek": DeepSeekAdapter,
        "tele": TeleAdapter,
        "ollama": OllamaAdapter,
        "custom": CustomAdapter,
    }

    _RUNTIME_ALLOWED_KWARGS: dict[str, set[str]] = {
        "minimax": {"api_key", "base_url", "model", "timeout"},
        "openai": {"api_key", "base_url", "model", "timeout"},
        "claude": {"api_key", "base_url", "model", "timeout"},
        "mimo": {"api_key", "base_url", "model", "timeout", "auth_type"},
        "deepseek": {"api_key", "base_url", "model", "timeout"},
        "tele": {"api_key", "base_url", "model", "auth_state_file", "timeout"},
        "ollama": {"base_url", "model", "timeout"},
        "custom": {
            "api_url",
            "model",
            "auth_type",
            "api_key",
            "headers",
            "request_template",
            "response_field",
            "timeout",
        },
    }

    @classmethod
    def create(cls, provider: str, **kwargs) -> ModelAdapter:
        """
        根据 provider 创建适配器实例

        Args:
            provider: 提供商名称 (minimax / openai / claude / mimo / ollama / custom)
            **kwargs: 传递给适配器的参数

        Returns:
            ModelAdapter 实例
        """
        provider = provider.lower()
        adapter_cls = cls._ADAPTERS.get(provider)

        if not adapter_cls:
            available = ", ".join(cls._ADAPTERS.keys())
            raise ValueError(
                f"未知 provider: '{provider}'. 可用: {available}"
            )

        try:
            return adapter_cls(**kwargs)
        except TypeError as e:
            raise ValueError(
                f"创建 {provider} 适配器失败，参数错误: {e}"
            ) from e

    @classmethod
    def create_from_config(
        cls,
        config: dict,
        provider: str = None,
        global_config: dict = None,
    ) -> ModelAdapter:
        """
        根据配置文件创建适配器

        Args:
            config: 模型配置字典 (从 models.yaml 加载)
            provider: 指定 provider，None 则使用 config.model.provider
            global_config: 全局配置 (temperature, max_tokens 等)

        Returns:
            ModelAdapter 实例
        """
        provider = provider or config.get("provider", "minimax")
        provider_config = config.get(provider, {})

        if not provider_config:
            raise ValueError(
                f"配置中找不到 provider '{provider}' 的配置"
            )

        # 提取通用参数
        common_params = {
            "api_key": provider_config.get("api_key", ""),
            "base_url": provider_config.get("base_url", ""),
            "model": provider_config.get("model", ""),
        }

        # 移除空值
        common_params = {k: v for k, v in common_params.items() if v}

        # 添加 provider 特定参数
        params = dict(common_params)
        metadata_keys = {"max_context_chars", "max_context_tokens"}
        for key, value in provider_config.items():
            if key not in ("api_key", "base_url", "model") and key not in metadata_keys and value is not None:
                params[key] = value
        if "timeout" in params:
            params["timeout"] = _coerce_timeout(params["timeout"])

        logger.info(f"[ModelFactory] 创建 {provider} 适配器，模型: {params.get('model', 'unknown')}")

        return cls.create(provider, **params)

    @classmethod
    def create_from_runtime_config(
        cls,
        model_config: dict,
        provider: str = None,
        api_key: str = None,
    ) -> ModelAdapter:
        """
        根据运行时扁平配置创建适配器。

        model_config 示例：
            {"provider":"minimax","api_key":"...","base_url":"...","model":"..."}
        """
        if not isinstance(model_config, dict):
            raise ValueError("model_config 必须是 dict")

        provider = (provider or model_config.get("provider", "minimax")).lower()
        raw = dict(model_config)
        raw.pop("provider", None)
        if api_key:
            raw["api_key"] = api_key

        # custom 适配器使用 api_url 字段
        if provider == "custom" and not raw.get("api_url") and raw.get("base_url"):
            raw["api_url"] = raw["base_url"]

        allowed = cls._RUNTIME_ALLOWED_KWARGS.get(provider, set(raw.keys()))
        kwargs = {k: v for k, v in raw.items() if k in allowed and v not in (None, "")}
        if "timeout" in kwargs:
            kwargs["timeout"] = _coerce_timeout(kwargs["timeout"])
        logger.info(f"[ModelFactory] 运行时创建 {provider} 适配器，参数: {sorted(kwargs.keys())}")
        return cls.create(provider, **kwargs)

    @classmethod
    def register(cls, name: str, adapter_cls: Type[ModelAdapter]):
        """
        注册自定义适配器

        Args:
            name: 适配器名称
            adapter_cls: 适配器类
        """
        if not issubclass(adapter_cls, ModelAdapter):
            raise ValueError(f"{adapter_cls} 必须继承 ModelAdapter")
        cls._ADAPTERS[name.lower()] = adapter_cls
        logger.info(f"[ModelFactory] 注册自定义适配器: {name}")

    @classmethod
    def list_providers(cls) -> list[str]:
        """列出所有可用的 provider"""
        return list(cls._ADAPTERS.keys())
