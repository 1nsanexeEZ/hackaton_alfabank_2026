"""Seed of products: the credit catalog.

Nine products, codes of seed/demo_data.PRODUCT_CODES; the first four match
the demo catalog of the frontend, STARTUP is for a company without turnover.
Rates and limits are synthetic. Upsert by code and version: running the seed
again leaves the same catalog.
"""

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from src.core.domain import Money
from src.modules.products.domain.product import CreditProduct, ProductStatus
from src.modules.products.domain.value_objects import (
    AmountRange,
    DocumentRequirement,
    Eligibility,
    ProcessingProfile,
    ProductCode,
    RateRange,
    SecurityRequirement,
    SupportProgram,
    TermRange,
)
from src.modules.products.infrastructure.repository import SqlAlchemyProductRepository

if TYPE_CHECKING:
    from seed.run import SeedContext

MLN = 1_000_000
ALL_FORMS = frozenset({"LLC", "IE", "JSC"})
COMPANIES = frozenset({"LLC", "JSC"})

# Priority industries of the state support program (two-digit OKVED classes):
# agriculture, manufacturing, hotels and catering, IT, research, healthcare.
PRIORITY_OKVED = frozenset(
    {"01", "02", "03", *(str(code) for code in range(10, 34)), "55", "56", "62", "63", "72", "86"}
)


def _rub(amount: int | str) -> Money:
    return Money(Decimal(amount))


def _financials(from_amount: int | None = None) -> tuple[DocumentRequirement, ...]:
    """Companies keep accounting statements, an individual entrepreneur — a tax return."""
    threshold = None if from_amount is None else _rub(from_amount)
    return (
        DocumentRequirement(
            "financial_report",
            "Бухгалтерская отчётность за последний год",
            required_from=threshold,
            legal_forms=COMPANIES,
        ),
        DocumentRequirement(
            "tax_return",
            "Налоговая декларация за последний год",
            required_from=threshold,
            legal_forms=frozenset({"IE"}),
        ),
    )


COLLATERAL_DOCUMENTS = DocumentRequirement(
    "collateral_documents", "Документы на залог: право собственности и оценка"
)
PURCHASE_CONTRACT = DocumentRequirement(
    "purchase_contract", "Договор купли-продажи или счёт продавца"
)
BANK_STATEMENT = DocumentRequirement(
    "bank_statement", "Выписка по расчётному счёту за 6 месяцев (CSV)"
)
EXISTING_LOANS = DocumentRequirement(
    "existing_loans_statement", "Справка о действующих кредитах: остаток долга и график"
)
BUSINESS_PLAN = DocumentRequirement(
    "business_plan", "Бизнес-план: продукт, рынок, команда, план продаж"
)
FINANCIAL_MODEL = DocumentRequirement(
    "financial_model", "Финансовая модель на срок кредита: выручка, расходы, денежный поток"
)

AUTO_FIELDS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "vehicle_type": {
            "type": "string",
            "title": "Тип транспорта",
            "enum": ["car", "truck", "special"],
        },
        "vehicle_description": {
            "type": "string",
            "title": "Марка, модель, год выпуска",
            "minLength": 2,
            "maxLength": 500,
        },
        "supplier_name": {"type": "string", "title": "Продавец", "maxLength": 200},
        "price": {"type": "number", "title": "Стоимость, ₽", "minimum": 1},
    },
    "required": ["vehicle_type", "vehicle_description", "price"],
}
MORTGAGE_FIELDS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "property_address": {
            "type": "string",
            "title": "Адрес объекта",
            "minLength": 5,
            "maxLength": 500,
        },
        "property_type": {
            "type": "string",
            "title": "Тип недвижимости",
            "enum": ["office", "warehouse", "retail", "production"],
        },
        "price": {"type": "number", "title": "Стоимость, ₽", "minimum": 1},
    },
    "required": ["property_address", "property_type", "price"],
}
REFINANCE_FIELDS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "loans": {
            "type": "array",
            "title": "Кредиты, которые нужно погасить",
            "minItems": 1,
            "maxItems": 10,
            "items": {
                "type": "object",
                "properties": {
                    "creditor": {"type": "string", "title": "Банк", "maxLength": 200},
                    "outstanding": {"type": "number", "title": "Остаток долга, ₽", "minimum": 1},
                    "monthly_payment": {
                        "type": "number",
                        "title": "Платёж в месяц, ₽",
                        "minimum": 0,
                    },
                    "rate": {
                        "type": "number",
                        "title": "Ставка, %",
                        "minimum": 0,
                        "maximum": 100,
                    },
                },
                "required": ["creditor", "outstanding", "monthly_payment", "rate"],
            },
        }
    },
    "required": ["loans"],
}


