from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import DeclarativeBase

from src.core.access.access_context import AccessContext
from src.core.access.apply_helper import apply_policies
from src.core.access.dependencies import get_access_context_for, get_current_token
from src.core.access.organizations import MemberOrganizationsResolver
from src.core.access.permissions import Permissions
from src.core.exceptions.handlers import register_exception_handlers
from src.core.facades import FacadeRegistry
from src.core.infrastructure.database.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin
from src.core.schemas.jwt_dto import OpenSubTokenDTO


class _Base(DeclarativeBase):
    pass


class Application(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, _Base):
    __tablename__ = "applications_test"


class Plain(UUIDPrimaryKeyMixin, _Base):
    __tablename__ = "plain_org_test"


READ = Permissions.REQUESTS_READ
USER_ID = uuid4()
ORG_A, ORG_B = uuid4(), uuid4()
CLIENT_POLICIES = {READ.value: ["org_member"]}


def sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True})).replace("-", "")


def test_rows_of_member_organizations_only() -> None:
    stmt = apply_policies(
        select(Application),
        Application,
        READ,
        [READ.value],
        CLIENT_POLICIES,
        USER_ID,
        frozenset({ORG_A, ORG_B}),
    )
    compiled = sql(stmt)
    assert "applications_test.organization_id IN" in compiled
    assert ORG_A.hex in compiled and ORG_B.hex in compiled


def test_no_organizations_means_no_rows() -> None:
    stmt = apply_policies(
        select(Application), Application, READ, [READ.value], CLIENT_POLICIES, USER_ID, frozenset()
    )
    assert "false" in sql(stmt).lower() or "0 = 1" in sql(stmt)


def test_missing_organization_ids_fail_loud() -> None:
    with pytest.raises(ValueError, match="organization ids"):
        apply_policies(
            select(Application), Application, READ, [READ.value], CLIENT_POLICIES, USER_ID
        )


def test_model_without_organization_fails_loud() -> None:
    with pytest.raises(ValueError, match="does not support"):
        apply_policies(
            select(Plain), Plain, READ, [READ.value], CLIENT_POLICIES, USER_ID, frozenset({ORG_A})
        )


def test_admin_is_not_restricted() -> None:
    stmt = apply_policies(
        select(Application), Application, READ, [Permissions.ADMIN.value], CLIENT_POLICIES, USER_ID
    )
    assert "WHERE" not in sql(stmt)


# --- resolving organizations in the HTTP dependency ------------------------


class CountingResolver:
    def __init__(self, organizations: frozenset[UUID]) -> None:
        self.organizations = organizations
        self.calls = 0

    async def member_organization_ids(self, account_id: UUID) -> frozenset[UUID]:
        self.calls += 1
        return self.organizations


class _Sessions:
    """Stand-in session factory: the dependency only passes the session on."""

    def __call__(self) -> "_Sessions":
        return self

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        return None


@pytest.fixture
def resolver() -> CountingResolver:
    return CountingResolver(frozenset({ORG_A}))


@pytest.fixture
def token_holder() -> dict[str, OpenSubTokenDTO]:
    return {}


@pytest.fixture
def client(
    resolver: CountingResolver, token_holder: dict[str, OpenSubTokenDTO]
) -> Iterator[TestClient]:
    app = FastAPI()
    register_exception_handlers(app)
    app.state.facades = FacadeRegistry()
    app.state.facades.register(MemberOrganizationsResolver, lambda _session: resolver)
    app.state.session_factory = _Sessions()
    app.dependency_overrides[get_current_token] = lambda: token_holder["token"]

    @app.get("/items")
    async def items(
        access: Annotated[AccessContext, Depends(get_access_context_for(READ))],
    ) -> dict[str, object]:
        ids = access.organization_ids
        return {"organization_ids": None if ids is None else sorted(str(i) for i in ids)}

    with TestClient(app) as test_client:
        yield test_client


def token(permissions: list[str], policies: dict[str, list[str]]) -> OpenSubTokenDTO:
    now = datetime.now(UTC)
    return OpenSubTokenDTO(
        subject=USER_ID,
        permissions=permissions,
        policies=policies,
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def test_client_gets_organizations_resolved(
    client: TestClient, resolver: CountingResolver, token_holder: dict[str, OpenSubTokenDTO]
) -> None:
    token_holder["token"] = token([READ.value], CLIENT_POLICIES)
    response = client.get("/items")
    assert response.status_code == 200
    assert response.json() == {"organization_ids": [str(ORG_A)]}
    assert resolver.calls == 1


def test_underwriter_without_policy_skips_resolution(
    client: TestClient, resolver: CountingResolver, token_holder: dict[str, OpenSubTokenDTO]
) -> None:
    token_holder["token"] = token([READ.value], {})
    assert client.get("/items").json() == {"organization_ids": None}
    assert resolver.calls == 0


def test_admin_skips_resolution(
    client: TestClient, resolver: CountingResolver, token_holder: dict[str, OpenSubTokenDTO]
) -> None:
    token_holder["token"] = token([Permissions.ADMIN.value], CLIENT_POLICIES)
    assert client.get("/items").json() == {"organization_ids": None}
    assert resolver.calls == 0


def test_permission_is_still_required(
    client: TestClient, token_holder: dict[str, OpenSubTokenDTO]
) -> None:
    token_holder["token"] = token([Permissions.FEED_READ.value], {})
    assert client.get("/items").status_code == 403
