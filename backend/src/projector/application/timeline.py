"""Which events become timeline entries and what the client may see in them.

Entries are built from the event alone (never from the current state of a
module), so a rebuild restores the history exactly. Client entries carry only
what the client may see: no reason codes, no score, no internal comments.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from src.core.messaging.contracts.applications import (
    ApplicationInfoProvided,
    ApplicationStatusChanged,
)
from src.core.messaging.contracts.base import IntegrationMessage
from src.core.messaging.contracts.decision import DecisionMade, ManualDecisionRejected
from src.core.messaging.contracts.process import (
    ProcessCompleted,
    ProcessFailed,
    ProcessStarted,
    StepCompleted,
    UserTaskCompleted,
    UserTaskCreated,
)
from src.projector.domain.timeline import (
    BANK,
    CLIENT,
    TimelineEntry,
    decision_title,
    status_title,
)

_CLIENT_DECISION_FIELDS = {
    "outcome",
    "decided_by",
    "offer",
    "requested_info",
    "client_explanation",
    "improvement_hints",
    "alternative_product_code",
}


def timeline_entry(
    source_event_id: UUID, at: datetime, message: IntegrationMessage
) -> TimelineEntry | None:
    """None — the event is not worth an entry (its status change already is one)."""
    application_id = getattr(message, "application_id", None)
    if not isinstance(application_id, UUID):
        return None

    def entry(
        kind: str, title: str, audience: str, details: dict[str, Any] | None = None
    ) -> TimelineEntry:
        return TimelineEntry.of_event(
            source_event_id, application_id, at, kind, title, audience, details
        )

    match message:
        case ApplicationStatusChanged():
            return entry(
                "status",
                status_title(message.to_status),
                CLIENT,
                {
                    "from_status": message.from_status,
                    "to_status": message.to_status,
                    "client_stage": message.client_stage,
                },
            )
        case ApplicationInfoProvided():
            return entry(
                "status",
                "Клиент ответил на запрос сведений",
                BANK,
                message.model_dump(mode="json", include={"info_request_id", "document_ids"}),
            )
        case ProcessStarted():
            return entry(
                "stage",
                f"Запущен маршрут {message.workflow_code}",
                BANK,
                message.model_dump(mode="json", include={"process_id", "workflow_code"}),
            )
        case StepCompleted() if message.client_stage:
            return entry("stage", message.client_stage, CLIENT, {"step_code": message.step_code})
        case StepCompleted():
            return entry(
                "stage",
                f"Выполнен шаг «{message.step_code}»",
                BANK,
                message.model_dump(mode="json", include={"process_id", "node_id", "step_code"}),
            )
        case ProcessCompleted():
            return entry(
                "stage",
                "Маршрут завершён",
                BANK,
                message.model_dump(mode="json", include={"process_id", "outcome"}),
            )
        case ProcessFailed():
            return entry(
                "stage",
                "Маршрут остановлен из-за ошибки",
                BANK,
                message.model_dump(mode="json", include={"process_id", "reason"}),
            )
        case UserTaskCreated():
            return entry(
                "task",
                f"Создана задача «{message.task_type}» для роли {message.candidate_role}",
                BANK,
                message.model_dump(
                    mode="json", include={"task_id", "task_type", "candidate_role", "due_at"}
                ),
            )
        case UserTaskCompleted():
            return entry(
                "task",
                "Задача выполнена",
                BANK,
                message.model_dump(mode="json", include={"task_id", "completed_by", "result"}),
            )
        case DecisionMade():
            return entry(
                "decision",
                decision_title(message.outcome),
                CLIENT,
                message.model_dump(mode="json", include=_CLIENT_DECISION_FIELDS),
            )
        case ManualDecisionRejected():
            return entry(
                "decision",
                "Решение андеррайтера не принято",
                BANK,
                message.model_dump(mode="json", include={"task_id", "reason"}),
            )
    return None
