"""Facts and template answers per scenario.

Each builder returns the facts (CONTEXT for the model, allowed numbers for the
post-check) and the template answer: the rules mode answer and the fallback
when the model is off, slow or fails the post-check.
"""

import re
from dataclasses import dataclass

from src.modules.assistant.domain.facts import Facts, day, money, months, percent
from src.modules.assistant.domain.intents import PaymentQuery, normalize
from src.modules.assistant.domain.views import (
    ApplicationView,
    ClientDecisionView,
    PaymentView,
    ProductView,
)

OUTCOME_RU = {
    "APPROVE": "заявка одобрена",
    "COUNTER_OFFER": "встречное предложение",
    "REQUEST_INFO": "нужна дополнительная информация",
    "MANUAL_REVIEW": "заявку рассматривает специалист банка",
    "REJECT": "отказ",
}
STATUS_RU = {
    "draft": "черновик",
    "submitted": "отправлена",
    "in_review": "на рассмотрении",
    "info_requested": "нужна информация от вас",
    "offer_ready": "решение готово",
    "signing": "подписание договора",
    "signed": "договор подписан",
    "disbursed": "кредит выдан",
    "rejected": "отказ",
    "offer_declined": "вы отказались от предложения",
    "expired": "срок предложения истёк",
    "cancelled": "заявка отозвана",
}
ACTIVE_STATUSES = frozenset(
    {"draft", "submitted", "in_review", "info_requested", "offer_ready", "signing", "signed"}
)
PURPOSE_RU = {
    "working_capital": "пополнение оборотных средств",
    "cash_gap": "кассовый разрыв",
    "equipment": "покупка оборудования",
    "vehicles": "покупка транспорта",
    "real_estate": "покупка недвижимости",
    "contract_execution": "исполнение контракта",
    "refinancing": "рефинансирование",
    "expansion": "развитие бизнеса",
}
SCHEDULE_RU = {
    "annuity": "равными платежами (аннуитет)",
    "differentiated": "дифференцированные платежи: основной долг равными частями",
    "interest_only": "ежемесячно только проценты, долг — в конце срока",
    "by_contract_schedule": "по графику контракта",
}
FACILITY_RU = {
    "term_loan": "деньги одной суммой",
    "credit_line_revolving": "возобновляемая кредитная линия",
    "credit_line_non_revolving": "невозобновляемая кредитная линия",
    "overdraft": "овердрафт по расчётному счёту",
}
COLLATERAL_RU = {"none": "без залога", "optional": "залог по желанию", "required": "нужен залог"}
DOCUMENT_RU = {
    "bank_statement": "выписка по расчётному счёту за 6 месяцев (CSV)",
    "financial_report": "бухгалтерская отчётность за последний год",
    "tax_return": "налоговая декларация за последний год",
    "collateral_documents": "документы на залог: право собственности и оценка",
    "purchase_contract": "договор купли-продажи или счёт продавца",
    "existing_loans_statement": "справка о действующих кредитах",
}

# Words of a question → product codes it is about.
_PRODUCT_WORDS: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = (
    (re.compile(r"без\s+залог|беззалог", re.I), ("UNSECURED",)),
    (re.compile(r"под\s+залог|залогов", re.I), ("SECURED",)),
    (re.compile(r"кредитн\w+\s+лини|\bлини[яиюей]\b", re.I), ("CREDIT_LINE",)),
    (re.compile(r"овердрафт", re.I), ("OVERDRAFT",)),
    (re.compile(r"автокредит|авто\b|машин|транспорт|грузовик", re.I), ("AUTO",)),
    (re.compile(r"ипотек|недвижим|помещени|склад|офис", re.I), ("MORTGAGE",)),
    (re.compile(r"рефинанс|перекредит|погасить\s+друг", re.I), ("REFINANCE",)),
    (re.compile(r"господдерж|льготн|програм\w+\s+мсп", re.I), ("GOV_SUPPORT",)),
    (re.compile(r"кассов\w*\s+разрыв|не\s+хватает\s+денег", re.I), ("OVERDRAFT", "CREDIT_LINE")),
    (re.compile(r"оборудован|станок|станк", re.I), ("SECURED", "GOV_SUPPORT")),
    (re.compile(r"оборотн|закупк|товар", re.I), ("UNSECURED", "CREDIT_LINE")),
    (re.compile(r"контракт|госзаказ|тендер", re.I), ("CREDIT_LINE", "UNSECURED")),
)

