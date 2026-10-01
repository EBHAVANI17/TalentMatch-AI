from dataclasses import dataclass, field
from typing import List, Optional, Protocol


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


class LLMError(Exception):
    """A provider call failed. retryable=True means another provider (or a later retry) may succeed."""

    def __init__(self, provider: str, message: str, *, retryable: bool = True, status: Optional[int] = None):
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.retryable = retryable
        self.status = status


@dataclass
class AllProvidersFailed(Exception):
    attempts: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        return "No AI provider could complete the request: " + "; ".join(self.attempts or ["none configured"])


class LLMProvider(Protocol):
    name: str
    model: str

    def complete_json(self, system: str, user: str, *, temperature: float, max_tokens: int) -> LLMResult:
        """Return a completion whose text should be a single JSON object."""
        ...
