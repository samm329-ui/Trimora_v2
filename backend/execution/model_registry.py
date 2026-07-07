from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from backend.config.models import ModelConfig

if TYPE_CHECKING:
    from backend.services.llm_provider import LLMProvider

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Immutable model-to-provider mapping.

    Frozen after startup to prevent accidental runtime mutations.
    """

    def __init__(self):
        self._models: dict[str, ModelConfig] = {}
        self._providers: dict[str, LLMProvider] = {}
        self._model_to_provider: dict[str, str] = {}
        self._frozen = False

    def register_model(self, config: ModelConfig, provider_name: str) -> None:
        """Register a model with its provider. Must be called before freeze()."""
        if self._frozen:
            raise RuntimeError("Cannot register models after freeze()")
        self._models[config.name] = config
        self._model_to_provider[config.name] = provider_name

    def register_provider(self, name: str, provider: LLMProvider) -> None:
        """Register a provider instance. Must be called before freeze()."""
        if self._frozen:
            raise RuntimeError("Cannot register providers after freeze()")
        self._providers[name] = provider

    def freeze(self) -> None:
        """Freeze the registry. No more mutations allowed."""
        self._frozen = True
        logger.info(
            "ModelRegistry frozen: %d models, %d providers",
            len(self._models),
            len(self._providers),
        )

    def get_config(self, model_name: str) -> ModelConfig:
        """Get model configuration."""
        if model_name not in self._models:
            raise ValueError(f"Unknown model: {model_name}")
        return self._models[model_name]

    def get_provider(self, model_name: str) -> LLMProvider:
        """Get provider for model."""
        provider_name = self._model_to_provider.get(model_name)
        if not provider_name:
            raise ValueError(f"No provider for model: {model_name}")
        provider = self._providers.get(provider_name)
        if provider is None:
            raise ValueError(f"Provider not found: {provider_name}")
        return provider

    def list_models(self) -> list[str]:
        """List available models."""
        return list(self._models.keys())

    @property
    def is_frozen(self) -> bool:
        return self._frozen