def catalog() -> tuple[CreditProduct, ...]:
    """In the order of PRODUCT_CODES (the catalog order)."""
    return (
        CreditProduct(
            code=ProductCode("UNSECURED"),
            version=1,
            status=ProductStatus.ACTIVE,
            sort_order=1,
            frontend_id="unsecured",
            name="Кредит без залога",
            short_description=(
                "На пополнение оборотных средств, развитие бизнеса "
                "или рефинансирование текущих долгов."
            ),
            description_plain=(
                "Деньги одной суммой на расчётный счёт без залога имущества. Подойдёт для "
                "оборотных средств, развития бизнеса, исполнения контракта и рефинансирования. "
                "До 5 млн ₽ решение принимается автоматически, от 5 млн ₽ нужна отчётность "
                "за последний год."
            ),
            purposes=frozenset(
                {"working_capital", "expansion", "refinancing", "contract_execution"}
            ),
            facility="term_loan",
            repayment_options=("annuity", "differentiated"),
            amount=AmountRange(_rub(300_000), _rub(30 * MLN)),
            term=TermRange(12, 60),
            rate=RateRange(Decimal("23.5"), Decimal("30")),
            security=SecurityRequirement("none"),
            eligibility=Eligibility(6, ALL_FORMS, _rub(3 * MLN)),
            required_documents=_financials(from_amount=5 * MLN),
            processing=ProcessingProfile("express_v2", _rub(5 * MLN)),
        ),
        CreditProduct(
            code=ProductCode("SECURED"),
            version=1,
            status=ProductStatus.ACTIVE,
            sort_order=2,
            frontend_id="secured",
            name="Кредит под залог",
            short_description=(
                "Крупная сумма на длинный срок под залог недвижимости, транспорта или оборудования."
            ),
            description_plain=(
                "Большая сумма и срок до 10 лет за счёт залога: недвижимость, транспорт или "
                "оборудование. Ставка ниже, чем без залога. Залог описывается в заявке, "
                "документы на него прикладываются."
            ),
            purposes=frozenset({"working_capital", "equipment", "expansion", "refinancing"}),
            facility="term_loan",
            repayment_options=("annuity", "differentiated"),
            amount=AmountRange(_rub(500_000), _rub(150 * MLN)),
            term=TermRange(12, 120),
            rate=RateRange(Decimal("21.5"), Decimal("27")),
            security=SecurityRequirement(
                "required", ("real_estate", "vehicle", "equipment"), guarantee="owner"
            ),
            eligibility=Eligibility(12, ALL_FORMS, _rub(10 * MLN)),
            required_documents=(*_financials(), COLLATERAL_DOCUMENTS),
            processing=ProcessingProfile("secured_v2", _rub(10 * MLN)),
        ),
        CreditProduct(
            code=ProductCode("CREDIT_LINE"),
            version=1,
            status=ProductStatus.ACTIVE,
            sort_order=3,
            frontend_id="credit-line",
            name="Кредитная линия",
            short_description=(
                "Берите деньги частями в пределах лимита, проценты начисляются "
                "только на использованную сумму."
            ),
            description_plain=(
                "Возобновляемый лимит: деньги берутся траншами, когда нужны, и гасятся из "
                "поступлений, после погашения лимит снова доступен. Закрывает кассовые разрывы "
                "и исполнение контрактов. Залог по желанию, от 30 млн ₽ — обязателен."
            ),
            purposes=frozenset({"working_capital", "cash_gap", "contract_execution"}),
            facility="credit_line_revolving",
            repayment_options=("interest_only", "annuity"),
            amount=AmountRange(_rub(1 * MLN), _rub(50 * MLN)),
            term=TermRange(12, 36),
            rate=RateRange(Decimal("22"), Decimal("28")),
            security=SecurityRequirement(
                "optional",
                ("real_estate", "vehicle", "equipment", "goods"),
                required_from=_rub(30 * MLN),
            ),
            eligibility=Eligibility(12, ALL_FORMS, _rub(12 * MLN)),
            required_documents=_financials(),
            processing=ProcessingProfile("standard_v2", _rub(10 * MLN)),
        ),
        CreditProduct(
            code=ProductCode("OVERDRAFT"),
            version=1,
            status=ProductStatus.ACTIVE,
            sort_order=4,
            frontend_id="overdraft",
            name="Овердрафт",
            short_description=(
                "Платите поставщикам и налоги, даже когда на расчётном счёте "
                "временно не хватает денег."
            ),
            description_plain=(
                "Платежи проходят, даже когда на счёте не хватает денег: банк добавляет "
                "недостающее, долг гасится из первых поступлений. Лимит считается по оборотам "
                "счёта, поэтому нужна выписка за 6 месяцев."
            ),
            purposes=frozenset({"cash_gap"}),
            facility="overdraft",
            repayment_options=("interest_only",),
            amount=AmountRange(_rub(100_000), _rub(10 * MLN)),
            term=TermRange(3, 12),
            rate=RateRange(Decimal("24"), Decimal("30")),
            security=SecurityRequirement("none"),
            eligibility=Eligibility(6, ALL_FORMS, _rub(5 * MLN)),
            required_documents=(BANK_STATEMENT,),
            processing=ProcessingProfile("express_v2", _rub(10 * MLN)),
        ),
        CreditProduct(
            code=ProductCode("AUTO"),
            version=1,
            status=ProductStatus.ACTIVE,
            sort_order=5,
            frontend_id="auto",
            name="Автокредит для бизнеса",
            short_description=(
                "Легковой и грузовой транспорт или спецтехника для бизнеса: в залог идёт покупка."
            ),
            description_plain=(
                "Кредит на покупку транспорта или спецтехники у продавца. Деньги идут продавцу, "
                "купленный транспорт становится залогом. В заявке — что покупаете, у кого и за "
                "сколько."
            ),
            purposes=frozenset({"vehicles"}),
            facility="term_loan",
            repayment_options=("annuity", "differentiated"),
            amount=AmountRange(_rub(500_000), _rub(50 * MLN)),
            term=TermRange(12, 84),
            rate=RateRange(Decimal("20"), Decimal("26")),
            security=SecurityRequirement("required", ("vehicle",)),
            target_use_confirmation=True,
            eligibility=Eligibility(6, ALL_FORMS, _rub(5 * MLN)),
            required_documents=(PURCHASE_CONTRACT,),
            application_fields_schema=AUTO_FIELDS,
            processing=ProcessingProfile("secured_v2", _rub(10 * MLN)),
        ),
        CreditProduct(
            code=ProductCode("MORTGAGE"),
            version=1,
            status=ProductStatus.ACTIVE,
            sort_order=6,
            frontend_id="mortgage",
            name="Бизнес-ипотека",
            short_description=(
                "Покупка коммерческой недвижимости: офис, склад, торговое помещение "
                "или производство."
            ),
            description_plain=(
                "Кредит на покупку коммерческой недвижимости, она же становится залогом. "
                "Только для ООО и АО со сроком работы от 2 лет. Каждую заявку рассматривает "
                "андеррайтер."
            ),
            purposes=frozenset({"real_estate"}),
            facility="term_loan",
            repayment_options=("annuity", "differentiated"),
            amount=AmountRange(_rub(3 * MLN), _rub(150 * MLN)),
            term=TermRange(24, 120),
            rate=RateRange(Decimal("23"), Decimal("28")),
            security=SecurityRequirement("required", ("real_estate",), guarantee="owner"),
            target_use_confirmation=True,
            eligibility=Eligibility(24, COMPANIES, _rub(30 * MLN)),
            required_documents=(
                _financials()[0],
                PURCHASE_CONTRACT,
                COLLATERAL_DOCUMENTS,
            ),
            application_fields_schema=MORTGAGE_FIELDS,
            processing=ProcessingProfile("mortgage_v2", _rub(0)),
        ),
        CreditProduct(
            code=ProductCode("REFINANCE"),
            version=1,
            status=ProductStatus.ACTIVE,
            sort_order=7,
            frontend_id="refinance",
            name="Рефинансирование",
            short_description=(
                "Переведите кредиты других банков в один: понятный график и, возможно, ниже ставка."
            ),
            description_plain=(
                "Новый кредит гасит кредиты в других банках, остаётся один платёж. В заявке — "
                "список кредитов с остатком и платежом. Залог по желанию, от 50 млн ₽ — "
                "обязателен."
            ),
            purposes=frozenset({"refinancing"}),
            facility="term_loan",
            repayment_options=("annuity", "differentiated"),
            amount=AmountRange(_rub(1 * MLN), _rub(100 * MLN)),
            term=TermRange(12, 84),
            rate=RateRange(Decimal("21"), Decimal("27")),
            security=SecurityRequirement(
                "optional", ("real_estate", "vehicle", "equipment"), required_from=_rub(50 * MLN)
            ),
            target_use_confirmation=True,
            eligibility=Eligibility(12, ALL_FORMS, _rub(10 * MLN)),
            required_documents=(EXISTING_LOANS,),
            application_fields_schema=REFINANCE_FIELDS,
            processing=ProcessingProfile("standard_v2", _rub(10 * MLN)),
        ),
        CreditProduct(
            code=ProductCode("GOV_SUPPORT"),
            version=1,
            status=ProductStatus.ACTIVE,
            sort_order=8,
            frontend_id="gov-support",
            name="Кредит с господдержкой",
            short_description=(
                "Льготная ставка для малого и среднего бизнеса из приоритетных отраслей."
            ),
            description_plain=(
                "Ставка не выше 15% годовых за счёт программы господдержки. Для компаний из "
                "реестра МСП в приоритетных отраслях: сельское хозяйство, производство, гостиницы "
                "и общепит, IT, наука, здравоохранение. Поручитель — Корпорация МСП."
            ),
            purposes=frozenset({"working_capital", "equipment", "expansion"}),
            facility="term_loan",
            repayment_options=("annuity", "differentiated"),
            amount=AmountRange(_rub(1 * MLN), _rub(100 * MLN)),
            term=TermRange(12, 60),
            rate=RateRange(Decimal("12"), Decimal("18")),
            security=SecurityRequirement("none", guarantee="msp_corporation"),
            support_program=SupportProgram(
                code="MSP_PRIORITY",
                name="Льготное кредитование МСП в приоритетных отраслях",
                rate_cap=Decimal("15"),
                msp_registry_required=True,
                okved_whitelist=PRIORITY_OKVED,
            ),
            target_use_confirmation=True,
            eligibility=Eligibility(12, ALL_FORMS, _rub(10 * MLN)),
            required_documents=_financials(),
            processing=ProcessingProfile("standard_v2", _rub(10 * MLN)),
        ),
        CreditProduct(
            code=ProductCode("STARTUP"),
            version=1,
            status=ProductStatus.ACTIVE,
            sort_order=9,
            frontend_id="startup",
            name="Кредит на запуск бизнеса",
            short_description=(
                "Для компании без оборотов: оценка по личной кредитной истории учредителя "
                "и бизнес-плану."
            ),
            description_plain=(
                "Кредит на старт для компании младше полугода или без годовой отчётности. "
                "Сначала проверяем личную кредитную историю учредителя (нужно его согласие), "
                "затем специалист оценивает бизнес-план, финансовую модель, обеспечение и "
                "участие в программе господдержки. Поручительство учредителя обязательно."
            ),
            purposes=frozenset({"working_capital", "equipment", "expansion"}),
            facility="term_loan",
            repayment_options=("annuity",),
            amount=AmountRange(_rub(500_000), _rub(5 * MLN)),
            term=TermRange(12, 60),
            rate=RateRange(Decimal("15"), Decimal("26")),
            security=SecurityRequirement("none", guarantee="owner"),
            support_program=SupportProgram(
                code="MSP_START",
                name="Льготное кредитование начинающих предпринимателей",
                rate_cap=Decimal("17"),
                msp_registry_required=False,
                okved_whitelist=PRIORITY_OKVED,
            ),
            target_use_confirmation=True,
            eligibility=Eligibility(0, ALL_FORMS, None, startup_only=True),
            required_documents=(BUSINESS_PLAN, FINANCIAL_MODEL),
            # Проектная оценка: каждую заявку решает андеррайтер.
            processing=ProcessingProfile("startup_v2", _rub(0)),
        ),
    )


async def seed(context: "SeedContext") -> None:
    """Idempotent: upsert by code and version."""
    async with context.session_factory() as session:
        repository = SqlAlchemyProductRepository(session)
        for product in catalog():
            await repository.save(product)
        await session.commit()
