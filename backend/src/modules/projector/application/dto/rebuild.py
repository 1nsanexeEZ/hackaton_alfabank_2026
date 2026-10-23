"""Result of the rebuild."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RebuildStats:
    applied: int = 0
    # Not an envelope or an unknown message type: the live consumer sends them to the DLQ.
    skipped: int = 0
    failed: int = 0
