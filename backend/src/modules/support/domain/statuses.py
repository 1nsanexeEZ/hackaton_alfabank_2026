"""The only allowed transitions of a ticket status."""

from src.core.exceptions.exceptions import InvalidStatusTransitionError
from src.modules.support.domain.enums import TicketStatus

S = TicketStatus

TRANSITIONS: dict[TicketStatus, frozenset[TicketStatus]] = {
    # Taken by an employee or closed by the client before anyone took it.
    S.OPEN: frozenset({S.IN_PROGRESS, S.CLOSED}),
    # OPEN: the employee returns it to the queue.
    S.IN_PROGRESS: frozenset({S.OPEN, S.RESOLVED, S.CLOSED}),
    # IN_PROGRESS: the client wrote again, the question is not answered after all.
    S.RESOLVED: frozenset({S.IN_PROGRESS, S.CLOSED}),
    S.CLOSED: frozenset(),
}


def ensure_transition(source: TicketStatus, target: TicketStatus) -> None:
    if target not in TRANSITIONS[source]:
        raise InvalidStatusTransitionError(
            f"Ticket cannot go from {source.value} to {target.value}",
            details={"from": source.value, "to": target.value},
        )
