"""Wiring of the assistant module into the application.

The model is picked once, by `ASSISTANT_LLM_PROVIDER` (docs/ai.md); tests put
a fake one into `app.state.assistant_model` after create_app(). A local model
is loaded into memory on startup, so the first question does not wait for it.
"""

import asyncio
import time

from fastapi import FastAPI

from src.core.config import Settings
from src.core.messaging.subscriber import Subscription
from src.modules.assistant.application.interfaces.language_model import LanguageModelSetup
from src.modules.assistant.infrastructure.adapters.language_models import build_language_model
from src.modules.assistant.infrastructure.adapters.model_gate import warm_up_when_served
from src.modules.assistant.infrastructure.adapters.rate_limiter import InMemoryRateLimiter
from src.modules.assistant.infrastructure.config import AssistantSettings
from src.modules.assistant.infrastructure.exception_handler import register_exception_handlers
from src.modules.assistant.presentation.api import router

NAME = "assistant"
RATE_WINDOW_S = 60.0
# How often to look whether the local model is served yet (Ollama starting, model not pulled).
WARM_UP_RETRY_S = 30.0


def register(app: FastAPI) -> None:
    app.include_router(router)
    register_exception_handlers(app)


def wire(app: FastAPI) -> None:
    """The assistant has no facade: nobody reads it."""
    config = AssistantSettings()
    app.state.assistant_model = build_language_model(config)
    app.state.assistant_rate_limiter = InMemoryRateLimiter(
        config.rate_limit_per_minute, RATE_WINDOW_S, time.monotonic
    )


async def startup(app: FastAPI) -> None:
    settings: Settings = app.state.settings
    setup: LanguageModelSetup = app.state.assistant_model
    model = setup.model
    # An external API needs no loading; tests run no background work.
    if model is None or not model.inside_perimeter or not settings.run_background_jobs:
        return
    stop = asyncio.Event()
    app.state.assistant_warm_up = (
        stop,
        asyncio.create_task(
            warm_up_when_served(model, stop, WARM_UP_RETRY_S), name="assistant-warm-up-on-start"
        ),
    )


async def shutdown(app: FastAPI) -> None:
    warm_up = getattr(app.state, "assistant_warm_up", None)
    if warm_up is not None:
        stop, task = warm_up
        stop.set()
        task.cancel()
    close = getattr(app.state.assistant_model.model, "aclose", None)
    if close is not None:
        await close()


def subscribers() -> list[Subscription]:
    """The assistant listens to nothing: it reads the neighbours when asked."""
    return []
