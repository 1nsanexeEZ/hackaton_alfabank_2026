"""What the underwriter's project assessment form of a startup starts with.

The bank has assessed the project before the application (decision, by the business plan and
the financial model), so the form comes filled in: the underwriter confirms the project or
changes what they disagree with.
- A valid passed assessment and the amount within the pre-approval — approve as asked;
  above it — a counter offer down to the pre-approved amount.
- Failed or expired — reject; the underwriter may still approve against it.
- The plan is acceptable when the assessment passed and weak otherwise: whether it is strong is
  for the underwriter to say.
- Collateral and the state support program — from the financial model.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

_GUARANTORS = {
    "msp_corporation": "гарантия Корпорации МСП",
    "regional_fund": "гарантия региональной гарантийной организации",
}


@dataclass(frozen=True, slots=True)
class ProjectForm:
    decision: Literal["approve", "counter_offer", "reject"]
    amount: Decimal | None
    term_months: int | None
    business_plan: Literal["strong", "acceptable", "weak"]
    collateral: str | None
    support_program: bool


def project_form(
    *,
    passed: bool,
    pre_approved: Decimal | None,
    requested: Decimal | None,
    term_months: int | None,
    collateral_description: str | None,
    guarantee: str,
    guarantee_share: Decimal,
) -> ProjectForm:
    if passed and pre_approved is not None:
        within = requested is not None and requested <= pre_approved
        decision: Literal["approve", "counter_offer", "reject"] = (
            "approve" if within else "counter_offer"
        )
        amount = requested if within else pre_approved
    else:
        decision, amount = "reject", None
    parts = [collateral_description] if collateral_description else []
    guarantor = _GUARANTORS.get(guarantee)
    if guarantor is not None:
        parts.append(f"{guarantor} на {(guarantee_share * 100).normalize():f}% суммы")
    return ProjectForm(
        decision=decision,
        amount=amount,
        term_months=term_months,
        business_plan="acceptable" if passed else "weak",
        collateral="; ".join(parts) or None,
        support_program=guarantor is not None,
    )
