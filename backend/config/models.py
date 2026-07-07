from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelConfig:
    """Immutable model configuration with computed safe limits."""

    name: str
    provider: str
    context_window: int
    max_input_tokens: int
    max_output_tokens: int
    rpm_limit: int
    tpm_limit: int
    rpd_limit: int
    chars_per_token: float = 3.7
    tpm_safety_buffer: float = 0.20
    rpm_safety_buffer: float = 0.30

    @property
    def safe_tpm(self) -> int:
        return int(self.tpm_limit * (1 - self.tpm_safety_buffer))

    @property
    def safe_rpm(self) -> int:
        return int(self.rpm_limit * (1 - self.rpm_safety_buffer))

    @property
    def max_payload_tokens(self) -> int:
        return self.max_input_tokens + self.max_output_tokens
