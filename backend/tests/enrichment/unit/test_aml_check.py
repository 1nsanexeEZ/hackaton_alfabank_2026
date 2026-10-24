"""Проверка по 115-ФЗ в снимке обогащения: бенефициары, перечни, ПДЛ, ЗСК — на каждой заявке.

Клиент, который уже получал кредит, проверяется так же, как новый: каждая команда обогащения
заново спрашивает ЕГРЮЛ, перечни, базу ПДЛ и ЗСК, прошлый результат не переиспользуется.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from src.core.domain.clock import FrozenClock
from src.core.messaging.contracts.enrichment import (
    EnrichmentCompleted,
    FetchEnrichment,
    PersonRef,
    ThirdPartyRef,
)
from src.modules.enrichment.application.dto.aml import (
    AmlCheckDTO,
    AmlSubjectDTO,
    BeneficialOwnerDTO,
)
from src.modules.enrichment.application.dto.registry import FounderDTO, RegistryExtractDTO
from src.modules.enrichment.application.use_cases.fetch_enrichment import FetchEnrichmentUseCase
from src.modules.enrichment.domain.exceptions import SourceNotFound, SourceUnavailable
from src.modules.enrichment.domain.snapshot import EnrichmentSnapshot
from src.modules.enrichment.infrastructure.repositories.serialization import (
    data_from_json,
    data_to_json,
)
from tests.enrichment.unit.test_fetch_enrichment import InMemoryRepo, sources
from tests.fakes.aml_sources import FakeAmlLists, FakePep, FakeZsk
from tests.fakes.messaging import FakeOutboxWriter

_INN = "7707115062"
_HOLDING = "7707115070"


def _extract(
    inn: str = _INN,
    *,
    founders: tuple[FounderDTO, ...] = (FounderDTO("Дочкин Дмитрий Данилович", Decimal(100)),),
    legal_form: str = "ООО",
    head: tuple[str, str, str | None] = ("Дочкин", "Дмитрий", "Данилович"),
) -> RegistryExtractDTO:
    return RegistryExtractDTO(
        inn=inn,
        ogrn="1",
        legal_form=legal_form,
        full_name=f"ООО {inn}",
        status="active",
        registered_at=date(2020, 1, 1),
        okved_main="46.90",
        okved_extra=(),
        head_last_name=head[0],
        head_first_name=head[1],
        head_middle_name=head[2],
        head_position="Генеральный директор",
        founders=founders,
        address="г. Москва",
        region_code="77",
        mass_address=False,
    )


class Registry:
    def __init__(self, *extracts: RegistryExtractDTO, fail: bool = False) -> None:
        self.extracts = {e.inn: e for e in extracts}
        self.fail = fail
        self.calls: list[str] = []

    async def fetch(self, inn: str) -> RegistryExtractDTO:
        self.calls.append(inn)
        if self.fail:
            raise SourceUnavailable("unavailable", "ЕГРЮЛ недоступен")
        if inn not in self.extracts:
            raise SourceNotFound()
        return self.extracts[inn]


def _command(representative: PersonRef | None = None) -> FetchEnrichment:
    return FetchEnrichment(
        application_id=uuid4(),
        organization_id=uuid4(),
        inn=_INN,
        sources=["egrul", "aml"],
        representative=representative,
    )


async def _run(
    command: FetchEnrichment | None = None, **fakes: object
) -> tuple[EnrichmentSnapshot, FakeOutboxWriter]:
    repo, outbox = InMemoryRepo(), FakeOutboxWriter()
    registry = fakes.pop("registry", Registry(_extract()))
    use_case = FetchEnrichmentUseCase(repo, sources(registry=registry, **fakes), FrozenClock())
    await use_case.execute(command or _command(), command_event_id=uuid4(), outbox=outbox)
    return repo.added[0], outbox


async def test_clean_company_is_checked() -> None:
    lists, pep, zsk = FakeAmlLists(), FakePep(), FakeZsk()
    snapshot, outbox = await _run(aml_lists=lists, pep=pep, zsk=zsk)

    check = snapshot.data_of("aml", AmlCheckDTO)
    assert check is not None
    assert check.list_hits == () and check.pep_hits == () and check.zsk.level == "low"
    assert check.beneficial_owners == (
        BeneficialOwnerDTO("Дочкин Дмитрий Данилович", "ownership", Decimal("100.00")),
    )
    assert [s.role for s in check.subjects] == ["company", "head"]
    assert "aml" in outbox.of_type(EnrichmentCompleted)[0].sources_ok
    assert zsk.calls == [_INN]


async def test_a_repeat_borrower_is_checked_again_on_every_application() -> None:
    """Повторная заявка того же клиента: перечни, ПДЛ, ЗСК и ЕГРЮЛ спрашиваются заново."""
    lists, pep, zsk = FakeAmlLists(), FakePep(), FakeZsk()
    registry = Registry(_extract())
    repo, outbox = InMemoryRepo(), FakeOutboxWriter()
    use_case = FetchEnrichmentUseCase(
        repo, sources(registry=registry, aml_lists=lists, pep=pep, zsk=zsk), FrozenClock()
    )

    await use_case.execute(_command(), command_event_id=uuid4(), outbox=outbox)
    # Клиента за это время включили в перечень — вторая заявка это видит.
    lists.listed["Дочкин Дмитрий Данилович"] = "freeze"
    await use_case.execute(_command(), command_event_id=uuid4(), outbox=outbox)

    assert len(lists.calls) == 2 and len(pep.calls) == 2 and zsk.calls == [_INN, _INN]
    assert registry.calls == [_INN, _INN]
    first, second = (s.data_of("aml", AmlCheckDTO) for s in repo.added)
    assert first is not None and first.list_hits == ()
    assert second is not None and [h.list for h in second.list_hits] == ["freeze"]


async def test_beneficial_owner_through_a_holding_is_screened() -> None:
    """Прямые учредители чистые, бенефициар (80% через холдинг) — в перечне ФРОМУ."""
    extract = _extract(
        founders=(
            FounderDTO("Дочкин Дмитрий Данилович", Decimal(20)),
            FounderDTO("ООО «Холдинг Восток»", Decimal(80), inn=_HOLDING),
        )
    )
    holding = _extract(
        _HOLDING,
        founders=(FounderDTO("Цепочкин Цезарь Цезаревич", Decimal(100)),),
        head=("Холдингов", "Харитон", "Харитонович"),
    )
    lists = FakeAmlLists({"Цепочкин Цезарь Цезаревич": "wmd"})
    snapshot, _ = await _run(registry=Registry(extract, holding), aml_lists=lists)

    check = snapshot.data_of("aml", AmlCheckDTO)
    assert check is not None
    assert check.beneficial_owners == (
        BeneficialOwnerDTO("Цепочкин Цезарь Цезаревич", "ownership", Decimal("80.00")),
    )
    assert AmlSubjectDTO("founder_company", f"ООО {_HOLDING}", _HOLDING) in check.subjects
    [hit] = check.list_hits
    assert (hit.subject.role, hit.subject.name, hit.list) == (
        "beneficial_owner",
        "Цепочкин Цезарь Цезаревич",
        "wmd",
    )


async def test_no_one_above_a_quarter_makes_the_head_the_owner() -> None:
    founders = tuple(FounderDTO(f"Партнёр № {i}", Decimal(20)) for i in range(5))
    snapshot, _ = await _run(registry=Registry(_extract(founders=founders)))
    check = snapshot.data_of("aml", AmlCheckDTO)
    assert check is not None
    assert check.beneficial_owners == (
        BeneficialOwnerDTO("Дочкин Дмитрий Данилович", "head_by_default"),
    )


async def test_representative_and_pep_are_screened() -> None:
    representative = PersonRef(
        account_id=uuid4(), last_name="Бухгалтерова", first_name="Вера", middle_name=None
    )
    pep = FakePep({"Бухгалтерова Вера": "foreign"})
    snapshot, _ = await _run(_command(representative), pep=pep)

    check = snapshot.data_of("aml", AmlCheckDTO)
    assert check is not None
    [hit] = check.pep_hits
    assert (hit.subject.role, hit.kind) == ("representative", "foreign")
    assert pep.calls == [("Дочкин Дмитрий Данилович", "Бухгалтерова Вера")]


async def test_listed_company_by_inn() -> None:
    snapshot, _ = await _run(aml_lists=FakeAmlLists({_INN: "terrorism"}))
    check = snapshot.data_of("aml", AmlCheckDTO)
    assert check is not None and check.list_hits[0].subject.role == "company"


async def test_registry_down_means_no_check() -> None:
    """Без ЕГРЮЛ не установить руководителя и бенефициаров — проверка не выполнена."""
    lists = FakeAmlLists()
    snapshot, outbox = await _run(registry=Registry(fail=True), aml_lists=lists)
    result = snapshot.results["aml"]
    assert result.status == "failed" and result.error is not None
    assert result.error.kind == "incomplete"
    assert lists.calls == []


async def test_unknown_company_in_the_chain_means_no_check() -> None:
    extract = _extract(founders=(FounderDTO("ООО «Нет»", Decimal(100), inn="7707000000"),))
    snapshot, outbox = await _run(registry=Registry(extract))
    assert snapshot.results["aml"].status == "failed"
    assert "aml" in outbox.of_type(EnrichmentCompleted)[0].sources_failed


async def test_any_screening_source_down_means_no_check() -> None:
    down: list[dict[str, object]] = [
        {"aml_lists": FakeAmlLists(fail=True)},
        {"pep": FakePep(fail=True)},
        {"zsk": FakeZsk(fail=True)},
    ]
    for fakes in down:
        snapshot, _ = await _run(**fakes)
        assert snapshot.results["aml"].status == "failed"
        assert snapshot.data_of("aml", AmlCheckDTO) is None


async def test_entrepreneur_is_the_beneficial_owner() -> None:
    extract = _extract(founders=(), legal_form="ИП", head=("Иванов", "Иван", "Иванович"))
    snapshot, _ = await _run(registry=Registry(extract))
    check = snapshot.data_of("aml", AmlCheckDTO)
    assert check is not None
    assert check.beneficial_owners == (BeneficialOwnerDTO("Иванов Иван Иванович", "entrepreneur"),)


async def test_check_survives_storage() -> None:
    founders = (
        FounderDTO("Дочкин Дмитрий Данилович", Decimal(20)),
        FounderDTO("ООО «Холдинг Восток»", Decimal(80), inn=_HOLDING),
    )
    holding = _extract(_HOLDING, founders=(FounderDTO("Цепочкин Цезарь Цезаревич", Decimal(100)),))
    snapshot, _ = await _run(
        registry=Registry(_extract(founders=founders), holding),
        aml_lists=FakeAmlLists({"Цепочкин Цезарь Цезаревич": "wmd"}),
        pep=FakePep({"Дочкин Дмитрий Данилович": "russian"}),
        zsk=FakeZsk("medium"),
    )
    check = snapshot.data_of("aml", AmlCheckDTO)
    assert check is not None
    assert data_from_json("aml", data_to_json("aml", check)) == check
    egrul = snapshot.data_of("egrul", RegistryExtractDTO)
    assert egrul is not None and data_from_json("egrul", data_to_json("egrul", egrul)) == egrul


async def test_beneficiary_and_pledgor_are_screened() -> None:
    """Выгодоприобретатель и залогодатель из заявки: организация — по ИНН, человек — по ФИО,
    в перечнях и в базе ПДЛ (115-ФЗ)."""
    command = FetchEnrichment(
        application_id=uuid4(),
        organization_id=uuid4(),
        inn=_INN,
        sources=["egrul", "aml"],
        third_parties=[
            ThirdPartyRef(
                role="beneficiary",
                kind="organization",
                name="ООО «Транзитный агент»",
                inn="7707115094",
            ),
            ThirdPartyRef(role="pledgor", kind="person", name="Посредников Павел Павлович"),
        ],
    )
    lists = FakeAmlLists({"7707115094": "freeze", "Посредников Павел Павлович": "terrorism"})
    pep = FakePep()
    snapshot, _ = await _run(command, aml_lists=lists, pep=pep)

    check = snapshot.data_of("aml", AmlCheckDTO)
    assert check is not None
    assert AmlSubjectDTO("beneficiary", "ООО «Транзитный агент»", "7707115094") in check.subjects
    assert AmlSubjectDTO("pledgor", "Посредников Павел Павлович") in check.subjects
    assert sorted((h.subject.role, h.list) for h in check.list_hits) == [
        ("beneficiary", "freeze"),
        ("pledgor", "terrorism"),
    ]
    # ПДЛ — только люди: организацию в базе ПДЛ не ищут.
    assert pep.calls == [("Дочкин Дмитрий Данилович", "Посредников Павел Павлович")]


async def test_third_parties_are_screened_on_every_application() -> None:
    lists = FakeAmlLists()
    registry = Registry(_extract())
    repo, outbox = InMemoryRepo(), FakeOutboxWriter()
    use_case = FetchEnrichmentUseCase(
        repo, sources(registry=registry, aml_lists=lists), FrozenClock()
    )
    party = ThirdPartyRef(role="beneficiary", kind="person", name="Агентов Аркадий")
    for _ in range(2):
        command = FetchEnrichment(
            application_id=uuid4(),
            organization_id=uuid4(),
            inn=_INN,
            sources=["egrul", "aml"],
            third_parties=[party],
        )
        await use_case.execute(command, command_event_id=uuid4(), outbox=outbox)
    assert [s[-1].role for s in lists.calls] == ["beneficiary", "beneficiary"]
