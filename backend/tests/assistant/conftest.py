import itertools
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from src.core.config import Settings
from src.main import create_app
from src.modules.assistant.application.interfaces.language_model import (
    LanguageModel,
    LanguageModelSetup,
    Provider,
)
from src.modules.assistant.infrastructure.adapters.model_gate import GatedLanguageModel
from src.modules.assistant.infrastructure.adapters.rate_limiter import InMemoryRateLimiter
from tests.assistant.chat import Chat, use_fixtures
from tests.helpers import create_schema


@pytest.fixture
def make_chat(settings: Settings) -> Iterator[Callable[..., Chat]]:
    """`make_chat(llm=FakeLlm(), timeout_s=0.05, rate_limit_per_minute=3)`; without a
    model the assistant answers by templates (`ASSISTANT_LLM_PROVIDER=off`)."""
    create_schema(settings.database_url)
    clients: list[TestClient] = []

    def make(
        llm: LanguageModel | None = None,
        *,
        provider: Provider = "local",
        timeout_s: float = 25.0,
        rate_limit_per_minute: int = 1000,
    ) -> Chat:
        app = create_app(settings)
        source = use_fixtures(app)
        app.state.assistant_model = (
            LanguageModelSetup(provider, GatedLanguageModel(llm, 1, 4, timeout_s))
            if llm
            else LanguageModelSetup("off", None, "ASSISTANT_LLM_PROVIDER=off")
        )
        clock = itertools.count()
        app.state.assistant_rate_limiter = InMemoryRateLimiter(
            rate_limit_per_minute, 60.0, lambda: next(clock) / 1000
        )
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return Chat(client, source)

    yield make
    for client in clients:
        client.__exit__(None, None, None)
