from dataclasses import dataclass
from decimal import Decimal

from src.modules.projector.facade import AmountBucketDTO, LatestApplicationDTO


@dataclass(frozen=True, slots=True)
class CountDTO:
    key: str
    count: int
    amount: Decimal


@dataclass(frozen=True, slots=True)
class ProductCountDTO:
    product_code: str
    product_name: str
    count: int
    amount: Decimal


@dataclass(frozen=True, slots=True)
class ApplicationsOverviewDTO:
    total: int  # every application, drafts too
    submitted: int
    requested_amount: Decimal  # of the submitted ones
    approved: int  # reached an approval (see `funnel`)
    decided: int  # reached a decision of the bank
    funnel: tuple[CountDTO, ...]  # started, submitted, decided, approved, signed, disbursed
    statuses: tuple[CountDTO, ...]  # every status with applications, by the status
    products: tuple[ProductCountDTO, ...]  # every application, most applications first
    amount_buckets: tuple[AmountBucketDTO, ...]
    latest: tuple[LatestApplicationDTO, ...]
