"""Seed of notifications: news articles with relevance tags.

Idempotent by slug: the id is derived from the slug, a rerun refreshes texts
and tags and keeps the publication date. Tags drive personal ranking: OKVED
prefixes (industry), product codes (seed.demo_data.PRODUCT_CODES), legal forms
and `general` — so the feed of ООО «Ромашка» (56.10) and ИП Иванова (62.01) differs.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, UUID, uuid5

from seed.demo_data import PRODUCT_CODES
from src.modules.notifications.domain.news import NewsArticle
from src.modules.notifications.infrastructure.repositories.news import SqlAlchemyNewsStore

if TYPE_CHECKING:
    from seed.run import SeedContext


@dataclass(frozen=True, slots=True)
class DemoNews:
    slug: str
    days_ago: int
    title: str
    body: str
    okved: tuple[str, ...] = ()
    products: tuple[str, ...] = ()
    legal_forms: tuple[str, ...] = ()
    general: bool = False


NEWS: tuple[DemoNews, ...] = (
    DemoNews(
        "horeca-gov-support",
        2,
        "Кредит с господдержкой для кафе, ресторанов и гостиниц",
        "Общепит и гостиничный бизнес входят в отрасли программы льготного кредитования: "
        "ставка ограничена потолком программы. Проверьте в кабинете, подходит ли компания "
        "по сроку работы и реестру МСП.",
        okved=("55", "56"),
        products=("GOV_SUPPORT",),
    ),
    DemoNews(
        "horeca-low-season",
        5,
        "Как кафе пережить низкий сезон без кассового разрыва",
        "Выручка общепита заметно меняется по месяцам, а аренда и зарплата — нет. "
        "Кредитная линия с лимитом под оборот закрывает провалы: деньги берутся, когда "
        "поступлений не хватает, и возвращаются в высокий сезон.",
        okved=("56",),
        products=("CREDIT_LINE", "OVERDRAFT"),
    ),
    DemoNews(
        "restaurant-equipment",
        9,
        "Обновить кухню ресторана: кредит под залог оборудования",
        "Новое оборудование может само стать залогом: это снижает ставку и увеличивает "
        "доступную сумму. Подготовьте счёт поставщика — он понадобится в заявке.",
        okved=("56.10",),
        products=("SECURED",),
    ),
    DemoNews(
        "it-gov-support",
        3,
        "Господдержка для IT-компаний: ставка ниже рыночной",
        "Разработка ПО и IT-услуги входят в отрасли программы льготного кредитования. "
        "Программа доступна компаниям из реестра МСП после 12 месяцев работы.",
        okved=("62", "63"),
        products=("GOV_SUPPORT",),
    ),
    DemoNews(
        "it-cash-flow",
        6,
        "Оплата по актам: как IT-команде не ждать денег от заказчика",
        "Заказчики часто платят через 30–60 дней после сдачи этапа. Овердрафт к счёту "
        "покрывает зарплату и подписки на время ожидания — без отдельной заявки на каждый раз.",
        okved=("62",),
        products=("OVERDRAFT",),
    ),
    DemoNews(
        "ie-confirm-income",
        4,
        "ИП на упрощёнке: как подтвердить доход для кредита",
        "Банку не нужна бухгалтерская отчётность ИП: доход подтверждается выпиской по "
        "расчётному счёту и декларацией. Чем полнее выписка, тем точнее лимит.",
        legal_forms=("IE",),
        products=("UNSECURED",),
    ),
    DemoNews(
        "ie-tax-calendar",
        8,
        "Налоговый календарь ИП: что оплатить до конца квартала",
        "Напоминаем о сроках авансовых платежей по упрощённой системе и фиксированных "
        "взносах. Своевременные платежи — плюс к оценке надёжности бизнеса.",
        legal_forms=("IE",),
    ),
    DemoNews(
        "llc-registry-update",
        7,
        "ООО и АО: как обновить сведения о руководителе в реестре",
        "Если руководитель сменился, изменения нужно внести в реестр. Банк сверяет "
        "данные заявки с реестром, и расхождение задерживает подписание договора.",
        legal_forms=("LLC", "JSC"),
    ),
    DemoNews(
        "construction-secured",
        10,
        "Строительным компаниям: оборотный кредит под залог техники",
        "Спецтехника и недвижимость компании снижают ставку и увеличивают сумму кредита. "
        "Удобно для авансирования материалов под новые объекты.",
        okved=("41", "42", "43"),
        products=("SECURED",),
    ),
    DemoNews(
        "transport-fleet",
        11,
        "Перевозчикам: автокредит на обновление парка",
        "Грузовик или фургон становятся залогом по кредиту — первоначальный взнос меньше, "
        "а срок — до семи лет. Понадобится договор с поставщиком транспорта.",
        okved=("49",),
        products=("AUTO",),
    ),
    DemoNews(
        "retail-season",
        12,
        "Розница: оборотные деньги к сезону распродаж",
        "Закупка под сезон требует денег заранее, а выручка приходит позже. Кредитная "
        "линия или овердрафт помогут выкупить товар вовремя.",
        okved=("47",),
        products=("CREDIT_LINE", "OVERDRAFT"),
    ),
    DemoNews(
        "wholesale-deferral",
        13,
        "Оптовикам: кредитная линия под отсрочку платежа покупателям",
        "Отсрочка для покупателей замораживает оборотные средства. Возобновляемая "
        "кредитная линия выравнивает поток платежей.",
        okved=("46",),
        products=("CREDIT_LINE",),
    ),
    DemoNews(
        "overdraft-basics",
        14,
        "Овердрафт: деньги на счёте, когда поступления задерживаются",
        "Овердрафт гасится автоматически из поступлений на счёт, проценты начисляются "
        "только за дни использования. Подходит для коротких разрывов до 30–60 дней.",
        products=("OVERDRAFT",),
    ),
    DemoNews(
        "refinance-basics",
        15,
        "Рефинансирование: объединить кредиты и снизить платёж",
        "Несколько кредитов можно заменить одним: платёж становится один, а срок — длиннее. "
        "Для заявки нужна справка о текущих кредитах.",
        products=("REFINANCE",),
    ),
    DemoNews(
        "mortgage-premises",
        16,
        "Бизнес-ипотека: своё помещение вместо аренды",
        "Платёж по ипотеке сопоставим с арендой, а помещение остаётся у компании. "
        "Решение по бизнес-ипотеке всегда принимает андеррайтер.",
        products=("MORTGAGE",),
        legal_forms=("LLC", "JSC"),
    ),
    DemoNews(
        "key-rate",
        1,
        "Ключевая ставка и стоимость кредита: что важно знать",
        "Ставка по кредиту складывается из ключевой ставки и надбавки за риск. "
        "Подтверждённая выручка и хорошая кредитная история уменьшают надбавку.",
        general=True,
    ),
    DemoNews(
        "how-scoring-works",
        20,
        "Как банк оценивает заявку: пять факторов",
        "Срок работы бизнеса, подтверждённая выручка, долговая нагрузка, кредитная "
        "история и прогноз кассового разрыва. Причины решения видны в кабинете.",
        general=True,
    ),
)

_NAMESPACE = "credit-cabinet/notifications/news/"


def news_id(slug: str) -> UUID:
    return uuid5(NAMESPACE_URL, _NAMESPACE + slug)


def _check() -> None:
    unknown = {code for news in NEWS for code in news.products} - set(PRODUCT_CODES)
    if unknown:
        raise ValueError(f"News refer to unknown products: {sorted(unknown)}")


async def seed(context: "SeedContext") -> None:
    """Idempotent: upsert by slug."""
    _check()
    now = context.clock.now()
    async with context.session_factory() as session:
        store = SqlAlchemyNewsStore(session)
        for news in NEWS:
            await store.upsert(
                NewsArticle(
                    id=news_id(news.slug),
                    slug=news.slug,
                    title=news.title,
                    body=news.body,
                    published_at=now - timedelta(days=news.days_ago),
                    okved_prefixes=news.okved,
                    product_codes=news.products,
                    legal_forms=news.legal_forms,
                    is_general=news.general,
                ),
                now,
            )
        await session.commit()
