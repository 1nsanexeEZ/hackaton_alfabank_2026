"""Personal news: the feed of ООО «Ромашка» (56.10, ООО) and ИП Иванова
(62.01, ИП) is different, and every pick says why."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from seed.notifications import NEWS, news_id
from src.notifications.domain.news import (
    CompanyProfile,
    NewsArticle,
    okved_matches,
    rank_news,
)
from tests.fakes import builders

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def seeded_articles() -> list[NewsArticle]:
    return [
        NewsArticle(
            id=news_id(n.slug),
            slug=n.slug,
            title=n.title,
            body=n.body,
            published_at=NOW - timedelta(days=n.days_ago),
            okved_prefixes=n.okved,
            product_codes=n.products,
            legal_forms=n.legal_forms,
            is_general=n.general,
        )
        for n in NEWS
    ]


def profile_of(code: str, **products: str) -> CompanyProfile:
    snapshot = builders.organization_snapshot(code)
    return CompanyProfile(
        okved_main=snapshot.okved_main,
        okved_extra=snapshot.okved_extra,
        legal_form=snapshot.legal_form,
        products=products,
    )


def test_romashka_and_ivanov_get_different_top_five() -> None:
    articles = seeded_articles()
    romashka = rank_news(articles, profile_of("romashka"), 5)
    ivanov = rank_news(articles, profile_of("ivanov"), 5)

    assert len(romashka) == len(ivanov) == 5
    assert [r.article.slug for r in romashka] != [r.article.slug for r in ivanov]
    assert [r.article.slug for r in romashka] == [
        "restaurant-equipment",
        "horeca-gov-support",
        "horeca-low-season",
        "llc-registry-update",
        "mortgage-premises",
    ]
    assert [r.article.slug for r in ivanov] == [
        "it-gov-support",
        "it-cash-flow",
        "ie-confirm-income",
        "ie-tax-calendar",
        "key-rate",
    ]
    assert romashka[0].relevance == ("ОКВЭД 56.10 — общепит",)
    assert romashka[1].relevance == ("ОКВЭД 56 — общепит",)
    assert ivanov[0].relevance == ("ОКВЭД 62 — разработка ПО",)
    assert ivanov[2].relevance == ("форма бизнеса — ИП",)
    assert ivanov[4].relevance == ("для всех клиентов",)


def test_product_interest_lifts_an_article_and_explains_it() -> None:
    articles = seeded_articles()
    ranked = rank_news(articles, profile_of("ivanov", OVERDRAFT="предодобрен"), 3)
    assert ranked[0].article.slug == "it-cash-flow"
    assert ranked[0].relevance == ("ОКВЭД 62 — разработка ПО", "продукт OVERDRAFT — предодобрен")
    overdraft = rank_news(articles, profile_of("ivanov", OVERDRAFT="предодобрен"), 20)
    assert "overdraft-basics" in {r.article.slug for r in overdraft}


def test_without_a_profile_only_general_news() -> None:
    ranked = rank_news(seeded_articles(), CompanyProfile(), 10)
    assert {r.article.slug for r in ranked} == {"key-rate", "how-scoring-works"}
    assert ranked[0].article.slug == "key-rate", "newer first"


def test_targeted_article_needs_a_match() -> None:
    articles = seeded_articles()
    slugs = {r.article.slug for r in rank_news(articles, profile_of("ivanov"), 50)}
    assert "horeca-low-season" not in slugs and "llc-registry-update" not in slugs


def test_ranking_is_deterministic_on_ties() -> None:
    same_day = NOW - timedelta(days=1)
    articles = [
        NewsArticle(uuid4(), slug, slug, "", same_day, okved_prefixes=("56",))
        for slug in ("b", "a", "c")
    ]
    ranked = rank_news(articles, profile_of("romashka"), 3)
    assert [r.article.slug for r in ranked] == ["a", "b", "c"]
    assert rank_news(list(reversed(articles)), profile_of("romashka"), 3) == ranked


def test_extra_okved_counts_less() -> None:
    article = NewsArticle(uuid4(), "it", "it", "", NOW, okved_prefixes=("62",))
    profile = CompanyProfile(okved_main="56.10", okved_extra=("62.01",))
    [ranked] = rank_news([article], profile, 5)
    assert ranked.relevance == ("доп. ОКВЭД 62 — разработка ПО",)
    assert ranked.score == 15


@pytest.mark.parametrize(
    "prefix,code,matches",
    [
        ("56", "56.10", True),
        ("56.1", "56.10", True),
        ("56.10", "56.10", True),
        ("56.2", "56.10", False),
        ("5", "56.10", False),
        ("62", "56.10", False),
    ],
)
def test_okved_prefix(prefix: str, code: str, matches: bool) -> None:
    assert okved_matches(prefix, code) is matches


def test_seed_has_enough_tagged_news() -> None:
    assert len(NEWS) >= 12
    assert len({n.slug for n in NEWS}) == len(NEWS)
    assert all(n.okved or n.products or n.legal_forms or n.general for n in NEWS)
