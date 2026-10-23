"""What the screens call statuses and kinds."""

from typing import Literal

# Application status in the frontend's terms
# (`frontend/src/entities/application/model/status.ts`).
ClientStatus = Literal[
    "draft",
    "submitted",
    "checking",
    "scoring",
    "info_requested",
    "approved",
    "counter_offer",
    "rejected",
    "signing",
    "issued",
    "cancelled",
    "declined",
    "expired",
]

TodoKind = Literal["info_requested", "offer_ready", "signing", "consent_required"]

# startup — younger than 6 months or no annual report: the founder's prescreen and the
# startup product instead of pre-approval.
Segment = Literal["established", "startup"]

# estimate — a conservative estimate without the credit bureau; full — after a check.
PreApprovalBasis = Literal["estimate", "full"]

# Consents kept in identity, as it names them.
ConsentKind = Literal["personal_data", "credit_bureau_company", "credit_bureau_personal"]
# account — the person gives it for themselves; organization — a representative, for the
# company.
ConsentScope = Literal["account", "organization"]
