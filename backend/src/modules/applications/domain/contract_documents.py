"""The contract as a document: the draft the client signs and the copy the bank seals.

Both are PDF files in an archive that keeps them unchanged. What happens to
them goes into a signing log where each entry carries the hash of the previous
one, so an entry cannot be changed or dropped without breaking the chain.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

_ZERO_HASH = "0" * 64


class ContractDocumentKind(StrEnum):
    DRAFT = "draft"  # what the client reads and signs
    SIGNED = "signed"  # the same contract with both signatures, sealed by the bank


@dataclass(frozen=True, slots=True)
class BankSeal:
    """The bank's signature embedded in the PDF (PAdES) and its certificate."""

    signer: str
    certificate_serial: str
    certificate_issuer: str
    valid_from: datetime
    valid_to: datetime
    signed_at: datetime
    timestamp_at: datetime | None


@dataclass(frozen=True, slots=True)
class ContractDocument:
    id: UUID
    application_id: UUID
    kind: ContractDocumentKind
    # The offer the document was made for: a new offer needs a new draft.
    offer_hash: str
    sha256: str
    size: int
    storage_key: str
    created_at: datetime
    seal: BankSeal | None = None


def deal_uid(deal_id: UUID) -> str:
    """Unique identifier of the deal for the credit history (218-FZ): the UUID
    and a check symbol, appendix 2 to Bank of Russia regulation 758-P.

    Without hyphens the 32 hex digits get weights 1..10 cyclically from the
    left, the weighted sum is divided by 16 and the remainder in hex is the
    check symbol.
    """
    digits = str(deal_id).replace("-", "")
    total = sum(int(digit, 16) * (index % 10 + 1) for index, digit in enumerate(digits))
    return f"{deal_id}-{total % 16:x}"


class SigningEventKind(StrEnum):
    DRAFT_ISSUED = "draft_issued"
    CLIENT_SIGNED = "client_signed"
    BANK_SEALED = "bank_sealed"


@dataclass(frozen=True, slots=True)
class SigningEvent:
    application_id: UUID
    seq: int
    at: datetime
    kind: SigningEventKind
    actor: str
    details: dict[str, Any] = field(default_factory=dict)
    prev_hash: str = _ZERO_HASH
    hash: str = _ZERO_HASH

    @classmethod
    def after(
        cls,
        previous: "SigningEvent | None",
        application_id: UUID,
        at: datetime,
        kind: SigningEventKind,
        actor: str,
        details: dict[str, Any],
    ) -> "SigningEvent":
        seq = previous.seq + 1 if previous else 1
        prev_hash = previous.hash if previous else _ZERO_HASH
        event = cls(application_id, seq, at, kind, actor, details, prev_hash)
        return cls(application_id, seq, at, kind, actor, details, prev_hash, event.digest())

    def digest(self) -> str:
        canonical = json.dumps(
            {
                "application_id": str(self.application_id),
                "seq": self.seq,
                "at": _utc(self.at).isoformat(),
                "kind": self.kind.value,
                "actor": self.actor,
                "details": self.details,
                "prev_hash": self.prev_hash,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()


def _utc(moment: datetime) -> datetime:
    """The same instant whether the database kept the time zone or not (SQLite does not)."""
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def chain_is_intact(events: list[SigningEvent]) -> bool:
    """Each entry is the one its hash says and points at the one before it."""
    previous_hash = _ZERO_HASH
    for seq, event in enumerate(events, start=1):
        if event.seq != seq or event.prev_hash != previous_hash or event.hash != event.digest():
            return False
        previous_hash = event.hash
    return True
