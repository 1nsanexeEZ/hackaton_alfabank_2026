"""The registry extract of enrichment as clients value objects."""

from dataclasses import replace
from datetime import date

import pytest

from src.core.exceptions.exceptions import InfrastructureError
from src.modules.clients.domain.value_objects import Kpp, PersonName, RegistryStatus
from src.modules.clients.infrastructure.registry import extract_of, short_name
from src.modules.enrichment.facade import RegistryExtractDTO

DTO = RegistryExtractDTO(
    inn="7701158817",
    ogrn="1027700399869",
    legal_form="ООО",
    full_name="Общество с ограниченной ответственностью «Ромашка»",
    status="active",
    registered_at=date(2020, 10, 21),
    okved_main="56.10",
    okved_extra=("56.29",),
    head_last_name="Смирнова",
    head_first_name="Анна",
    head_middle_name="Сергеевна",
    head_position="Генеральный директор",
    founders=(),
    address="г. Москва, ул. Тверская, д. 1",
    region_code="77",
    mass_address=False,
    kpp="770101001",
)


@pytest.mark.parametrize(
    ("full", "short"),
    [
        ("Общество с ограниченной ответственностью «Ромашка»", "ООО «Ромашка»"),
        ("ОБЩЕСТВО С ОГРАНИЧЕННОЙ  ОТВЕТСТВЕННОСТЬЮ «ВЕКТОР»", "ООО «ВЕКТОР»"),
        ("Публичное акционерное общество «Банк»", "ПАО «Банк»"),
        ("Акционерное общество «Завод»", "АО «Завод»"),
        ("Индивидуальный предприниматель Иванов Иван Иванович", "ИП Иванов Иван Иванович"),
        ("ООО «Ромашка»", "ООО «Ромашка»"),
    ],
)
def test_short_name(full: str, short: str) -> None:
    assert short_name(full) == short


def test_extract_in_value_objects() -> None:
    extract = extract_of(DTO)
    assert extract.name == "ООО «Ромашка»"
    assert extract.kpp == Kpp("770101001")
    assert extract.status is RegistryStatus.ACTIVE
    assert extract.head == PersonName("Смирнова", "Анна", "Сергеевна")
    assert [code.value for code in extract.okved_extra] == ["56.29"]
    assert extract_of(replace(DTO, kpp=None)).kpp is None


@pytest.mark.parametrize(
    "broken",
    [
        {"okved_main": "6"},
        {"status": "dissolved"},
        {"head_last_name": ""},
        {"region_code": "Москва"},
    ],
)
def test_unreadable_extract_is_the_registry_fault(broken: dict[str, str]) -> None:
    with pytest.raises(InfrastructureError) as error:
        extract_of(replace(DTO, **broken))  # type: ignore[arg-type]
    assert error.value.details is not None
    assert error.value.details["code"] == "bad_registry_data"
