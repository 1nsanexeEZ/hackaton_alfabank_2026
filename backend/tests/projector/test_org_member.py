"""The overview table carries organization_id: the `org_member` policy works on it."""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.access.apply_helper import apply_policies
from src.core.access.permissions import Permissions
from src.core.infrastructure.database.mixins import OrganizationOwnedMixin
from src.modules.projector.infrastructure.database.models import ApplicationOverviewRow
from tests.projector.unit.factories import overview
from tests.projector.world import OpenStore

READ = Permissions.REQUESTS_READ
CLIENT_POLICIES = {READ.value: ["org_member"]}
ROMASHKA, VECTOR, IVANOV = uuid4(), uuid4(), uuid4()


async def visible(
    session_factory: async_sessionmaker[AsyncSession],
    granted: list[str],
    organization_ids: frozenset | None,
) -> set:
    stmt = apply_policies(
        select(ApplicationOverviewRow),
        ApplicationOverviewRow,
        READ,
        granted,
        CLIENT_POLICIES,
        uuid4(),
        organization_ids,
    )
    async with session_factory() as session:
        return {row.organization_id for row in (await session.scalars(stmt)).all()}


async def test_client_sees_only_companies_he_is_a_member_of(
    store: OpenStore, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    assert issubclass(ApplicationOverviewRow, OrganizationOwnedMixin)
    async with store() as s:
        for organization_id in (ROMASHKA, VECTOR, IVANOV, ROMASHKA):
            await s.save_overview(overview(organization_id=organization_id))

    # director of Romashka
    assert await visible(session_factory, [READ.value], frozenset({ROMASHKA})) == {ROMASHKA}
    # the accountant works for Romashka and the sole proprietor Ivanov
    accountant = await visible(session_factory, [READ.value], frozenset({ROMASHKA, IVANOV}))
    assert accountant == {ROMASHKA, IVANOV}
    # a member of no company sees nothing
    assert await visible(session_factory, [READ.value], frozenset()) == set()
    # admin is not restricted
    admin = await visible(session_factory, [Permissions.ADMIN.value], None)
    assert admin == {ROMASHKA, VECTOR, IVANOV}
