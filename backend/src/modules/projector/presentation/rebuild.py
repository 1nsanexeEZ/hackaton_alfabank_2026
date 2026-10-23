"""Entry of the rebuild for scripts/projector_rebuild.py: Kafka bodies are
parsed here, the rebuild itself is RebuildReadModelsUseCase."""

import json
from collections.abc import AsyncIterable, AsyncIterator
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import src.core.messaging.contracts  # noqa: F401  registers every contract
from src.core.facades import FacadeRegistry
from src.core.messaging.contracts.base import IntegrationMessage, get_contract
from src.core.messaging.envelope import Envelope
from src.modules.projector.application.dto.rebuild import RebuildStats
from src.modules.projector.application.use_cases.rebuild import Event
from src.modules.projector.presentation.dependencies import rebuild_use_case, replay_event_use_case


def parse(body: dict[str, Any] | bytes) -> tuple[Envelope, IntegrationMessage] | None:
    try:
        raw = body if isinstance(body, dict) else json.loads(body)
        envelope = Envelope.model_validate(raw)
        return envelope, get_contract(envelope.type).model_validate(envelope.payload)
    except (ValueError, LookupError, PydanticValidationError):
        return None


async def _parsed(messages: AsyncIterable[dict[str, Any] | bytes]) -> AsyncIterator[Event]:
    async for body in messages:
        yield parse(body)


async def rebuild(
    session_factory: async_sessionmaker[AsyncSession],
    facades: FacadeRegistry,
    messages: AsyncIterable[dict[str, Any] | bytes],
    attempts: int = 3,
) -> RebuildStats:
    use_case = rebuild_use_case(session_factory, facades, attempts)
    return await use_case.execute(_parsed(messages))


async def apply_one(
    session_factory: async_sessionmaker[AsyncSession],
    facades: FacadeRegistry,
    envelope: Envelope,
    message: IntegrationMessage,
) -> None:
    await replay_event_use_case(session_factory, facades).execute(envelope, message)
