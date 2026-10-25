"""SupportTicket — a client's question to the bank and the chat on it.

The only owner of the ticket status: every change goes through a method here.
- The client who opened the ticket writes into it while it is not closed and
  may close it. A message into a resolved ticket takes it back to work.
- An employee takes an open ticket; from then on it is theirs and nobody can
  take it again. Only they answer, resolve, close it or return it to the queue.
  A supervisor (the admin) may do that in a ticket taken by someone else, but
  takes an open ticket like anyone, so a ticket always has one handler.
"""

from datetime import datetime
from typing import Any, Self
from uuid import UUID

from src.core.exceptions.exceptions import ConflictError, PermissionDeniedError
from src.modules.support.domain.entities import TicketMessage
from src.modules.support.domain.enums import Side, TicketStatus
from src.modules.support.domain.events import (
    MessagePosted,
    TicketEvent,
    TicketOpened,
    TicketStatusChanged,
)
from src.modules.support.domain.statuses import ensure_transition
from src.modules.support.domain.value_objects import (
    SUBJECT_MAX_LENGTH,
    TEXT_MAX_LENGTH,
    Staff,
    TicketNumber,
    clean_text,
)

S = TicketStatus


class SupportTicket:
    def __init__(
        self,
        *,
        id: UUID,
        number: TicketNumber,
        author_id: UUID,
        subject: str,
        status: TicketStatus,
        created_at: datetime,
        updated_at: datetime,
        organization_id: UUID | None = None,
        application_id: UUID | None = None,
        assignee_id: UUID | None = None,
        taken_at: datetime | None = None,
        resolved_at: datetime | None = None,
        closed_at: datetime | None = None,
        messages: list[TicketMessage] | None = None,
        version: int = 1,
    ) -> None:
        self.id = id
        self.number = number
        self.author_id = author_id
        self.subject = subject
        self.status = status
        self.organization_id = organization_id
        self.application_id = application_id
        self.assignee_id = assignee_id
        self.taken_at = taken_at
        self.resolved_at = resolved_at
        self.closed_at = closed_at
        self.messages: list[TicketMessage] = list(messages or [])
        self.version = version
        self.created_at = created_at
        self.updated_at = updated_at
        self._events: list[TicketEvent] = []

    @classmethod
    def open(
        cls,
        *,
        id: UUID,
        number: TicketNumber,
        author_id: UUID,
        subject: str,
        text: str,
        message_id: UUID,
        now: datetime,
        organization_id: UUID | None = None,
        application_id: UUID | None = None,
    ) -> Self:
        """A new ticket in the queue with the client's first message."""
        ticket = cls(
            id=id,
            number=number,
            author_id=author_id,
            subject=clean_text(subject, "subject", SUBJECT_MAX_LENGTH),
            status=S.OPEN,
            created_at=now,
            updated_at=now,
            organization_id=organization_id,
            application_id=application_id,
        )
        ticket.messages.append(
            TicketMessage(
                id=message_id,
                author_id=author_id,
                side=Side.CLIENT,
                text=clean_text(text, "text", TEXT_MAX_LENGTH),
                created_at=now,
            )
        )
        ticket._events.append(ticket._event(TicketOpened, now))
        return ticket

    # --- reading -----------------------------------------------------------------

    @property
    def last_message(self) -> TicketMessage | None:
        return self.messages[-1] if self.messages else None

    def pull_events(self) -> list[TicketEvent]:
        events, self._events = self._events, []
        return events

    # --- the client ----------------------------------------------------------------

    def post_client_message(
        self, author_id: UUID, message_id: UUID, text: str, now: datetime
    ) -> TicketMessage:
        self._ensure_author(author_id)
        self._ensure_not_closed()
        message = self._append(message_id, author_id, Side.CLIENT, text, now)
        if self.status is S.RESOLVED:
            # The answer did not help: the same employee gets the ticket back.
            self.resolved_at = None
            self._move(S.IN_PROGRESS, Side.CLIENT, author_id, now)
        return message

    def close_by_client(self, author_id: UUID, now: datetime) -> None:
        self._ensure_author(author_id)
        self._close(Side.CLIENT, author_id, now)

    # --- an employee ----------------------------------------------------------------

    def take(self, staff: Staff, now: datetime) -> None:
        """The ticket becomes the employee's. Taken already — 409 for anyone,
        the one who holds it included."""
        if self.assignee_id is not None:
            raise ConflictError(
                "The ticket is already taken",
                details={"code": "already_taken", "assignee_id": str(self.assignee_id)},
            )
        ensure_transition(self.status, S.IN_PROGRESS)
        self.assignee_id = staff.account_id
        self.taken_at = now
        self._move(S.IN_PROGRESS, Side.STAFF, staff.account_id, now)

    def release(self, staff: Staff, now: datetime) -> None:
        """Back to the queue: anyone may take it again."""
        self._ensure_handler(staff)
        ensure_transition(self.status, S.OPEN)
        self.assignee_id = None
        self.taken_at = None
        self._move(S.OPEN, Side.STAFF, staff.account_id, now)

    def post_staff_message(
        self, staff: Staff, message_id: UUID, text: str, now: datetime
    ) -> TicketMessage:
        self._ensure_not_closed()
        self._ensure_handler(staff)
        return self._append(message_id, staff.account_id, Side.STAFF, text, now)

    def resolve(self, staff: Staff, now: datetime) -> None:
        self._ensure_handler(staff)
        ensure_transition(self.status, S.RESOLVED)
        self.resolved_at = now
        self._move(S.RESOLVED, Side.STAFF, staff.account_id, now)

    def close_by_staff(self, staff: Staff, now: datetime) -> None:
        self._ensure_handler(staff)
        self._close(Side.STAFF, staff.account_id, now)

    # --- rules ---------------------------------------------------------------------

    def _ensure_author(self, account_id: UUID) -> None:
        if account_id != self.author_id:
            raise PermissionDeniedError(
                "Only the client who opened the ticket can do this",
                details={"code": "not_author"},
            )

    def _ensure_not_closed(self) -> None:
        if self.status is S.CLOSED:
            raise ConflictError("The ticket is closed", details={"code": "ticket_closed"})

    def _ensure_handler(self, staff: Staff) -> None:
        if self.assignee_id is None:
            raise ConflictError("Take the ticket first", details={"code": "not_taken"})
        if self.assignee_id != staff.account_id and not staff.supervisor:
            raise PermissionDeniedError(
                "The ticket is taken by another employee",
                details={"code": "not_assignee", "assignee_id": str(self.assignee_id)},
            )

    def _close(self, side: Side, actor_id: UUID, now: datetime) -> None:
        ensure_transition(self.status, S.CLOSED)
        self.closed_at = now
        self._move(S.CLOSED, side, actor_id, now)

    def _append(
        self, message_id: UUID, author_id: UUID, side: Side, text: str, now: datetime
    ) -> TicketMessage:
        message = TicketMessage(
            id=message_id,
            author_id=author_id,
            side=side,
            text=clean_text(text, "text", TEXT_MAX_LENGTH),
            created_at=now,
        )
        self.messages.append(message)
        self.updated_at = now
        self._events.append(
            self._event(
                MessagePosted,
                now,
                message_id=message.id,
                side=side.value,
                author_id=author_id,
                text=message.text,
            )
        )
        return message

    def _move(self, target: TicketStatus, side: Side, actor_id: UUID, now: datetime) -> None:
        source, self.status = self.status, target
        self.updated_at = now
        self._events.append(
            self._event(
                TicketStatusChanged,
                now,
                from_status=source.value,
                to_status=target.value,
                side=side.value,
                actor_id=actor_id,
            )
        )

    def _event[E: TicketEvent](self, kind: type[E], now: datetime, **fields: Any) -> E:
        return kind(
            occurred_at=now,
            ticket_id=self.id,
            number=str(self.number),
            subject=self.subject,
            client_id=self.author_id,
            assignee_id=self.assignee_id,
            organization_id=self.organization_id,
            application_id=self.application_id,
            **fields,
        )