ROLE_LINE = (
    "Я помощник кредитного кабинета: объясняю решение по заявке, подсказываю, что делать "
    "дальше, рассказываю о кредитах банка и считаю платёж калькулятором."
)


@dataclass(frozen=True, slots=True)
class Draft:
    facts: Facts
    template: str
    # The model may reword only answers built from facts; refusals stay templates.
    rewordable: bool = True


# ---------- facts ----------


def application_facts(app: ApplicationView, product_name: str) -> list[str]:
    lines = [f"Заявка № {app.number}, продукт «{product_name}»."]
    if app.request:
        purpose = PURPOSE_RU.get(app.request.purpose, app.request.purpose)
        lines.append(
            f"Запрошено: {money(app.request.amount)} на {months(app.request.term_months)}, "
            f"цель — {purpose}."
        )
    lines.append(f"Статус заявки: {STATUS_RU.get(app.status, app.status)}.")
    if app.client_stage:
        lines.append(f"Этап: {app.client_stage}.")
    return lines


def decision_facts(decision: ClientDecisionView, products: dict[str, ProductView]) -> list[str]:
    lines = [f"Решение банка: {OUTCOME_RU.get(decision.outcome, decision.outcome)}."]
    lines.append(f"Объяснение банка: {decision.client_explanation}")
    if decision.terms:
        t = decision.terms
        lines.append(
            f"Предложение банка: {money(t.amount)} на {months(t.term_months)}, ставка "
            f"{percent(t.rate)} годовых, ежемесячный платёж {money(t.monthly_payment)}, "
            f"{SCHEDULE_RU.get(t.schedule_type, t.schedule_type)}. "
            f"Предложение действует до {day(t.expires_at)}."
        )
        lines.extend(f"Условие: {c}" for c in t.conditions)
    if decision.alternative_product_code:
        alt = products.get(decision.alternative_product_code)
        if alt:
            lines.append(f"Банк советует также продукт «{alt.name}»: {alt.short_description}")
    if decision.requested_info:
        info = decision.requested_info
        docs = ", ".join(DOCUMENT_RU.get(d, d) for d in info.documents)
        lines.append(f"Банк просит: {info.comment}" + (f" Документы: {docs}." if docs else ""))
    lines.extend(f"Что можно сделать: {hint}" for hint in decision.improvement_hints)
    return lines


def product_facts(product: ProductView) -> list[str]:
    lines = [
        f"Продукт «{product.name}»: {product.description_plain}",
        f"«{product.name}»: сумма от {money(product.amount_min)} до {money(product.amount_max)}, "
        f"срок от {months(product.term_min_months)} до {months(product.term_max_months)}, "
        f"ставка от {percent(product.rate_base)} до {percent(product.rate_max)} годовых, "
        f"{FACILITY_RU.get(product.facility, product.facility)}, "
        f"{COLLATERAL_RU.get(product.collateral_kind, product.collateral_kind)}.",
        f"«{product.name}», погашение: "
        + "; ".join(SCHEDULE_RU.get(r, r) for r in product.repayment_options)
        + ".",
    ]
    requirements = [f"бизнесу не меньше {months(product.min_business_age_months)}"]
    if product.min_annual_revenue:
        requirements.append(f"выручка за год от {money(product.min_annual_revenue)}")
    lines.append(f"«{product.name}», требования: " + ", ".join(requirements) + ".")
    if product.required_documents:
        docs = []
        for d in product.required_documents:
            title = d.title
            if d.required_from_amount:
                title += f" (при сумме от {money(d.required_from_amount)})"
            docs.append(title)
        lines.append(f"«{product.name}», документы: " + "; ".join(docs) + ".")
    if product.support_program_name and product.support_rate_cap:
        lines.append(
            f"«{product.name}»: программа «{product.support_program_name}», ставка не выше "
            f"{percent(product.support_rate_cap)} годовых для компаний из реестра МСП "
            f"в приоритетных отраслях."
        )
    return lines


