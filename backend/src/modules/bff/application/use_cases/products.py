"""Product matching and the calculator with the pre-approval."""

from decimal import Decimal
from uuid import UUID

from src.core.access.access_context import AccessContext
from src.core.exceptions.exceptions import ValidationError
from src.modules.bff.application.dto.products import (
    CalculationDTO,
    PersonalScheduleDTO,
    PreApprovedTermsDTO,
    ReasonDTO,
    RecommendationItemDTO,
    RecommendationsDTO,
    SuggestionDTO,
)
from src.modules.bff.application.interfaces.neighbours import Neighbours
from src.modules.bff.application.use_cases.common import ensure_visible, segment_of
from src.modules.clients.facade import ClientsFacade
from src.modules.decision.facade import DecisionFacade, PreApprovedOfferDTO
from src.modules.products.facade import ProductDTO, ProductsFacade, Purpose, Repayment


class RecommendProductsUseCase:
    def __init__(self, neighbours: Neighbours) -> None:
        self._n = neighbours

    async def execute(
        self,
        access: AccessContext,
        organization_id: UUID | None,
        purpose: Purpose,
        amount: Decimal,
        term_months: int,
    ) -> RecommendationsDTO:
        """With organization_id: eligibility of the company and pre-approved amounts."""
        pre_approved: dict[str, Decimal] = {}
        startup: bool | None = None
        if organization_id is not None:
            await ensure_visible(self._n, access, organization_id)
            snapshot = await self._n(ClientsFacade).get_snapshot(organization_id)
            startup = segment_of(snapshot) == "startup"

            async def load() -> dict[str, Decimal]:
                offers = await self._n(DecisionFacade).get_pre_approved(organization_id)
                return {o.product_code: o.max_amount for o in offers}

            pre_approved = await self._n.optional("pre_approved", load, {})
        found = sorted(
            await self._n(ProductsFacade).recommend(purpose, amount, term_months, organization_id),
            key=lambda r: r.rank,
        )
        # A startup sees only the startup products, a business with turnover — all but them.
        if startup is not None:
            found = [r for r in found if r.product.startup_only == startup]
        best = next((r.product.code for r in found if r.eligible is not False), None)
        items = tuple(
            RecommendationItemDTO(
                product_code=r.product.code,
                product_name=r.product.name,
                short_description=r.product.short_description,
                rank=r.rank,
                fit="unavailable"
                if r.eligible is False
                else ("best" if r.product.code == best else "suitable"),
                eligible=r.eligible,
                eligibility=tuple(ReasonDTO.of(x) for x in r.reasons),
                rate_from=r.product.rate_base,
                amount_max=r.product.amount_max,
                term_max_months=r.product.term_max_months,
                payment_from=r.estimated_monthly_payment,
                pre_approved_max=pre_approved.get(r.product.code),
            )
            for r in found
        )
        return RecommendationsDTO(items=items, degraded=self._n.degraded)


class PersonalScheduleUseCase:
    """The rate is the bank's: the pre-approved one, the base one without it.
    A request above the pre-approved terms is not an error: the decision
    comes after the check, the bank may answer with a counteroffer."""

    def __init__(self, neighbours: Neighbours) -> None:
        self._n = neighbours

    async def execute(
        self, access: AccessContext, organization_id: UUID, code: str, request: CalculationDTO
    ) -> PersonalScheduleDTO:
        amount, term_months = request.amount, request.term_months
        await ensure_visible(self._n, access, organization_id)
        products = self._n(ProductsFacade)
        product = await products.get_product(code)
        check = await products.check_eligibility(code, organization_id)
        repayment = request.repayment or product.repayment_options[0]
        _ensure_within_product(product, amount, term_months, repayment)

        async def load() -> PreApprovedOfferDTO | None:
            offers = await self._n(DecisionFacade).get_pre_approved(organization_id)
            return next((o for o in offers if o.product_code == code), None)

        offer = await self._n.optional("pre_approved", load, None)
        rate = offer.rate_from if offer is not None else product.rate_base
        schedule = products.calculate_payment(amount, term_months, rate, repayment)
        reasons = [ReasonDTO.of(r) for r in check.reasons]
        pre_approved: PreApprovedTermsDTO | None = None
        within: bool | None = None
        suggestion: SuggestionDTO | None = None
        if offer is not None:
            pre_approved = _terms(offer)
            above = _above_pre_approved(offer, amount, term_months)
            within = not above
            reasons += above
            if above:
                suggestion = _suggestion(products, product, offer, amount, term_months, repayment)
        return PersonalScheduleDTO(
            schedule=schedule,
            pre_approved=pre_approved,
            within_pre_approved=within,
            eligible=check.eligible,
            reasons=tuple(reasons),
            suggestion=suggestion,
            degraded=self._n.degraded,
        )


