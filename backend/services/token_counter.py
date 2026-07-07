from __future__ import annotations

import logging

from backend.config.models import ModelConfig

logger = logging.getLogger(__name__)

try:
    import tiktoken

    _HAVE_TIKTOKEN = True
except ImportError:
    _HAVE_TIKTOKEN = False


class TokenCounter:
    """Token counting with tiktoken fallback to heuristic estimation."""

    def __init__(self, model_config: ModelConfig):
        self.config = model_config
        self._tokenizer = None
        if _HAVE_TIKTOKEN:
            try:
                self._tokenizer = tiktoken.get_encoding("cl100k_base")
            except Exception:
                logger.debug("tiktoken unavailable, using heuristic fallback")

    def count(self, text: str) -> int:
        """Count tokens. Uses tiktoken if available, else heuristic."""
        if not text:
            return 0
        if self._tokenizer is not None:
            try:
                return len(self._tokenizer.encode(text))
            except Exception:
                pass
        return max(1, len(text) // int(self.config.chars_per_token))

    def estimate_output(self, prompt_tokens: int, task_type: str) -> int:
        """Estimate output tokens based on task type."""
        estimates = {
            "validation": 50,
            "classification": 100,
            "annotation": 800,
            "reasoning": 600,
            "summary": 500,
        }
        return estimates.get(task_type, 200)
