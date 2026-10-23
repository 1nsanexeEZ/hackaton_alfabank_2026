from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Self
from uuid import UUID

from src.modules.identity.domain.entities import Consent
from src.modules.identity.domain.enums import ConsentType


@dataclass(frozen=True, slots=True)
class ConsentRecordDTO:
    """A consent as its owner sees it: in force or not at `now`."""

    type: ConsentType
    given_at: datetime
    valid_until: datetime | None
    revoked_at: datetime | None
    active: bool
    text_version: str
    # Who gave it; for a company consent — the representative.
    given_by: UUID
    # Set for a company consent only.
    organization_id: UUID | None = None
    revoked_by: UUID | None = None

    @classmethod
    def from_entity(cls, consent: Consent, now: datetime) -> Self:
        return cls(
            type=consent.type,
            given_at=consent.given_at,
            valid_until=consent.valid_until,
            revoked_at=consent.revoked_at,
            active=consent.is_active(now),
            text_version=consent.text_version,
            given_by=consent.account_id,
            organization_id=consent.organization_id,
            revoked_by=consent.revoked_by,
        )


@dataclass(frozen=True, slots=True)
class GiveConsentsDTO:
    types: Sequence[ConsentType]
    # Kept with every consent: where it was given from.
    ip: str | None
    user_agent: str | None
