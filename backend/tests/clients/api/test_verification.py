"""POST /organizations/{id}/verification and the auto check after enrichment."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI

from seed.clients import ADDRESSES
from seed.demo_data import COMPANIES_BY_CODE
from src.core.config import Settings
from src.core.exceptions.exceptions import InfrastructureError
from src.core.messaging.contracts.enrichment import EnrichmentCompleted
from src.core.messaging.outbox import build_envelope
from src.core.messaging.subscriber import MessageProcessor
from src.modules.clients import module as clients_module
from src.modules.enrichment.facade import (
    EnrichmentFacade,
    EnrichmentSnapshotDTO,
    RegistryExtractDTO,
    SourceErrorDTO,
)
from tests.clients.api.conftest import KUZNETSOVA, NOW, SMIRNOVA, Demo, start_demo
from tests.core.messaging.conftest import RecordingDeadLetters
from tests.fakes import install
from tests.fakes.enrichment_facade import FakeEnrichmentFacade

FULL_FORMS = {
    "LLC": "Общество с ограниченной ответственностью",
    "IE": "Индивидуальный предприниматель",
}


def registry_extract(code: str, **overrides: Any) -> RegistryExtractDTO:
    """What external-mocks answer: the full name, the head as in the seed."""
    company = COMPANIES_BY_CODE[code]
    head = company.registry_head
    short_form = "ИП" if company.legal_form == "IE" else "ООО"
    extract = RegistryExtractDTO(
        inn=company.inn,
        ogrn=company.ogrn,
        legal_form=short_form,
        full_name=company.name.replace(short_form, FULL_FORMS[company.legal_form], 1),
        status=company.registry_status,
        registered_at=date(2020, 10, 21),
        okved_main=company.okved_main,
        okved_extra=(),
        head_last_name=head.last_name,
        head_first_name=head.first_name,
        head_middle_name=head.middle_name,
        head_position="Генеральный директор",
        founders=(),
        address=ADDRESSES[code],
        region_code="77",
        mass_address=False,
        kpp=company.kpp,
    )
    return replace(extract, **overrides)


class Registry(FakeEnrichmentFacade):
    """The enrichment facade with a registry that may be down."""

    def __init__(self) -> None:
        super().__init__()
        self.down = False
        self.fresh: list[bool] = []

    async def lookup_registry(self, inn: str, *, fresh: bool = False) -> RegistryExtractDTO | None:
        self.fresh.append(fresh)
        if self.down:
            raise InfrastructureError("Реестр временно недоступен")
        return await super().lookup_registry(inn, fresh=fresh)


@pytest.fixture
def registry() -> Registry:
    registry = Registry()
    for code in COMPANIES_BY_CODE:
        registry.add_registry_extract(registry_extract(code))
    return registry


@pytest.fixture
def demo(settings: Settings, registry: Registry) -> Iterator[Demo]:
    def configure(app: FastAPI) -> None:
        install(app, EnrichmentFacade, registry)

    with start_demo(settings, configure) as value:
        yield value


def verify(demo: Demo, code: str, headers: dict[str, str]) -> Any:
    return demo.client.post(f"/organizations/{demo.orgs[code]}/verification", headers=headers)


def card(demo: Demo, code: str) -> dict[str, Any]:
    return demo.client.get(f"/organizations/{demo.orgs[code]}", headers=demo.as_admin()).json()


# --- on request ---------------------------------------------------------------


def test_same_data_is_verified(demo: Demo, registry: Registry) -> None:
    version = card(demo, "romashka")["version"]

    response = verify(demo, "romashka", demo.as_client(SMIRNOVA))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["updated_fields"] == [] and body["discrepancies"] == []
    organization = body["organization"]
    assert organization["name"] == "ООО «Ромашка»"
    assert organization["verification"] == {
        "status": "verified",
        "checked_at": NOW.isoformat().replace("+00:00", "Z"),
        "discrepancies": [],
    }
    assert organization["version"] == version + 1
    assert organization["my_role"] == "director"
    assert registry.fresh == [True]
    [record] = demo.outbox()
    assert record.message_type == "OrganizationVerified"
    assert record.key == str(demo.orgs["romashka"])


def test_changed_card_follows_the_registry(demo: Demo, registry: Registry) -> None:
    registry.add_registry_extract(
        registry_extract(
            "romashka",
            address="г. Москва, ул. Тверская, д. 1",
            okved_extra=("56.29",),
            kpp="770143001",
            status="liquidating",
        )
    )

    response = verify(demo, "romashka", demo.as_client(KUZNETSOVA))

    assert response.status_code == 200, response.text
    assert response.json()["updated_fields"] == [
        {
            "field": "address.full",
            "before": "г. Москва, ул. Тверская, д. 12, стр. 1",
            "after": "г. Москва, ул. Тверская, д. 1",
        },
        {"field": "kpp", "before": "770101001", "after": "770143001"},
        {"field": "okved_extra", "before": None, "after": "56.29"},
        {"field": "registry_status", "before": "active", "after": "liquidating"},
    ]
    stored = card(demo, "romashka")
    assert stored["address"]["full"] == "г. Москва, ул. Тверская, д. 1"
    assert stored["kpp"] == "770143001" and stored["okved_extra"] == ["56.29"]
    assert stored["registry_status"] == "liquidating"
    assert stored["inn"] == "7701158817" and stored["ogrn"] == "1027700399869"
    assert stored["verification"]["status"] == "verified"


def test_underwriter_finds_the_head_mismatch(demo: Demo) -> None:
    response = verify(demo, "vector", demo.as_underwriter())

    assert response.status_code == 200, response.text
    body = response.json()
    mismatch = {"field": "head_name", "declared": "Петров П. П.", "registry": "Сидоров С. С."}
    assert body["discrepancies"] == [mismatch]
    assert body["organization"]["verification"]["status"] == "mismatch"
    assert body["organization"]["head_name"] == "Сидоров Сергей Сергеевич"
    assert body["organization"]["my_role"] is None
    [record] = demo.outbox()
    assert record.message_type == "OrganizationVerificationMismatch"
    assert record.envelope["payload"]["discrepancies"] == [mismatch]


def test_new_head_in_the_registry_is_not_taken_silently(demo: Demo, registry: Registry) -> None:
    registry.add_registry_extract(
        registry_extract("romashka", head_last_name="Новикова", head_first_name="Нина")
    )

    body = verify(demo, "romashka", demo.as_client(SMIRNOVA)).json()

    assert body["discrepancies"] == [
        {"field": "head_name", "declared": "Смирнова А. С.", "registry": "Новикова Н. С."}
    ]
    stored = card(demo, "romashka")
    assert stored["head_name"] == "Смирнова Анна Сергеевна"
    assert stored["verification"]["status"] == "mismatch"


def test_somebody_elses_company_is_not_found(demo: Demo, registry: Registry) -> None:
    headers = demo.as_client(SMIRNOVA)
    stranger = verify(demo, "vector", headers)
    assert stranger.status_code == 404 and stranger.json()["code"] == "not_found"
    missing = demo.client.post(f"/organizations/{uuid4()}/verification", headers=headers)
    assert missing.status_code == 404
    assert registry.fresh == [] and demo.outbox() == []


def test_unknown_inn_in_the_registry(demo: Demo, registry: Registry) -> None:
    del registry.registry[COMPANIES_BY_CODE["romashka"].inn]

    response = verify(demo, "romashka", demo.as_client(SMIRNOVA))

    assert response.status_code == 422
    assert response.json()["details"]["code"] == "registry_not_found"
    assert card(demo, "romashka")["verification"]["status"] == "verified"
    assert demo.outbox() == []


def test_registry_down_changes_nothing(demo: Demo, registry: Registry) -> None:
    before = card(demo, "vector")
    registry.down = True

    response = verify(demo, "vector", demo.as_underwriter())

    assert response.status_code == 503
    assert response.json()["code"] == "unavailable"
    assert card(demo, "vector") == before
    assert demo.outbox() == []


def test_underwriter_changes_nothing_else(demo: Demo) -> None:
    response = demo.client.post(
        f"/organizations/{demo.orgs['vector']}/members",
        json={"login": KUZNETSOVA, "role": "employee"},
        headers=demo.as_underwriter(),
    )
    assert response.status_code == 403
    assert response.json()["details"]["code"] == "not_a_member"


# --- pre-approval -------------------------------------------------------------


def test_mismatch_recalculates_the_pre_approval(demo: Demo) -> None:
    verify(demo, "vector", demo.as_underwriter())
    [mismatch] = demo.outbox()

    demo.run(demo.app.state.messaging.drain)

    updated = [r for r in demo.outbox() if r.message_type == "PreApprovedOffersUpdated"]
    assert [r.envelope["causation_id"] for r in updated] == [str(mismatch.event_id)]
    assert updated[0].key == str(demo.orgs["vector"])


# --- auto check after enrichment ----------------------------------------------


def snapshot(demo: Demo, code: str, egrul: RegistryExtractDTO | None) -> EnrichmentSnapshotDTO:
    return EnrichmentSnapshotDTO(
        id=uuid4(),
        application_id=uuid4(),
        organization_id=demo.orgs[code],
        collected_at=NOW,
        sources_ok=("egrul",) if egrul else (),
        sources_failed=()
        if egrul
        else (SourceErrorDTO(source="egrul", code="unavailable", message="Реестр не ответил"),),
        egrul=egrul,
        fns=None,
        bki=None,
        cashflow=None,
    )


def deliver(demo: Demo, application_id: UUID, event_id: UUID | None = None) -> str:
    """EnrichmentCompleted through the real processor: inbox, transaction, retries."""
    [subscription] = clients_module.subscribers()
    message = EnrichmentCompleted(application_id=application_id, snapshot_id=uuid4())
    envelope = build_envelope(
        message,
        producer="enrichment",
        occurred_at=NOW,
        correlation_id=application_id,
        event_id=event_id,
    ).model_dump(mode="json")
    processor = MessageProcessor(
        demo.app.state.session_factory,
        demo.app.state.facades,
        demo.clock,
        RecordingDeadLetters(),
        backoff_seconds=(0.0,),
    )
    return demo.run(processor.process, subscription, envelope)


def test_auto_check_follows_the_extract_of_the_application(demo: Demo, registry: Registry) -> None:
    moved = registry_extract("romashka", address="г. Москва, ул. Тверская, д. 1")
    taken = registry.add_snapshot(snapshot(demo, "romashka", moved))
    event_id = uuid4()

    assert deliver(demo, taken.application_id, event_id) == "processed"

    assert card(demo, "romashka")["address"]["full"] == "г. Москва, ул. Тверская, д. 1"
    [record] = demo.outbox()
    assert record.message_type == "OrganizationVerified"
    assert record.envelope["causation_id"] == str(event_id)
    assert record.envelope["correlation_id"] == str(taken.application_id)
    # The registry itself is not asked: the extract came with the snapshot.
    assert registry.fresh == []
    # The same message again is a duplicate (inbox).
    assert deliver(demo, taken.application_id, event_id) == "duplicate"
    assert len(demo.outbox()) == 1


def test_auto_check_skips_a_snapshot_without_the_registry(demo: Demo, registry: Registry) -> None:
    before = card(demo, "vector")
    failed = registry.add_snapshot(snapshot(demo, "vector", None))

    assert deliver(demo, failed.application_id) == "processed"
    assert deliver(demo, uuid4()) == "processed"

    assert card(demo, "vector") == before
    assert demo.outbox() == []


def test_auto_check_ignores_an_extract_of_another_company(demo: Demo, registry: Registry) -> None:
    foreign = registry.add_snapshot(snapshot(demo, "romashka", registry_extract("vector")))

    assert deliver(demo, foreign.application_id) == "processed"

    assert demo.outbox() == []
