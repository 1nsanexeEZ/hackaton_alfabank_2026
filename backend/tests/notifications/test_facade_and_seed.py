from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from seed.notifications import NEWS, news_id
from seed.notifications import seed as seed_news
from seed.run import SeedContext
from src.core.config import Settings
from src.core.domain.clock import FrozenClock
from src.core.facades import FacadeRegistry
from src.core.messaging.contracts import CONTRACTS
from src.core.messaging.runtime import validate_subscriptions
from src.modules.notifications import module
from src.modules.notifications.domain.feed import UNDERWRITERS, Delivery, FeedEntry, Recipient
from src.modules.notifications.infrastructure.database.models import NewsItem
from src.modules.notifications.infrastructure.repositories.feed import SqlAlchemyFeedStore
from src.modules.notifications.presentation.dependencies import notifications_facade
from tests.notifications.conftest import World


def seed_context(
    session_factory: async_sessionmaker[AsyncSession], clock: FrozenClock
) -> SeedContext:
    return SeedContext(Settings(_env_file=None), session_factory, FacadeRegistry(), clock)


async def test_seed_is_idempotent(
    session_factory: async_sessionmaker[AsyncSession], clock: FrozenClock
) -> None:
    await seed_news(seed_context(session_factory, clock))
    async with session_factory() as session:
        first = {row.slug: row.published_at for row in (await session.scalars(select(NewsItem)))}

    clock.advance(timedelta(days=3))
    await seed_news(seed_context(session_factory, clock))
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(NewsItem))
        rows = (await session.scalars(select(NewsItem))).all()

    assert count == len(NEWS) >= 12
    assert {row.id for row in rows} == {news_id(n.slug) for n in NEWS}
    assert {row.slug: row.published_at for row in rows} == first, "publication date is kept"


async def test_facade_reads_the_feed_of_an_account(
    session_factory: async_sessionmaker[AsyncSession],
    registry: FacadeRegistry,
    world: World,
    clock: FrozenClock,
) -> None:
    underwriter = world.identity.add_account(email="u@bank.test", role_name="underwriter")
    async with session_factory() as session:
        store = SqlAlchemyFeedStore(session)
        own = FeedEntry(
            type="status_changed",
            audience="client",
            title="своя",
            body="",
            organization_id=world.romashka.id,
            application_id=world.card.id,
        )
        other = FeedEntry(
            type="status_changed",
            audience="client",
            title="Иванов",
            body="",
            organization_id=world.ivanov.id,
        )
        bank = FeedEntry(type="task_assigned", audience="bank", title="задача", body="")
        await store.append(
            Delivery(own, (Recipient.account(world.director),)), uuid4(), "T", clock.now()
        )
        await store.append(
            Delivery(other, (Recipient.account(world.accountant),)), uuid4(), "T", clock.now()
        )
        await store.append(Delivery(bank, (UNDERWRITERS,)), uuid4(), "T", clock.now())
        await session.commit()

    await seed_news(seed_context(session_factory, clock))
    async with session_factory() as session:
        facade = notifications_facade(session, registry, clock)
        assert await facade.unread_count(world.director) == 1
        assert await facade.unread_count(world.director, world.ivanov.id) == 0
        assert [i.title for i in await facade.latest(world.director, world.romashka.id)] == ["своя"]
        assert [i.title for i in await facade.latest(world.director, application_id=uuid4())] == []
        assert [i.title for i in await facade.latest(underwriter.id)] == ["задача"]
        assert await facade.unread_count(world.stranger) == 0

        news = await facade.personal_news(world.romashka.id, limit=3)
        assert [n.relevance[0] for n in news] == [
            "ОКВЭД 56.10 — общепит",
            "ОКВЭД 56 — общепит",
            "ОКВЭД 56 — общепит",
        ]
        ivanov_news = await facade.personal_news(world.ivanov.id, limit=3)
        assert {n.id for n in news}.isdisjoint({n.id for n in ivanov_news})


async def test_facade_without_identity_shows_own_records_only(
    session_factory: async_sessionmaker[AsyncSession], clock: FrozenClock
) -> None:
    account = uuid4()
    async with session_factory() as session:
        entry = FeedEntry(type="task_assigned", audience="bank", title="задача", body="")
        await SqlAlchemyFeedStore(session).append(
            Delivery(entry, (UNDERWRITERS,)), uuid4(), "T", clock.now()
        )
        await session.commit()
    async with session_factory() as session:
        facade = notifications_facade(session, FacadeRegistry(), clock)
        assert await facade.latest(account) == []
        assert await facade.personal_news(uuid4()) == [], "unknown company and no news seeded"


def test_subscriptions_cover_the_five_source_topics() -> None:
    subscriptions = module.subscribers()
    validate_subscriptions(subscriptions)
    assert {s.topic for s in subscriptions} == {
        "applications.events",
        "process.events",
        "decision.events",
        "clients.events",
        "support.events",
    }
    assert {s.group_id for s in subscriptions} == {
        "notifications.feed.applications",
        "notifications.feed.process",
        "notifications.feed.decision",
        "notifications.feed.clients",
        "notifications.feed.support",
    }
    for subscription in subscriptions:
        assert subscription.message_types, subscription.topic
        for message_type in subscription.message_types:
            assert CONTRACTS[message_type].TOPIC == subscription.topic
