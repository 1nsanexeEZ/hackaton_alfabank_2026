"""Value sets of the read models, shared by the contract and the records."""

from typing import Literal

ActionRequired = Literal["none", "info", "offer", "sign"]
Audience = Literal["client", "bank"]
QueueSort = Literal["due_at", "amount", "score", "created_at"]
# Kind of a manual review: check — models see a moderate risk, dispute — models or data
# disagree (decision `review_kind`).
ReviewKind = Literal["check", "dispute"]
EntryKind = Literal["status", "stage", "task", "decision"]
