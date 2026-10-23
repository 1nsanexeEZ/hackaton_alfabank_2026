from typing import Literal

# personal_data — processing of personal data (152-FZ), valid until revoked;
# credit_bureau_personal — the person's own credit history (218-FZ), six months.
ConsentType = Literal["personal_data", "credit_bureau_personal"]

# Edition of the consent text the client is shown; a new text — a new version here.
CONSENT_TEXT_VERSIONS: dict[ConsentType, str] = {
    "personal_data": "pd-2026-10",
    "credit_bureau_personal": "bki-fl-2026-10",
}
# None — valid until revoked. A consent to request a credit history is valid for six
# months (218-FZ, art. 6).
CONSENT_VALIDITY_MONTHS: dict[ConsentType, int | None] = {
    "personal_data": None,
    "credit_bureau_personal": 6,
}
