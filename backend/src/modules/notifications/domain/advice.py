"""Personal advice from scoring flags and decision reason codes.

Flags are matched by keywords, so `cash_gap`, `cash_gap_forecast` and
`CASH_GAP_RISK` give the same advice; unknown flags are ignored."""

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Advice:
    code: str
    title: str
    body: str
    # May contain {application_id} / {organization_id}.
    link: str | None
    keywords: tuple[str, ...]
    # The advice suggests these products: pointless if the application is for one of them.
    products: tuple[str, ...] = ()

    def matches(self, signal: str) -> bool:
        normalized = signal.strip().lower()
        return any(keyword in normalized for keyword in self.keywords)


RULES: tuple[Advice, ...] = (
    Advice(
        code="cash_gap",
        title="Прогнозируется кассовый разрыв — посмотрите кредитную линию",
        body=(
            "По движению денег на счёте ожидается период, когда поступлений не хватит "
            "на платежи. Кредитная линия или овердрафт закроют разрыв: проценты — "
            "только за дни, когда деньги использованы."
        ),
        link="/products/CREDIT_LINE",
        keywords=("cash_gap", "cashgap", "liquidity_gap"),
        products=("CREDIT_LINE", "OVERDRAFT"),
    ),
    Advice(
        code="confirm_revenue",
        title="Подтвердите выручку выпиской — условия станут лучше",
        body=(
            "Заявленная выручка пока не подтверждена. Загрузите выписку по расчётному "
            "счёту за 12 месяцев: подтверждённые обороты увеличивают доступную сумму "
            "и снижают ставку."
        ),
        link="/applications/{application_id}",
        keywords=(
            "revenue_unconfirmed",
            "revenue_not_confirmed",
            "unconfirmed_revenue",
            "unverified_revenue",
            "revenue_mismatch",
            "revenue_discrepancy",
        ),
    ),
    Advice(
        code="young_business",
        title="Бизнесу меньше года — какие продукты доступны",
        body=(
            "Кредитная линия и кредит с господдержкой доступны компаниям от 12 месяцев "
            "работы. Пока подойдут кредит без залога и овердрафт, а после года работы "
            "выбор расширится."
        ),
        link="/products/OVERDRAFT",
        keywords=("young_business", "short_history", "business_age", "new_business"),
    ),
    Advice(
        code="debt_load",
        title="Высокая долговая нагрузка — рефинансирование снизит платёж",
        body=(
            "Платежи по текущим кредитам занимают большую часть дохода. Рефинансирование "
            "объединит кредиты в один и уменьшит ежемесячный платёж."
        ),
        link="/products/REFINANCE",
        keywords=("debt_load", "debt_burden", "high_dti", "dsti"),
        products=("REFINANCE",),
    ),
    Advice(
        code="tax_arrears",
        title="Есть задолженность перед бюджетом",
        body=(
            "Погасите налоговую задолженность и обновите данные в заявке: "
            "с долгом перед бюджетом кредит не одобряется."
        ),
        link="/applications/{application_id}",
        keywords=("tax_arrear", "tax_debt"),
    ),
    Advice(
        code="registry_mismatch",
        title="Сведения о компании расходятся с реестром",
        body=(
            "Проверьте руководителя и реквизиты в карточке компании. Пока расхождение "
            "не устранено, условия могут быть хуже, а подписание — недоступно."
        ),
        link="/organizations/{organization_id}",
        keywords=("registry_mismatch", "verification_mismatch", "head_mismatch"),
    ),
    Advice(
        code="add_collateral",
        title="Залог снизит ставку",
        body=(
            "Сумма заявки высока для кредита без обеспечения. Кредит под залог "
            "недвижимости, транспорта или оборудования — это большая сумма и ниже ставка."
        ),
        link="/products/SECURED",
        keywords=("collateral_recommended", "low_collateral", "ltv_high", "amount_over_limit"),
        products=("SECURED", "MORTGAGE", "AUTO"),
    ),
)


def advice_for(signals: Iterable[str], current_product: str | None = None) -> list[Advice]:
    """Advice for every rule some signal matches, in the order of RULES, each once."""
    normalized = [s for s in signals if s]
    return [
        rule
        for rule in RULES
        if any(rule.matches(signal) for signal in normalized)
        and (current_product is None or current_product not in rule.products)
    ]
