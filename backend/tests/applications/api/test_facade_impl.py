"""The facade other modules read through, on the real database."""

from decimal import Decimal
from uuid import UUID

import pytest

from src.core.exceptions.exceptions import ConflictError
from src.modules.applications.facade import ApplicationsFacade
from tests.applications.api.conftest import World


def facade_call(world: World, method: str, *args: object) -> object:
    async def call() -> object:
        app = world.client.app
        async with app.state.session_factory() as session:  # type: ignore[attr-defined]
            facade = app.state.facades.get(ApplicationsFacade, session)  # type: ignore[attr-defined]
            return await getattr(facade, method)(*args)

    return world.run(call)


def test_card_and_scoring_input(world: World) -> None:
    application = world.submit(world.ready())
    application_id = UUID(application["id"])

    card = facade_call(world, "get_card", application_id)
    assert card.status == "submitted"  # type: ignore[attr-defined]
    assert card.org_snapshot.inn == "7701158817"  # type: ignore[attr-defined]
    assert card.org_snapshot.financial_reports[0].revenue == Decimal("48000000")  # type: ignore[attr-defined]
    assert card.request.amount == Decimal("3000000.00")  # type: ignore[attr-defined]

    scoring = facade_call(world, "get_scoring_input", application_id)
    statement_id = UUID(application["documents"][0]["id"])
    assert scoring.statement_document_ids == (statement_id,)  # type: ignore[attr-defined]
    assert scoring.product_terms.code == "UNSECURED"  # type: ignore[attr-defined]
    assert scoring.credit_bureau_consent_at is not None  # type: ignore[attr-defined]

    content = facade_call(world, "read_document", application_id, statement_id)
    assert content.startswith(b"date;amount")  # type: ignore[attr-defined]
    statements = facade_call(world, "list_documents", application_id, "bank_statement")
    assert [d.id for d in statements] == [statement_id]  # type: ignore[attr-defined]


def test_draft_has_no_scoring_input(world: World) -> None:
    application = world.create()
    with pytest.raises(ConflictError):
        facade_call(world, "get_scoring_input", UUID(application["id"]))
    card = facade_call(world, "get_card", UUID(application["id"]))
    assert card.request is None and card.org_snapshot is None  # type: ignore[attr-defined]


def test_completeness_for_the_process(world: World) -> None:
    draft = world.create()
    missing = facade_call(world, "get_completeness", UUID(draft["id"]))
    assert missing.complete is False  # type: ignore[attr-defined]
    assert missing.missing_documents == ("bank_statement",)  # type: ignore[attr-defined]
    assert "request.amount" in missing.missing_fields  # type: ignore[attr-defined]

    world.client.post(f"/applications/{draft['id']}/cancel", headers=world.headers(world.director))
    ready = world.submit(world.ready())
    complete = facade_call(world, "get_completeness", UUID(ready["id"]))
    assert complete.complete is True  # type: ignore[attr-defined]


def test_list_for_organization(world: World) -> None:
    active = world.create()
    cancelled = world.create(product_code="OVERDRAFT")
    world.client.post(
        f"/applications/{cancelled['id']}/cancel", headers=world.headers(world.director)
    )

    everything = facade_call(world, "list_for_organization", world.romashka, False)
    assert {a.id for a in everything} == {UUID(active["id"]), UUID(cancelled["id"])}  # type: ignore[attr-defined]
    only_active = facade_call(world, "list_for_organization", world.romashka, True)
    assert [a.id for a in only_active] == [UUID(active["id"])]  # type: ignore[attr-defined]