# ---------- scenarios ----------


def explain_decision(
    app: ApplicationView,
    decision: ClientDecisionView | None,
    products: dict[str, ProductView],
) -> Draft:
    facts = Facts()
    facts.extend(application_facts(app, _name(products, app.product_code)))
    if decision is None:
        facts.add("Решения по заявке ещё нет.")
        template = (
            f"По заявке № {app.number} решения пока нет: она на этапе "
            f"«{app.client_stage or STATUS_RU.get(app.status, app.status)}». "
            "Как только банк примет решение, оно появится в карточке заявки."
        )
        return Draft(facts, template)
    facts.outcome = decision.outcome
    facts.extend(decision_facts(decision, products))
    _add_client_text(facts, app)

    parts = [f"По заявке № {app.number}: {decision.client_explanation}"]
    if decision.terms:
        t = decision.terms
        parts.append(
            f"Условия: {money(t.amount)} на {months(t.term_months)} под {percent(t.rate)} "
            f"годовых, платёж {money(t.monthly_payment)} в месяц. Предложение действует до "
            f"{day(t.expires_at)} — принять или отклонить его можно в карточке заявки."
        )
        if t.conditions:
            parts.append("Условия банка: " + "; ".join(t.conditions) + ".")
    if decision.alternative_product_code and decision.alternative_product_code in products:
        alt = products[decision.alternative_product_code]
        parts.append(f"Также посмотрите продукт «{alt.name}»: {alt.short_description}")
    if decision.requested_info:
        parts.append(_requested_info_text(decision))
    if decision.improvement_hints:
        parts.append("Что можно сделать: " + " ".join(decision.improvement_hints))
    return Draft(facts, "\n\n".join(parts))


def application_status(
    app: ApplicationView,
    decision: ClientDecisionView | None,
    products: dict[str, ProductView],
    *,
    can_sign: bool,
) -> Draft:
    facts = Facts()
    facts.extend(application_facts(app, _name(products, app.product_code)))
    open_requests = [r for r in app.info_requests if r.status == "open"]
    for r in open_requests:
        docs = ", ".join(DOCUMENT_RU.get(d, d) for d in r.requested_documents)
        due = f" Срок — до {day(r.due_at)}." if r.due_at else ""
        facts.add(f"Открытый дозапрос: {r.comment} Документы: {docs or 'нет'}.{due}")
    if decision is not None:
        facts.outcome = decision.outcome
        facts.extend(decision_facts(decision, products))
    if app.status == "signing":
        facts.add(
            "Договор подписывает руководитель компании или сотрудник с доверенностью на подпись."
        )
        facts.add(f"У этого пользователя {'есть' if can_sign else 'нет'} права подписи.")

    status = STATUS_RU.get(app.status, app.status)
    head = f"Заявка № {app.number} — {status}"
    if app.client_stage and app.client_stage.lower() != status.lower():
        head += f", этап «{app.client_stage}»"
    head += "."
    match app.status:
        case "draft":
            step = "Заявка ещё не отправлена: заполните анкету, приложите документы и отправьте её."
        case "submitted" | "in_review":
            step = (
                "От вас сейчас ничего не нужно: банк проверяет данные. "
                "О решении мы сообщим в кабинете."
            )
            if decision is not None and decision.outcome == "MANUAL_REVIEW":
                step = decision.client_explanation
        case "info_requested":
            if open_requests:
                r = open_requests[0]
                docs = ", ".join(DOCUMENT_RU.get(d, d) for d in r.requested_documents)
                due = f" до {day(r.due_at)}" if r.due_at else ""
                step = f"Банку нужна информация: {r.comment} Загрузите в карточке заявки{due}"
                step += f": {docs}." if docs else " недостающие данные."
            else:
                step = "Банку нужна информация — откройте карточку заявки, там список."
        case "offer_ready":
            # «решение готово» is already in the head, from STATUS_RU.
            step = "Условия предложения — в карточке заявки."
            if decision is not None and decision.terms:
                t = decision.terms
                step = (
                    f"Банк предлагает {money(t.amount)} на {months(t.term_months)} "
                    f"под {percent(t.rate)} годовых, платёж {money(t.monthly_payment)} в месяц. "
                    f"Примите или отклоните предложение в карточке заявки до {day(t.expires_at)}."
                )
        case "signing":
            step = (
                "Договор ждёт подписи. Подписать может руководитель или сотрудник с "
                "доверенностью на подпись."
            )
            if not can_sign:
                step += (
                    " У вас права подписи нет: попросите руководителя подписать договор "
                    "или выдать вам доверенность."
                )
        case "signed" | "disbursed":
            step = "Договор подписан, деньги перечисляются на расчётный счёт."
        case "rejected":
            step = decision.client_explanation if decision else "Банк не одобрил заявку."
            if decision and decision.improvement_hints:
                step += " Что можно сделать: " + " ".join(decision.improvement_hints)
        case _:
            step = "Заявка закрыта. Если кредит всё ещё нужен, подайте новую заявку."
    return Draft(facts, f"{head} {step}")


