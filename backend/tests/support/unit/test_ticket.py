"""The ticket aggregate: statuses, who may take, write and close."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from src.core.exceptions.exceptions import (
    ConflictError,
    InvalidStatusTransitionError,
    PermissionDeniedError,
    ValidationError,
)
from src.modules.support.domain.enums import Side, TicketStatus
from src.modules.support.domain.events import MessagePosted, TicketOpened, TicketStatusChanged
from src.modules.support.domain.ticket import SupportTicket
from src.modules.support.domain.value_objects import (
    TEXT_MAX_LENGTH,
    Staff,
    TicketNumber,
)
from tests.fakes.builders import NOW

S = TicketStatus
LATER = NOW + timedelta(minutes=5)

CLIENT = uuid4()
ANNA = Staff(uuid4())
BORIS = Staff(uuid4())
ADMIN = Staff(uuid4(), supervisor=True)


def opened(**overrides: object) -> SupportTicket:
    values: dict[str, object] = {
        "id": uuid4(),
        "number": TicketNumber.issue(2026, 1),
        "author_id": CLIENT,
        "subject": "Не вижу выписку",
        "text": "Загрузил выписку, а в заявке её нет",
        "message_id": uuid4(),
        "now": NOW,
    }
    values.update(overrides)
    ticket = SupportTicket.open(**values)  # type: ignore[arg-type]
    ticket.pull_events()
    return ticket


def taken(staff: Staff = ANNA) -> SupportTicket:
    ticket = opened()
    ticket.take(staff, NOW)
    ticket.pull_events()
    return ticket


def code(error: pytest.ExceptionInfo[Exception]) -> str | None:
    details = getattr(error.value, "details", None) or {}
    return details.get("code")


# --- opening ---------------------------------------------------------------------


def test_opened_ticket_waits_in_the_queue_with_the_first_message() -> None:
    organization, application = uuid4(), uuid4()
    ticket = SupportTicket.open(
        id=uuid4(),
        number=TicketNumber.issue(2026, 7),
        author_id=CLIENT,
        subject="  Вопрос по ставке ",
        text=" Почему ставка выше, чем в калькуляторе? ",
        message_id=uuid4(),
        now=NOW,
        organization_id=organization,
        application_id=application,
    )

    assert ticket.status is S.OPEN
    assert str(ticket.number) == "ТП-2026-000007"
    assert ticket.subject == "Вопрос по ставке"
    assert ticket.assignee_id is None
    [message] = ticket.messages
    assert (message.author_id, message.side, message.text) == (
        CLIENT,
        Side.CLIENT,
        "Почему ставка выше, чем в калькуляторе?",
    )
    [event] = ticket.pull_events()
    assert isinstance(event, TicketOpened)
    assert (event.client_id, event.organization_id, event.application_id) == (
        CLIENT,
        organization,
        application,
    )


@pytest.mark.parametrize("field", ["subject", "text"])
@pytest.mark.parametrize("value", ["", "   \n "])
def test_blank_subject_or_text_is_rejected(field: str, value: str) -> None:
    with pytest.raises(ValidationError) as error:
        opened(**{field: value})
    assert error.value.details == {"field": field}


def test_too_long_message_is_rejected() -> None:
    ticket = opened()

    with pytest.raises(ValidationError):
        ticket.post_client_message(CLIENT, uuid4(), "я" * (TEXT_MAX_LENGTH + 1), NOW)
    assert len(ticket.messages) == 1


def test_number_format() -> None:
    assert str(TicketNumber.issue(2026, 123)) == "ТП-2026-000123"
    with pytest.raises(ValueError):
        TicketNumber("КР-2026-000123")
    with pytest.raises(ValueError):
        TicketNumber.issue(2026, 1_000_000)


# --- taking ----------------------------------------------------------------------


def test_take_makes_the_ticket_the_employees() -> None:
    ticket = opened()

    ticket.take(ANNA, LATER)

    assert ticket.status is S.IN_PROGRESS
    assert (ticket.assignee_id, ticket.taken_at, ticket.updated_at) == (
        ANNA.account_id,
        LATER,
        LATER,
    )
    [event] = ticket.pull_events()
    assert isinstance(event, TicketStatusChanged)
    assert (event.from_status, event.to_status, event.side, event.actor_id) == (
        "open",
        "in_progress",
        "staff",
        ANNA.account_id,
    )
    assert event.assignee_id == ANNA.account_id


@pytest.mark.parametrize("second", [ANNA, BORIS, ADMIN], ids=["same", "another", "admin"])
def test_a_taken_ticket_cannot_be_taken_again(second: Staff) -> None:
    ticket = taken(ANNA)

    with pytest.raises(ConflictError) as error:
        ticket.take(second, LATER)

    assert code(error) == "already_taken"
    assert ticket.assignee_id == ANNA.account_id
    assert ticket.pull_events() == []


def test_a_ticket_closed_before_anyone_took_it_cannot_be_taken() -> None:
    ticket = opened()
    ticket.close_by_client(CLIENT, NOW)

    with pytest.raises(InvalidStatusTransitionError):
        ticket.take(ANNA, LATER)


def test_released_ticket_is_back_in_the_queue_for_anyone() -> None:
    ticket = taken(ANNA)

    ticket.release(ANNA, LATER)

    assert ticket.status is S.OPEN
    assert (ticket.assignee_id, ticket.taken_at) == (None, None)
    ticket.take(BORIS, LATER)
    assert ticket.assignee_id == BORIS.account_id


def test_only_the_handler_or_the_admin_releases() -> None:
    ticket = taken(ANNA)

    with pytest.raises(PermissionDeniedError):
        ticket.release(BORIS, LATER)
    ticket.release(ADMIN, LATER)
    assert ticket.status is S.OPEN


# --- the chat --------------------------------------------------------------------


def test_the_handler_answers_the_client() -> None:
    ticket = taken(ANNA)

    message = ticket.post_staff_message(ANNA, uuid4(), "Выписка на месте, обновите страницу", LATER)

    assert message.side is Side.STAFF
    assert ticket.status is S.IN_PROGRESS
    assert ticket.last_message == message
    [event] = ticket.pull_events()
    assert isinstance(event, MessagePosted)
    assert (event.side, event.author_id, event.client_id, event.text) == (
        "staff",
        ANNA.account_id,
        CLIENT,
        "Выписка на месте, обновите страницу",
    )


def test_nobody_answers_before_the_ticket_is_taken() -> None:
    ticket = opened()

    with pytest.raises(ConflictError) as error:
        ticket.post_staff_message(ANNA, uuid4(), "Отвечу сразу", NOW)

    assert code(error) == "not_taken"


def test_another_employee_does_not_write_into_a_taken_ticket() -> None:
    ticket = taken(ANNA)

    with pytest.raises(PermissionDeniedError) as error:
        ticket.post_staff_message(BORIS, uuid4(), "Я тоже отвечу", LATER)

    assert code(error) == "not_assignee"
    assert len(ticket.messages) == 1


def test_the_admin_writes_into_a_ticket_taken_by_someone_else() -> None:
    ticket = taken(ANNA)

    ticket.post_staff_message(ADMIN, uuid4(), "Подключился руководитель", LATER)

    assert ticket.assignee_id == ANNA.account_id
    assert ticket.messages[-1].author_id == ADMIN.account_id


def test_a_stranger_does_not_write_as_the_client() -> None:
    ticket = opened()

    with pytest.raises(PermissionDeniedError) as error:
        ticket.post_client_message(uuid4(), uuid4(), "Чужое обращение", NOW)

    assert code(error) == "not_author"


def test_the_client_writes_into_an_open_ticket_and_it_stays_in_the_queue() -> None:
    ticket = opened()

    ticket.post_client_message(CLIENT, uuid4(), "Забыл: заявка КР-2026-000001", LATER)

    assert ticket.status is S.OPEN
    assert len(ticket.messages) == 2


def test_a_message_into_a_resolved_ticket_takes_it_back_to_the_handler() -> None:
    ticket = taken(ANNA)
    ticket.resolve(ANNA, NOW)
    ticket.pull_events()

    ticket.post_client_message(CLIENT, uuid4(), "Не помогло", LATER)

    assert ticket.status is S.IN_PROGRESS
    assert (ticket.assignee_id, ticket.resolved_at) == (ANNA.account_id, None)
    posted, reopened = ticket.pull_events()
    assert isinstance(posted, MessagePosted)
    assert isinstance(reopened, TicketStatusChanged)
    assert (reopened.from_status, reopened.to_status, reopened.side) == (
        "resolved",
        "in_progress",
        "client",
    )


# --- resolving and closing ---------------------------------------------------------


def test_resolve_then_close() -> None:
    ticket = taken(ANNA)

    ticket.resolve(ANNA, NOW)
    assert (ticket.status, ticket.resolved_at) == (S.RESOLVED, NOW)
    ticket.close_by_staff(ANNA, LATER)
    assert (ticket.status, ticket.closed_at) == (S.CLOSED, LATER)


def test_another_employee_does_not_resolve_or_close() -> None:
    ticket = taken(ANNA)

    with pytest.raises(PermissionDeniedError):
        ticket.resolve(BORIS, LATER)
    with pytest.raises(PermissionDeniedError):
        ticket.close_by_staff(BORIS, LATER)
    ticket.close_by_staff(ADMIN, LATER)
    assert ticket.status is S.CLOSED


def test_staff_closes_only_a_taken_ticket() -> None:
    ticket = opened()

    with pytest.raises(ConflictError) as error:
        ticket.close_by_staff(ADMIN, NOW)

    assert code(error) == "not_taken"


def test_a_resolved_ticket_is_not_returned_to_the_queue() -> None:
    ticket = taken(ANNA)
    ticket.resolve(ANNA, NOW)

    with pytest.raises(InvalidStatusTransitionError):
        ticket.release(ANNA, LATER)


def test_the_client_closes_own_ticket_in_any_open_status() -> None:
    for ticket in (opened(), taken()):
        ticket.close_by_client(CLIENT, LATER)
        assert (ticket.status, ticket.closed_at) == (S.CLOSED, LATER)


def test_a_stranger_does_not_close_the_ticket() -> None:
    with pytest.raises(PermissionDeniedError):
        opened().close_by_client(uuid4(), NOW)


def test_nobody_writes_into_a_closed_ticket() -> None:
    ticket = taken(ANNA)
    ticket.close_by_client(CLIENT, NOW)

    with pytest.raises(ConflictError) as client_error:
        ticket.post_client_message(CLIENT, uuid4(), "Ещё вопрос", LATER)
    with pytest.raises(ConflictError) as staff_error:
        ticket.post_staff_message(ANNA, uuid4(), "Ответ", LATER)

    assert code(client_error) == code(staff_error) == "ticket_closed"
    assert len(ticket.messages) == 1


def test_a_closed_ticket_is_final() -> None:
    ticket = taken(ANNA)
    ticket.close_by_staff(ANNA, NOW)

    with pytest.raises(InvalidStatusTransitionError):
        ticket.close_by_client(CLIENT, LATER)
    with pytest.raises(InvalidStatusTransitionError):
        ticket.resolve(ANNA, LATER)
    with pytest.raises(ConflictError):
        ticket.take(BORIS, LATER)


def _ids(ticket: SupportTicket) -> list[UUID]:
    return [m.id for m in ticket.messages]


def test_messages_keep_their_order() -> None:
    ticket = taken(ANNA)
    first, second = uuid4(), uuid4()

    ticket.post_staff_message(ANNA, first, "Уточните ИНН", NOW)
    ticket.post_client_message(CLIENT, second, "7701158817", LATER)

    assert _ids(ticket)[1:] == [first, second]
    assert ticket.last_message is not None and ticket.last_message.side is Side.CLIENT
