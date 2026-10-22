"""Use cases of products: catalog, terms snapshot, eligibility, matching, calculator."""

from decimal import Decimal

from src.core.domain import Money
from src.core.exceptions.exceptions import NotFoundError, ValidationError
from src.modules.products.application.ports import ProductRepository
from src.modules.products.domain.calculator import PaymentCalculator, PaymentSchedule
from src.modules.products.domain.product import CreditProduct, ProductStatus
from src.modules.products.domain.recommender import ProductRecommender, Recommendation
from src.modules.products.domain.value_objects import (
    BorrowerProfile,
    EligibilityCheck,
    LoanNeed,
    ProductTerms,
)


class ProductService:
    def __init__(
        self,
        products: ProductRepository,
        calculator: PaymentCalculator | None = None,
        recommender: ProductRecommender | None = None,
    ) -> None:
        self._products = products
        self._calculator = calculator or PaymentCalculator()
        self._recommender = recommender or ProductRecommender(self._calculator)

    async def get(self, code: str) -> CreditProduct:
        """Active or archived; a draft is not published yet."""
        product = await self._products.get_current(code)
        if product is None or product.status == ProductStatus.DRAFT:
            raise NotFoundError("Product not found", details={"code": code})
        return product

    async def get_selectable(self, code: str) -> CreditProduct:
        product = await self.get(code)
        product.ensure_selectable()
        return product

    async def list_active(self, purpose: str | None = None) -> list[CreditProduct]:
        products = await self._products.list_active()
        return [p for p in products if purpose is None or p.serves(purpose)]

    async def terms_snapshot(self, code: str) -> ProductTerms:
        return (await self.get(code)).snapshot()

    async def check_eligibility(self, code: str, borrower: BorrowerProfile) -> EligibilityCheck:
        return (await self.get_selectable(code)).check_eligibility(borrower)

    async def recommend(
        self, need: LoanNeed, borrower: BorrowerProfile | None = None
    ) -> list[Recommendation]:
        return self._recommender.recommend(await self.list_active(), need, borrower)

    async def calculate(
        self,
        code: str,
        amount: Money,
        term_months: int,
        rate: Decimal | None = None,
        repayment: str | None = None,
    ) -> PaymentSchedule:
        """Schedule within the product frames: the base rate and the default
        schedule unless asked otherwise."""
        product = await self.get_selectable(code)
        rates = product.client_rate
        rate = rates.base if rate is None else rate
        repayment = repayment or product.default_repayment
        if not product.amount.contains(amount):
            raise _out_of_range("amount", product.amount.min.amount, product.amount.max.amount)
        if not product.term.contains(term_months):
            raise _out_of_range("term_months", product.term.min_months, product.term.max_months)
        if not rates.contains(rate):
            raise _out_of_range("rate", rates.base, rates.max)
        if repayment not in product.repayment_options:
            raise ValidationError(
                "The product does not offer this schedule",
                details={
                    "field": "repayment",
                    "code": "not_offered",
                    "options": list(product.repayment_options),
                },
            )
        return self._calculator.schedule(amount, term_months, rate, repayment)

    def calculate_payment(
        self, amount: Money, term_months: int, rate: Decimal, repayment: str
    ) -> PaymentSchedule:
        return self._calculator.schedule(amount, term_months, rate, repayment)


def _out_of_range(field: str, low: Decimal | int, high: Decimal | int) -> ValidationError:
    return ValidationError(
        "Value is out of the product frames",
        details={"field": field, "code": "out_of_range", "min": str(low), "max": str(high)},
    )