def _ensure_within_product(
    product: ProductDTO, amount: Decimal, term_months: int, repayment: Repayment
) -> None:
    """The same 422 as `POST /products/{code}/calculate` gives."""
    if not product.amount_min <= amount <= product.amount_max:
        raise _out_of_range("amount", product.amount_min, product.amount_max)
    if not product.term_min_months <= term_months <= product.term_max_months:
        raise _out_of_range("term_months", product.term_min_months, product.term_max_months)
    if repayment not in product.repayment_options:
        raise ValidationError(
            "The product does not offer this schedule",
            details={
                "field": "repayment",
                "code": "not_offered",
                "options": list(product.repayment_options),
            },
        )


def _out_of_range(field: str, low: Decimal | int, high: Decimal | int) -> ValidationError:
    return ValidationError(
        "Value is out of the product frames",
        details={"field": field, "code": "out_of_range", "min": str(low), "max": str(high)},
    )


def _terms(offer: PreApprovedOfferDTO) -> PreApprovedTermsDTO:
    return PreApprovedTermsDTO(
        max_amount=offer.max_amount,
        rate_from=offer.rate_from,
        term_max_months=offer.term_max_months,
        valid_until=offer.valid_until,
        # Only the kind of the estimate leaves the bank, not what it is based on.
        basis="full" if offer.basis == "full" else "estimate",
    )


def _above_pre_approved(
    offer: PreApprovedOfferDTO, amount: Decimal, term_months: int
) -> list[ReasonDTO]:
    reasons = []
    if amount > offer.max_amount:
        reasons.append(
            ReasonDTO(
                code="amount_above_pre_approved",
                passed=False,
                message=f"Предварительно доступно до {_rub(offer.max_amount)}",
            )
        )
    if term_months > offer.term_max_months:
        reasons.append(
            ReasonDTO(
                code="term_above_pre_approved",
                passed=False,
                message=f"Предварительно доступен срок до {offer.term_max_months} мес.",
            )
        )
    return reasons


def _suggestion(
    products: ProductsFacade,
    product: ProductDTO,
    offer: PreApprovedOfferDTO,
    amount: Decimal,
    term_months: int,
    repayment: Repayment,
) -> SuggestionDTO | None:
    """The request cut to the pre-approved amount and term; none when the cut
    falls below the product minimum."""
    amount = min(amount, offer.max_amount)
    term_months = min(term_months, offer.term_max_months)
    if amount < product.amount_min or term_months < product.term_min_months:
        return None
    schedule = products.calculate_payment(amount, term_months, offer.rate_from, repayment)
    return SuggestionDTO(
        amount=amount, term_months=term_months, monthly_payment=schedule.monthly_payment
    )


def _rub(value: Decimal) -> str:
    """`Decimal("5000000")` -> `5 000 000 ₽`."""
    whole, _, kopecks = f"{value:,.2f}".replace(",", " ").partition(".")
    return f"{whole},{kopecks} ₽" if kopecks != "00" else f"{whole} ₽"
