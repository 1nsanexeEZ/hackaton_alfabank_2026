"""Who reads which feed: an account reads its own records, bank staff also the
records of the back office role."""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from src.core.access.permissions import Permissions
from src.modules.notifications.domain.feed import UNDERWRITERS, Recipient

# Holders of these permissions are bank staff: they read the back office feed
# (`role:underwriter`) and may look at any company.
BANK_PERMISSIONS = frozenset({Permissions.BACKOFFICE_READ.value, Permissions.ADMIN.value})
# Identity roles of bank staff, for the facade that knows only the account id.
BANK_ROLE_NAMES = frozenset({"underwriter", "admin"})


def is_bank_staff(permissions: Sequence[str]) -> bool:
    return not BANK_PERMISSIONS.isdisjoint(permissions)


def viewer_recipients(account_id: UUID, bank_staff: bool) -> tuple[Recipient, ...]:
    own = Recipient.account(account_id)
    return (own, UNDERWRITERS) if bank_staff else (own,)


@dataclass(frozen=True, slots=True)
class StreamGrant:
    """What a redeemed stream ticket opens: the account and the feeds it reads."""

    account_id: UUID
    recipients: tuple[Recipient, ...]
