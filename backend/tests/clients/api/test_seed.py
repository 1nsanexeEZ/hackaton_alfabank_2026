import logging
from collections import Counter

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from seed import clients as clients_seed
from seed.demo_data import ACCOUNTS, ACCOUNTS_BY_EMAIL, COMPANIES
from seed.run import SeedContext
from src.core.config import Settings
from src.core.domain.clock import FrozenClock
from src.core.facades import FacadeRegistry
from src.core.messaging.outbox import OutboxRecord
from src.modules.clients.infrastructure.models import (
    FinancialReportModel,
    MemberModel,
    OrganizationModel,
)
from src.modules.clients.infrastructure.repositories import SqlAlchemyOrganizationRepository
from src.modules.identity.facade import IdentityFacade
from tests.clients.api.conftest import NOW, add_demo_account
from tests.fakes import builders
from tests.fakes.identity_facade import FakeIdentityFacade

Sessions = async_sessionmaker[AsyncSession]
KUZNETSOVA = "accountant@romashka.test"


def context(sessions: Sessions, identity: FakeIdentityFacade | None) -> SeedContext:
    registry = FacadeRegistry()
    if identity is not None:
        registry.register(IdentityFacade, lambda _session: identity)
    return SeedContext(Settings(_env_file=None), sessions, registry, FrozenClock(NOW))


async def counts(sessions: Sessions) -> dict[str, int]:
    async with sessions() as session:
        return {
            model.__tablename__: await session.scalar(select(func.count()).select_from(model))
            for model in (OrganizationModel, MemberModel, FinancialReportModel, OutboxRecord)
        }


def demo_identity(skip: str | None = None) -> FakeIdentityFacade:
    identity = FakeIdentityFacade()
    for account in ACCOUNTS:
        if account.email != skip:
            add_demo_account(identity, account)
    return identity


async def test_seed_is_idempotent(session_factory: Sessions) -> None:
    seed_context = context(session_factory, demo_identity())
    await clients_seed.seed(seed_context)
    first = await counts(session_factory)
    await clients_seed.seed(seed_context)

    assert (
        await counts(session_factory)
        == first
        == {
            "clients_organizations": 6,
            "clients_members": 8,
            # last year for every company, the year before for all but Ivanov
            "clients_financial_reports": 11,
            # the initial state publishes nothing
            "core_outbox": 0,
        }
    )


async def test_seed_follows_demo_data(session_factory: Sessions) -> None:
    identity = demo_identity()
    await clients_seed.seed(context(session_factory, identity))
    by_email = {a.email: a for a in identity.accounts.values()}

    async with session_factory() as session:
        repository = SqlAlchemyOrganizationRepository(session)
        for company in COMPANIES:
            org = await repository.get_by_inn(company.inn)
            assert org is not None
            assert org.name == company.name and org.okved_main.value == company.okved_main
            assert org.registry_status.value == company.registry_status
            assert org.business_age_months(NOW) == company.registered_months_ago
            assert org.address.region_code == "77"
            assert org.tax_regime.value == ("usn" if company.legal_form == "IE" else "osn")
            expected = builders.organization_snapshot(company.code)
            assert org.verification.status.value == expected.verification_status
            for account in ACCOUNTS:
                for membership in account.memberships:
                    if membership.company_code != company.code:
                        continue
                    member = org.member(by_email[account.email].id)
                    assert member.role.value == membership.role
                    assert member.authority.value == membership.authority, account.email

    roles = Counter(m.role for a in ACCOUNTS for m in a.memberships)
    assert roles == {"director": 5, "accountant": 2, "owner": 1}


async def test_missing_account_is_skipped_without_personal_data(
    session_factory: Sessions, caplog: pytest.LogCaptureFixture
) -> None:
    identity = demo_identity(skip=KUZNETSOVA)
    with caplog.at_level(logging.WARNING, logger="seed.clients"):
        await clients_seed.seed(context(session_factory, identity))
    assert (await counts(session_factory))["clients_members"] == 6
    assert "accountant" in caplog.text
    assert "@" not in caplog.text and "Кузнецова" not in caplog.text

    # Once identity has the account, the next run completes the companies.
    add_demo_account(identity, ACCOUNTS_BY_EMAIL[KUZNETSOVA])
    await clients_seed.seed(context(session_factory, identity))
    assert (await counts(session_factory))["clients_members"] == 8


async def test_seed_without_identity_creates_companies(session_factory: Sessions) -> None:
    await clients_seed.seed(context(session_factory, None))
    assert await counts(session_factory) == {
        "clients_organizations": 6,
        "clients_members": 0,
        "clients_financial_reports": 11,
        "core_outbox": 0,
    }


def test_months_ago_keeps_the_calendar() -> None:
    from datetime import date

    assert clients_seed.months_ago(date(2026, 10, 21), 72) == date(2020, 10, 21)
    assert clients_seed.months_ago(date(2026, 3, 31), 1) == date(2026, 2, 28)
    assert clients_seed.months_ago(date(2026, 1, 15), 13) == date(2024, 12, 15)
