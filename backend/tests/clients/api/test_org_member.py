"""The `org_member` port on the real clients implementation: rows of another
module (here — an OrganizationOwnedMixin table of clients itself, read under
`requests.read` as the applications module does) are narrowed to the companies
of the caller."""

from collections.abc import Iterator
from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import select

from src.clients.infrastructure.models import FinancialReportModel
from src.core.access.access_context import AccessContext
from src.core.access.apply_helper import apply_access_context
from src.core.access.dependencies import get_access_context_for
from src.core.access.permissions import Permissions
from src.core.config import Settings
from src.core.infrastructure.database.session import DbSession
from tests.clients.api.conftest import IVANOV, KUZNETSOVA, PETROV, SMIRNOVA, Demo, start_demo


def add_probe(app: FastAPI) -> None:
    @app.get("/probe/rows")
    async def rows(
        access: Annotated[
            AccessContext, Depends(get_access_context_for(Permissions.REQUESTS_READ))
        ],
        session: DbSession,
    ) -> dict[str, Any]:
        stmt = apply_access_context(
            select(FinancialReportModel.organization_id), FinancialReportModel, access
        )
        ids = access.organization_ids
        return {
            "resolved": None if ids is None else sorted(str(i) for i in ids),
            "rows": sorted({str(i) for i in (await session.scalars(stmt)).all()}),
        }


@pytest.fixture
def probe(settings: Settings) -> Iterator[Demo]:
    with start_demo(settings, add_probe) as demo:
        yield demo


def visible(demo: Demo, email: str) -> set[str]:
    response = demo.client.get("/probe/rows", headers=demo.as_client(email))
    assert response.status_code == 200
    body = response.json()
    assert set(body["rows"]) <= set(body["resolved"])
    return set(body["rows"])


def ids(demo: Demo, *codes: str) -> set[str]:
    return {str(demo.orgs[code]) for code in codes}


def test_romashka_client_sees_romashka_rows_only(probe: Demo) -> None:
    assert visible(probe, SMIRNOVA) == ids(probe, "romashka")
    assert str(probe.orgs["vector"]) not in visible(probe, SMIRNOVA)


def test_accountant_sees_romashka_and_ivanov(probe: Demo) -> None:
    assert visible(probe, KUZNETSOVA) == ids(probe, "romashka", "ivanov")
    assert visible(probe, IVANOV) == ids(probe, "ivanov")
    assert visible(probe, PETROV) == ids(probe, "vector")


def test_underwriter_is_not_narrowed(probe: Demo) -> None:
    body = probe.client.get("/probe/rows", headers=probe.as_underwriter()).json()
    assert body["resolved"] is None
    assert set(body["rows"]) == ids(probe, *probe.orgs)