def applications_overview(apps: list[ApplicationView], products: dict[str, ProductView]) -> Draft:
    facts = Facts()
    active = [a for a in apps if a.status in ACTIVE_STATUSES]
    if not active:
        facts.add("Активных заявок нет.")
        return Draft(
            facts,
            "Активных заявок у вас нет. Подобрать кредит и подать заявку можно на главной "
            "странице кабинета.",
        )
    lines = []
    for a in active:
        line = (
            f"Заявка № {a.number} «{_name(products, a.product_code)}» — "
            f"{STATUS_RU.get(a.status, a.status)}"
            + (f", этап «{a.client_stage}»" if a.client_stage else "")
            + "."
        )
        facts.add(line)
        lines.append(line)
    return Draft(
        facts,
        "Ваши заявки:\n"
        + "\n".join(f"— {line}" for line in lines)
        + "\n\nВыберите заявку в кабинете, и я расскажу подробнее.",
    )


def products_answer(question: str, products: list[ProductView]) -> Draft:
    matched = match_products(question, products)
    facts = Facts()
    if not matched:
        for p in products:
            facts.add(
                f"«{p.name}»: {p.short_description} Сумма до {money(p.amount_max)}, "
                f"ставка от {percent(p.rate_base)} годовых."
            )
        lines = [
            f"— «{p.name}»: до {money(p.amount_max)}, от {percent(p.rate_base)} годовых. "
            f"{p.short_description}"
            for p in products
        ]
        return Draft(
            facts,
            "Кредиты банка для бизнеса:\n" + "\n".join(lines) + "\n\nСпросите про любой — "
            "расскажу условия и документы или посчитаю платёж.",
        )
    for p in matched:
        facts.extend(product_facts(p))
    blocks = []
    for p in matched:
        docs = "; ".join(d.title for d in p.required_documents) or "отдельные документы не нужны"
        blocks.append(
            f"«{p.name}»: {p.description_plain} Сумма от {money(p.amount_min)} до "
            f"{money(p.amount_max)}, срок от {months(p.term_min_months)} до "
            f"{months(p.term_max_months)}, ставка от {percent(p.rate_base)} до "
            f"{percent(p.rate_max)} годовых — точную ставку банк назначит после оценки заявки. "
            f"Документы: {docs}."
        )
    return Draft(facts, "\n\n".join(blocks))


