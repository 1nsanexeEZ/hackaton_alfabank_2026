from typing import Any
from uuid import UUID, uuid4

import pytest

from src.core.domain.clock import FrozenClock
from src.core.messaging.contracts.process import StepCompleted
from src.core.messaging.outbox import build_envelope


class RecordingDeadLetters:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    async def publish_dead_letter(self, topic: str, body: dict[str, Any], error: str) -> None:
        self.items.append({"topic": topic, "body": body, "error": error})


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock()


@pytest.fixture
def dead_letters() -> RecordingDeadLetters:
    return RecordingDeadLetters()


def step_envelope(
    application_id: UUID | None = None, event_id: UUID | None = None
) -> dict[str, Any]:
    application_id = application_id or uuid4()
    message = StepCompleted(
        process_id=uuid4(),
        application_id=application_id,
        node_id="fetch",
        step_code="fetch_enrichment",
        client_stage="Проверяем данные о компании",
    )
    envelope = build_envelope(
        message,
        producer="process",
        occurred_at=FrozenClock().now(),
        correlation_id=application_id,
        event_id=event_id,
    )
    return envelope.model_dump(mode="json")
