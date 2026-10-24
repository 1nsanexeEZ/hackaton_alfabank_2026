"""Autosave of a draft: what the client changed."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.modules.applications.application.dto.applications import (
    BeneficiaryBasis,
    CollateralDTO,
    ThirdPartyDTO,
)
from src.modules.applications.application.dto.common import UNSET, Unset


@dataclass(frozen=True, slots=True)
class DraftRequestDTO:
    """The loan request of a draft: any part may still be empty."""

    amount: Decimal | None = None
    term_months: int | None = None
    purpose: str | None = None
    purpose_comment: str | None = None


@dataclass(frozen=True, slots=True)
class ConsentsChoiceDTO:
    personal_data: bool
    credit_bureau: bool
    automated_decision: bool = False


@dataclass(frozen=True, slots=True)
class BeneficiaryChoiceDTO:
    acts_for_third_party: bool
    beneficiary: ThirdPartyDTO | None = None
    basis: BeneficiaryBasis | None = None


@dataclass(frozen=True, slots=True)
class DraftChangesDTO:
    """UNSET — not sent. `request` and `product_fields` sent as null change
    nothing; `collateral: null` removes it, `consents: null` withdraws both."""

    version: int
    request: DraftRequestDTO | None | Unset = UNSET
    product_fields: dict[str, Any] | None | Unset = UNSET
    collateral: CollateralDTO | None | Unset = UNSET
    consents: ConsentsChoiceDTO | None | Unset = UNSET
    # null withdraws the answer.
    beneficiary: BeneficiaryChoiceDTO | None | Unset = UNSET