def payment_answer(
    query: PaymentQuery,
    schedule: PaymentView | None,
    product: ProductView | None,
    source: str,
) -> Draft:
    facts = Facts()
    if schedule is None:
        facts.add("Для расчёта нужны сумма и срок.")
        example = "«Сколько платить за 3 млн на 24 месяца по кредиту без залога?»"
        return Draft(
            facts,
            "Чтобы посчитать платёж, напишите сумму и срок, например: " + example,
            rewordable=False,
        )
    if product:
        facts.add(f"Продукт «{product.name}».")
    facts.add(
        f"Расчёт калькулятора: {money(schedule.amount)} на {months(schedule.term_months)} "
        f"под {percent(schedule.rate)} годовых ({source}), "
        f"{SCHEDULE_RU.get(schedule.repayment, schedule.repayment)}: "
        f"ежемесячный платёж {money(schedule.monthly_payment)}, переплата "
        f"{money(schedule.total_interest)}, всего {money(schedule.total_paid)}."
    )
    first = "первый платёж" if schedule.repayment != "annuity" else "платёж"
    template = (
        f"Если взять {money(schedule.amount)} на {months(schedule.term_months)} под "
        f"{percent(schedule.rate)} годовых ({source}), {first} — {money(schedule.monthly_payment)} "
        f"в месяц, переплата — {money(schedule.total_interest)}, всего вернёте "
        f"{money(schedule.total_paid)}. Это предварительный расчёт: точные условия банк "
        "назовёт после оценки заявки."
    )
    return Draft(facts, template)


def internal_data_refusal(decision: ClientDecisionView | None) -> Draft:
    facts = Facts()
    text = (
        "Внутреннюю оценку заявки — баллы, рейтинги, данные кредитной истории и правила банка — "
        "я не раскрываю. Могу объяснить решение так, как его сформулировал банк, и подсказать, "
        "что поможет получить условия лучше."
    )
    if decision and decision.improvement_hints:
        facts.extend(f"Что можно сделать: {h}" for h in decision.improvement_hints)
        text += " Что можно сделать: " + " ".join(decision.improvement_hints)
    return Draft(facts, text, rewordable=False)


def injection_refusal() -> Draft:
    return Draft(
        Facts(),
        "Я не меняю свои правила и не могу повлиять на решение банка, статус заявки или "
        "условия. " + ROLE_LINE,
        rewordable=False,
    )


def off_topic() -> Draft:
    return Draft(
        Facts(),
        "С этим я не помогу. " + ROLE_LINE + " Например: «Почему мне предложили другие условия?», "
        "«Что с моей заявкой?», «Сколько платить за 2 млн на 2 года?».",
        rewordable=False,
    )


def greeting() -> Draft:
    return Draft(
        Facts(),
        "Здравствуйте! " + ROLE_LINE + " Решение по заявке принимает банк, я его только объясняю.",
        rewordable=False,
    )


def need_application() -> Draft:
    return Draft(
        Facts(),
        "Чтобы ответить про решение, выберите заявку в кабинете — я расскажу, что решил банк "
        "и что можно сделать дальше.",
        rewordable=False,
    )


# ---------- helpers ----------


def match_products(question: str, products: list[ProductView]) -> list[ProductView]:
    by_code = {p.code: p for p in products}
    text = normalize(question)
    codes: list[str] = []
    for p in products:
        if normalize(p.name).lower() in text.lower() and p.code not in codes:
            codes.append(p.code)
    for pattern, matched in _PRODUCT_WORDS:
        if pattern.search(text):
            codes.extend(c for c in matched if c not in codes)
    return [by_code[c] for c in codes if c in by_code][:2]


def _name(products: dict[str, ProductView], code: str) -> str:
    product = products.get(code)
    return product.name if product else code


def _requested_info_text(decision: ClientDecisionView) -> str:
    info = decision.requested_info
    assert info is not None
    docs = ", ".join(DOCUMENT_RU.get(d, d) for d in info.documents)
    return f"Банк просит: {info.comment}" + (
        f" Загрузите в карточке заявки: {docs}." if docs else ""
    )


def _add_client_text(facts: Facts, app: ApplicationView) -> None:
    if app.request and app.request.purpose_comment:
        cleaned = re.sub(r"[<>{}\[\]`]", " ", app.request.purpose_comment)
        facts.client_text.append(" ".join(cleaned.split())[:200])
