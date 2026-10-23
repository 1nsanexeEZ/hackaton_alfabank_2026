"""Feed entries: what a business event turns into, and who receives it."""

from dataclasses import dataclass
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from src.modules.notifications.facade import FeedItemType

RecipientType = Literal["account", "role"]
Audience = Literal["client", "bank"]
Priority = Literal["low", "normal", "high"]

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


def stage_group(application_id: UUID) -> str:
    return f"stage:{application_id}"


def task_group(task_id: UUID) -> str:
    return f"task:{task_id}"


def pre_approved_group(organization_id: UUID) -> str:
    return f"pre-approved:{organization_id}"
