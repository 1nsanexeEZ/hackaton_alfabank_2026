"""The model that words the answer, behind one interface.

The assistant does not depend on who serves the model: a local open-weights
model (Ollama, llama.cpp, vLLM), the bank's own model behind an API or any
other provider is an adapter in `infrastructure/adapters/language_models.py`,
picked by `ASSISTANT_LLM_PROVIDER`. Without a model the assistant answers by
templates from the same facts.
"""

from dataclasses import dataclass
from typing import Literal, Protocol

from src.modules.assistant.domain.prompt import ChatMessage

Provider = Literal["off", "local", "api"]


class LanguageModelUnavailableError(Exception):
    """Refused connection, an error or a bad answer: the caller falls back to rules."""


class LanguageModelBusyError(Exception):
    """The queue to the model is full: answer by template right away."""


class LanguageModelTimeoutError(Exception):
    """No answer within the deadline, the wait in the queue included."""


class LanguageModel(Protocol):
    # The model's name on its server.
    model: str
    # The host that serves it: shown in the status, never a key.
    host: str
    # True — the model runs inside the bank's perimeter, so the client's own text may
    # reach it; an external API gets the bank's facts only.
    inside_perimeter: bool

    async def complete(self, messages: list[ChatMessage]) -> str:
        """Raises LanguageModelUnavailableError, LanguageModelBusyError,
        LanguageModelTimeoutError."""
        ...

    async def ping(self) -> bool:
        """The server answers and serves the model."""
        ...

    async def warm_up(self) -> None:
        """Load the model into memory ahead of a question, without the answer deadline:
        a cold start may take longer than a question may wait. Errors are swallowed."""
        ...


class ModelReachability(Protocol):
    async def reachable(self, model: LanguageModel) -> bool:
        """The last known answer of `model.ping()`, without waiting the ping's timeout: the
        check runs in the background."""
        ...


@dataclass(frozen=True, slots=True)
class LanguageModelSetup:
    """What `ASSISTANT_LLM_PROVIDER` gave: a model, or None and the reason."""

    provider: Provider
    model: LanguageModel | None
    disabled_reason: str | None = None
