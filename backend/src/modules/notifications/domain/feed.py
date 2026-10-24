"""Feed entries: what a business event turns into, and who receives it."""

from dataclasses import dataclass
from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from src.modules.notifications.domain.enums import Audience, FeedItemType, Priority, RecipientType

# Role of the back office feed (`role:underwriter`).
UNDERWRITER_ROLE = "underwriter"


@dataclass(frozen=True, slots=True)
class Recipient:
    """An account (a member of the company) or a whole bank role."""

    type: RecipientType
    id: str

    @classmethod
    def account(cls, account_id: UUID) -> "Recipient":
        return cls("account", str(account_id))

    @classmethod
    def role(cls, role: str) -> "Recipient":
        return cls("role", role)


UNDERWRITERS = Recipient.role(UNDERWRITER_ROLE)


@dataclass(frozen=True, slots=True)
class FeedEntry:
    """One feed record before it is addressed. Title and body are already
    rendered and HTML-escaped (see templates)."""

    type: FeedItemType
    audience: Audience
    title: str
    body: str
    link: str | None = None
    priority: Priority = "normal"
    action_required: bool = False
    organization_id: UUID | None = None
    application_id: UUID | None = None
    # Entries with the same key replace each other for a recipient instead of
    # piling up: the current stage of an application, a task, pre-approved offers.
    group_key: str | None = None
    # Tells apart several entries made from one event (advice items).
    discriminator: str | None = None

    def source_id(self, event_id: UUID) -> UUID:
        """Idempotency key of the entry: the event id, or a stable derivative of
        it when one event produces several entries for the same recipient."""
        if self.discriminator is None:
            return event_id
        return uuid5(NAMESPACE_URL, f"{event_id}/{self.discriminator}")


@dataclass(frozen=True, slots=True)
class Delivery:
    entry: FeedEntry
    recipients: tuple[Recipient, ...]
    # True: replace the recipient's entry with the same group_key.
    replace_group: bool = False
    # True (with replace_group): a correction of an earlier entry. Nothing is written
    # for a recipient who has no entry of the group, or whose entry already says this.
    only_existing: bool = False


@dataclass(frozen=True, slots=True)
class FeedRecord:
    """A stored entry of one recipient."""

    id: UUID
    # Stream position: the SSE event id.
    seq: int
    recipient: Recipient
    audience: Audience
    type: FeedItemType
    title: str
    body: str
    link: str | None
    priority: Priority
    action_required: bool
    organization_id: UUID | None
    application_id: UUID | None
    created_at: datetime
    read_at: datetime | None


def stage_group(application_id: UUID) -> str:
    return f"stage:{application_id}"


def task_group(task_id: UUID) -> str:
    return f"task:{task_id}"


def pre_approved_group(organization_id: UUID) -> str:
    return f"pre-approved:{organization_id}"


def support_queue_group(ticket_id: UUID) -> str:
    """The back office entry of a ticket waiting in the queue."""
    return f"support-queue:{ticket_id}"


def support_client_group(ticket_id: UUID) -> str:
    """The client's entry of a ticket: the latest answer or status."""
    return f"support:{ticket_id}"


def support_assignee_group(ticket_id: UUID) -> str:
    """The entry of the employee who took the ticket: the latest client message."""
    return f"support-assignee:{ticket_id}"
