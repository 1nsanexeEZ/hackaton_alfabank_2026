from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from src.core.exceptions.exceptions import NotFoundError
from src.products.facade import (
    EligibilityCheckDTO,
    PaymentDTO,
    PaymentScheduleDTO,
    ProductDTO,
    ProductTermsDTO,
    Purpose,
    RecommendationDTO,
    Repayment,
)
from tests.fakes import builders

_KOPECK = Decimal("0.01")


def _round(value: Decimal) -> Decimal:
    return value.quantize(_KOPECK, rounding=ROUND_HALF_UP)


class FakeProductsFacade:
    def __init__(self) -> None:
        self.products: dict[str, ProductDTO] = {}
        # (code, organization_id) -> result; unknown pairs are eligible.
        self.eligibility: dict[tuple[str, UUID], EligibilityCheckDTO] = {}

    def add_product(self, product: ProductDTO) -> ProductDTO:
        self.products[product.code] = product
        return product

    def set_eligibility(self, check: EligibilityCheckDTO) -> None:
        self.eligibility[(check.product_code, check.organization_id)] = check

    async def get_product(self, code: str) -> ProductDTO:
        try:
            return self.products[code]
        except KeyError:
            raise NotFoundError("Product not found") from None

    async def list_active(self) -> list[ProductDTO]:
        return [p for p in self.products.values() if p.status == "active"]

    async def get_terms_snapshot(self, code: str) -> ProductTermsDTO:
        return builders.product_terms(await self.get_product(code))

    async def check_eligibility(self, code: str, organization_id: UUID) -> EligibilityCheckDTO:
        await self.get_product(code)
        return self.eligibility.get(
            (code, organization_id),
            EligibilityCheckDTO(code, organization_id, eligible=True, reasons=()),
        )

    async def recommend(
        self,
        purpose: Purpose,
        amount: Decimal,
        term_months: int,
        organization_id: UUID | None = None,
    ) -> list[RecommendationDTO]:
        matching = [
            p
            for p in await self.list_active()
            if purpose in p.purposes and p.amount_min <= amount <= p.amount_max
        ]
        return [
            RecommendationDTO(
                product=p,
                rank=rank,
                eligible=None if organization_id is None else True,
                reasons=(),
                estimated_monthly_payment=self.calculate_payment(
                    amount, term_months, p.rate_base, "annuity"
                ).monthly_payment,
            )
            for rank, p in enumerate(matching, start=1)
        ]

    def calculate_payment(
        self, amount: Decimal, term_months: int, rate: Decimal, repayment: Repayment
    ) -> PaymentScheduleDTO:
        monthly_rate = rate / Decimal(1200)
        balance = amount
        payments: list[PaymentDTO] = []
        if repayment == "annuity":
            if monthly_rate == 0:
                annuity = amount / term_months
            else:
                annuity = amount * monthly_rate / (1 - (1 + monthly_rate) ** -term_months)
            annuity = _round(annuity)
        for number in range(1, term_months + 1):
            interest = _round(balance * monthly_rate)
            if number == term_months:
                principal = balance
            elif repayment == "annuity":
                principal = annuity - interest
            elif repayment == "interest_only":
                principal = Decimal("0.00")
            else:
                principal = _round(amount / term_months)
            balance = balance - principal
            payments.append(
                PaymentDTO(number, None, principal, interest, principal + interest, balance)
            )
        total_interest = sum((p.interest for p in payments), Decimal("0"))
        return PaymentScheduleDTO(
            amount=amount,
            term_months=term_months,
            rate=rate,
            repayment=repayment,
            monthly_payment=payments[0].total,
            total_interest=total_interest,
            total_paid=amount + total_interest,
            payments=tuple(payments),
        )
