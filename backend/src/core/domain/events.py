from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """A fact that happened inside a module.

    `occurred_at` is passed explicitly (from a Clock), so domain code stays
    deterministic and testable. Domain events never leave the module as is:
    they are mapped to integration contracts (src.core.messaging.contracts)
    before going to the outbox.
    """

    occurred_at: datetime
