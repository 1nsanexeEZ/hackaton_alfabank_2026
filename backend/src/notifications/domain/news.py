"""Personal news: deterministic ranking of articles for a company profile.

An article is shown when it is general or matches the company by industry
(OKVED prefix), product interest or legal form. Each match adds points and a
human reason, so the cabinet can say why the article was picked."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

# Points of one match. The industry is the strongest signal of relevance.
OKVED_MAIN_POINTS = 30
OKVED_MAIN_EXACT_BONUS = 10  # prefix deeper than the two-digit class
OKVED_EXTRA_POINTS = 15
PRODUCT_POINTS = 20
LEGAL_FORM_POINTS = 10
GENERAL_POINTS = 1

GENERAL_REASON = "для всех клиентов"

OKVED_CLASS_TITLES: dict[str, str] = {
    "01": "сельское хозяйство",
    "10": "производство пищевых продуктов",
    "41": "строительство зданий",
    "42": "строительство инженерных сооружений",
    "43": "специализированные строительные работы",
    "45": "торговля автомобилями",
    "46": "оптовая торговля",
    "47": "розничная торговля",
    "49": "сухопутный транспорт",
    "52": "складское хозяйство",
    "55": "гостиницы",
    "56": "общепит",
    "62": "разработка ПО",
    "63": "IT-услуги",
    "68": "операции с недвижимостью",
    "72": "научные исследования",
    "86": "здравоохранение",
}

LEGAL_FORM_TITLES: dict[str, str] = {"LLC": "ООО", "IE": "ИП", "JSC": "АО"}


def _digits(code: str) -> str:
    return "".join(ch for ch in code if ch.isdigit())


def okved_matches(prefix: str, code: str) -> bool:
    """'56' and '56.1' match '56.10'; '5' is not a prefix (at least a class)."""
    wanted = _digits(prefix)
    return len(wanted) >= 2 and _digits(code).startswith(wanted)


def okved_reason(prefix: str, extra: bool = False) -> str:
    title = OKVED_CLASS_TITLES.get(_digits(prefix)[:2])
    label = f"доп. ОКВЭД {prefix}" if extra else f"ОКВЭД {prefix}"
    return f"{label} — {title}" if title else label


@dataclass(frozen=True, slots=True)
class NewsArticle:
    id: UUID
    slug: str
    title: str
    body: str
    published_at: datetime
    okved_prefixes: tuple[str, ...] = ()
    product_codes: tuple[str, ...] = ()
    legal_forms: tuple[str, ...] = ()
    is_general: bool = False


@dataclass(frozen=True, slots=True)
class CompanyProfile:
    okved_main: str | None = None
    okved_extra: tuple[str, ...] = ()
    legal_form: str | None = None
    # Product code -> why the company is interested ("есть заявка", "предодобрен").
    products: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RankedNews:
    article: NewsArticle
    score: int
    relevance: tuple[str, ...]


def score_article(article: NewsArticle, profile: CompanyProfile) -> RankedNews | None:
    points = 0
    reasons: list[str] = []

    best_okved: tuple[int, str] | None = None
    for prefix in article.okved_prefixes:
        if profile.okved_main and okved_matches(prefix, profile.okved_main):
            value = OKVED_MAIN_POINTS + (OKVED_MAIN_EXACT_BONUS if len(_digits(prefix)) > 2 else 0)
            candidate = (value, okved_reason(prefix))
        elif any(okved_matches(prefix, code) for code in profile.okved_extra):
            candidate = (OKVED_EXTRA_POINTS, okved_reason(prefix, extra=True))
        else:
            continue
        if best_okved is None or candidate[0] > best_okved[0]:
            best_okved = candidate
    if best_okved is not None:
        points += best_okved[0]
        reasons.append(best_okved[1])

    for code in article.product_codes:
        why = profile.products.get(code)
        if why is not None:
            points += PRODUCT_POINTS
            reasons.append(f"продукт {code} — {why}")

    if profile.legal_form and profile.legal_form in article.legal_forms:
        points += LEGAL_FORM_POINTS
        title = LEGAL_FORM_TITLES.get(profile.legal_form, profile.legal_form)
        reasons.append(f"форма бизнеса — {title}")

    if article.is_general:
        points += GENERAL_POINTS
        if not reasons:
            reasons.append(GENERAL_REASON)

    if not reasons:
        return None
    return RankedNews(article, points, tuple(reasons))


def rank_news(
    articles: Iterable[NewsArticle], profile: CompanyProfile, limit: int
) -> list[RankedNews]:
    """Most relevant first; equal scores — newer first, then by slug (stable)."""
    ranked = [r for r in (score_article(a, profile) for a in articles) if r is not None]
    ranked.sort(key=lambda r: (-r.score, -r.article.published_at.timestamp(), r.article.slug))
    return ranked[: max(limit, 0)]
