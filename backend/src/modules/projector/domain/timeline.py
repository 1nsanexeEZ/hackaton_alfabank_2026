"""Timeline of an application: one entry per event, for the client or for the bank.

The entry id is derived from the event id, so a replay (or a rebuild) writes
exactly the same entry and never a second one.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid5

CLIENT = "client"
BANK = "bank"

_ENTRY_NAMESPACE = UUID("6f1d4c52-7a43-4f43-9d8e-2b1a0f6c3e11")

STATUS_TITLES: dict[str, str] = {
    "draft": "Черновик заявки",
    "submitted": "Заявка отправлена в банк",
    "in_review": "Заявка на рассмотрении",
    "info_requested": "Банк запросил дополнительные сведения",
    "offer_ready": "Готово предложение банка",
    "signing": "Предложение принято, идёт подписание",
    "signed": "Договор подписан",
    "disbursed": "Кредит выдан",
    "rejected": "Банк отказал в кредите",
    "offer_declined": "Предложение банка отклонено",
    "expired": "Срок предложения истёк",
    "cancelled": "Заявка отозвана",
}

DECISION_TITLES: dict[str, str] = {
    "APPROVE": "Кредит одобрен",
    "COUNTER_OFFER": "Банк предложил другие условия",
    "REQUEST_INFO": "Для решения нужны дополнительные сведения",
    "MANUAL_REVIEW": "Заявку рассматривает специалист банка",
    "REJECT": "Банк отказал в кредите",
}


def status_title(status: str) -> str:
    return STATUS_TITLES.get(status, f"Статус заявки: {status}")


def decision_title(outcome: str) -> str:
    return DECISION_TITLES.get(outcome, f"Решение по заявке: {outcome}")


def entry_id(source_event_id: UUID) -> UUID:
    return uuid5(_ENTRY_NAMESPACE, str(source_event_id))


@dataclass(frozen=True, slots=True)
class TimelineEntry:
    id: UUID
    application_id: UUID
    source_event_id: UUID
    at: datetime
    kind: str
    title: str
    audience: str
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def of_event(
        cls,
        source_event_id: UUID,
        application_id: UUID,
        at: datetime,
        kind: str,
        title: str,
        audience: str,
        details: dict[str, Any] | None = None,
    ) -> "TimelineEntry":
        return cls(
            id=entry_id(source_event_id),
            application_id=application_id,
            source_event_id=source_event_id,
            at=at,
            kind=kind,
            title=title,
            audience=audience,
            details=details or {},
        )

    def visible_to(self, audience: str) -> bool:
        """The client sees client entries only, the bank sees everything."""
        return audience == BANK or self.audience == CLIENT
