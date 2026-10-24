from enum import StrEnum


class TicketStatus(StrEnum):
    # Waits in the queue: nobody has taken it yet.
    OPEN = "open"
    # Taken by an employee: the chat goes on between the client and them.
    IN_PROGRESS = "in_progress"
    # The employee answered the question; a new message of the client opens it again.
    RESOLVED = "resolved"
    # Final: nobody writes into it anymore.
    CLOSED = "closed"


class Side(StrEnum):
    """Who wrote a message or changed the status."""

    CLIENT = "client"
    STAFF = "staff"
