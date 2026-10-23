"""Сид decision на настоящем приложении: предодобрения демо-компаний считаются через настоящие
clients, products (eligibility) и scoring (estimate); повторный запуск даёт те же предложения."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from seed import decision as decision_seed
from seed.demo_data import COMPANIES_BY_CODE
from seed.run import SeedContext
from src.core.config import Settings
from src.core.domain.clock import FrozenClock
from src.main import create_app
from src.modules.clients.infrastructure.models import OrganizationModel
from src.modules.decision.facade import DecisionFacade, PreApprovedOfferDTO
from tests.decision.unit.decision_world import NOW
from tests.helpers import create_schema


@pytest.fixture(scope="module")
def seeded(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    folder: Path = tmp_path_factory.mktemp("decision-seed")
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{(folder / 'seed.db').as_posix()}",
        jwt_private_key_path=folder / "keys" / "private.pem",
        jwt_public_key_path=folder / "keys" / "public.pem",
        messaging_mode="manual",
        minio_ensure_bucket=False,
        seed_demo_data=True,
    )
    create_schema(settings.database_url)
    with TestClient(create_app(settings, clock=FrozenClock(NOW))) as client:
        yield client


def _offers(client: TestClient, code: str) -> dict[str, PreApprovedOfferDTO]:
    state: Any = client.app.state  # type: ignore[attr-defined]

    async def read() -> dict[str, PreApprovedOfferDTO]:
        async with state.session_factory() as session:
            stmt = select(OrganizationModel.id).where(
                OrganizationModel.inn == COMPANIES_BY_CODE[code].inn
            )
            organization_id = (await session.scalars(stmt)).one()
            offers = await state.facades.get(DecisionFacade, session).get_pre_approved(
                organization_id
            )
            return {offer.product_code: offer for offer in offers}

    return client.portal.call(read)  # type: ignore[union-attr]


def test_demo_companies_get_pre_approved_offers(seeded: TestClient) -> None:
    romashka = _offers(seeded, "romashka")

    assert "UNSECURED" in romashka
    assert all(offer.basis == "estimate" for offer in romashka.values())
    # «Закат» ликвидируется: предлагать нечего.
    assert _offers(seeded, "zakat") == {}


def test_seed_is_idempotent(seeded: TestClient) -> None:
    before = {code: _offers(seeded, code) for code in COMPANIES_BY_CODE}
    state: Any = seeded.app.state  # type: ignore[attr-defined]
    context = SeedContext(state.settings, state.session_factory, state.facades, FrozenClock(NOW))

    seeded.portal.call(decision_seed.seed, context)  # type: ignore[union-attr]

    assert {code: _offers(seeded, code) for code in COMPANIES_BY_CODE} == before
