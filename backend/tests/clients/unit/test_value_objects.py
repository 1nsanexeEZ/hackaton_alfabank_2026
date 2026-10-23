from datetime import UTC, date, datetime, timedelta

import pytest

from seed.demo_data import COMPANIES, DemoCompany
from src.core.exceptions.exceptions import ValidationError
from src.modules.clients.domain.enums import LegalForm, VerificationStatus
from src.modules.clients.domain.value_objects import (
    Address,
    Discrepancy,
    FiscalPeriod,
    Inn,
    Kpp,
    Ogrn,
    OkvedCode,
    PersonName,
    Requisites,
    VerificationResult,
)

ROMASHKA = next(c for c in COMPANIES if c.code == "romashka")
IVANOV = next(c for c in COMPANIES if c.code == "ivanov")


def code_of(error: pytest.ExceptionInfo[ValidationError]) -> tuple[str, str]:
    assert error.value.details is not None
    return error.value.details["field"], error.value.details["code"]


def spoil(value: str, position: int) -> str:
    digit = (int(value[position]) + 1) % 10
    return value[:position] + str(digit) + value[position + 1 :]


# --- requisites of the demo companies ----------------------------------------


@pytest.mark.parametrize("company", COMPANIES, ids=[c.code for c in COMPANIES])
def test_demo_requisites_are_valid(company: DemoCompany) -> None:
    requisites = Requisites.of(company.inn, company.ogrn, company.legal_form, company.kpp)
    assert requisites.legal_form is LegalForm(company.legal_form)
    assert requisites.inn.is_entrepreneur == requisites.ogrn.is_entrepreneur
    assert requisites.inn.is_entrepreneur == (company.legal_form == "IE")
    assert (requisites.kpp is None) == (company.legal_form == "IE")


@pytest.mark.parametrize("company", COMPANIES, ids=[c.code for c in COMPANIES])
def test_spoiled_inn_check_digit_is_rejected(company: DemoCompany) -> None:
    # Both check digits of a 12-digit INN are verified.
    positions = (-1,) if len(company.inn) == 10 else (-2, -1)
    for position in positions:
        with pytest.raises(ValidationError) as error:
            Inn(spoil(company.inn, len(company.inn) + position))
        assert code_of(error) == ("inn", "bad_checksum")


@pytest.mark.parametrize("company", COMPANIES, ids=[c.code for c in COMPANIES])
def test_spoiled_ogrn_check_digit_is_rejected(company: DemoCompany) -> None:
    with pytest.raises(ValidationError) as error:
        Ogrn(spoil(company.ogrn, len(company.ogrn) - 1))
    assert code_of(error) == ("ogrn", "bad_checksum")


@pytest.mark.parametrize(
    "value", ["", "770115881", "77011588170", "770115881a", "７７０１１５８８１７"]
)
def test_inn_format(value: str) -> None:
    with pytest.raises(ValidationError) as error:
        Inn(value)
    assert code_of(error) == ("inn", "bad_format")


@pytest.mark.parametrize(
    "value",
    [
        "102770039986",  # 12 digits
        "2027700399869",  # 13 digits, but not 1 or 5 first
        "125770689768464",  # 15 digits, but not 3 first
        "10277003998a9",
    ],
)
def test_ogrn_format(value: str) -> None:
    with pytest.raises(ValidationError) as error:
        Ogrn(value)
    assert code_of(error) == ("ogrn", "bad_format")


def test_kpp_format() -> None:
    assert str(Kpp("770101001")) == "770101001"
    assert Kpp("7701AB001").value == "7701AB001"
    for bad in ("77010100", "7701010011", "7701ab001", "AB0101001"):
        with pytest.raises(ValidationError):
            Kpp(bad)


@pytest.mark.parametrize(
    "inn,ogrn,legal_form,kpp,field",
    [
        # INN of a legal entity with OGRNIP
        (ROMASHKA.inn, IVANOV.ogrn, "LLC", ROMASHKA.kpp, "ogrn"),
        # OGRN of a legal entity with the INN of an entrepreneur
        (IVANOV.inn, ROMASHKA.ogrn, "IE", None, "ogrn"),
        # an entrepreneur has no KPP
        (IVANOV.inn, IVANOV.ogrn, "IE", "770101001", "kpp"),
        # a legal entity always has one
        (ROMASHKA.inn, ROMASHKA.ogrn, "LLC", None, "kpp"),
        # legal form against the INN
        (ROMASHKA.inn, ROMASHKA.ogrn, "IE", None, "inn"),
        (IVANOV.inn, IVANOV.ogrn, "LLC", "770101001", "inn"),
        (IVANOV.inn, IVANOV.ogrn, "JSC", "770101001", "inn"),
    ],
)
def test_inconsistent_requisites(
    inn: str, ogrn: str, legal_form: str, kpp: str | None, field: str
) -> None:
    with pytest.raises(ValidationError) as error:
        Requisites.of(inn, ogrn, legal_form, kpp)
    assert code_of(error)[0] == field


def test_joint_stock_company_is_a_legal_entity() -> None:
    requisites = Requisites.of(ROMASHKA.inn, ROMASHKA.ogrn, "JSC", ROMASHKA.kpp)
    assert requisites.legal_form is LegalForm.JSC
    assert not requisites.legal_form.is_entrepreneur


def test_unknown_legal_form() -> None:
    with pytest.raises(ValidationError) as error:
        Requisites.of(ROMASHKA.inn, ROMASHKA.ogrn, "PAO", ROMASHKA.kpp)
    assert code_of(error) == ("legal_form", "unknown")


def test_requisites_are_frozen() -> None:
    requisites = Requisites.of(ROMASHKA.inn, ROMASHKA.ogrn, "LLC", ROMASHKA.kpp)
    with pytest.raises(AttributeError):
        requisites.inn = Inn(IVANOV.inn)  # type: ignore[misc]


# --- okved, address, period --------------------------------------------------


@pytest.mark.parametrize(
    "value,division,section",
    [("56.10", "56", "I"), ("62.01", "62", "J"), ("47.19.1", "47", "G"), ("01", "01", "A")],
)
def test_okved(value: str, division: str, section: str) -> None:
    code = OkvedCode(value)
    assert (code.division, code.section) == (division, section)


@pytest.mark.parametrize("value", ["5610", "56.", "56.100", "1.1", "56.10.10.1", "AB.10"])
def test_okved_format(value: str) -> None:
    with pytest.raises(ValidationError) as error:
        OkvedCode(value)
    assert code_of(error) == ("okved", "bad_format")


def test_okved_division_must_exist() -> None:
    with pytest.raises(ValidationError) as error:
        OkvedCode("04.10")
    assert code_of(error) == ("okved", "unknown_division")


@pytest.mark.parametrize("company", COMPANIES, ids=[c.code for c in COMPANIES])
def test_demo_okved_is_valid(company: DemoCompany) -> None:
    assert OkvedCode(company.okved_main).division == company.okved_main[:2]


def test_address() -> None:
    assert Address("г. Москва, ул. Тверская, д. 1", "77").region_code == "77"
    with pytest.raises(ValidationError):
        Address("  ", "77")
    with pytest.raises(ValidationError):
        Address("г. Москва", "7")


@pytest.mark.parametrize(
    "quarter,ends_on",
    [
        (None, date(2025, 12, 31)),
        (1, date(2025, 3, 31)),
        (2, date(2025, 6, 30)),
        (3, date(2025, 9, 30)),
        (4, date(2025, 12, 31)),
    ],
)
def test_fiscal_period_end(quarter: int | None, ends_on: date) -> None:
    period = FiscalPeriod(2025, quarter)
    assert period.ends_on == ends_on
    assert period.is_annual == (quarter is None)
    assert period.is_closed(ends_on + timedelta(days=1))
    assert not period.is_closed(ends_on)


def test_fiscal_period_bounds() -> None:
    assert str(FiscalPeriod(2025)) == "2025" and str(FiscalPeriod(2025, 3)) == "2025 Q3"
    for year, quarter in ((1999, None), (2101, None), (2025, 0), (2025, 5)):
        with pytest.raises(ValidationError):
            FiscalPeriod(year, quarter)


# --- people and registry check -----------------------------------------------


def test_person_name_normalized_for_the_registry() -> None:
    declared = PersonName("  Сёмин ", "Пётр", "Петрович")
    registry = PersonName("СЕМИН", "петр", "  петрович")
    assert declared.normalized() == "семин петр петрович"
    assert declared.matches(registry)
    assert not declared.matches(PersonName("Семин", "Петр"))
    assert PersonName("Петров", "Пётр", "Петрович").short == "Петров П. П."
    assert PersonName("Андеррайтеров", "Андрей").full == "Андеррайтеров Андрей"


def test_person_name_is_masked_in_repr() -> None:
    name = PersonName("Смирнова", "Анна", "Сергеевна")
    for text in (repr(name), str(name), f"{name}", repr([name])):
        assert "Смирнова" not in text and "Анна" not in text
    assert name.full == "Смирнова Анна Сергеевна"


def test_person_name_validation() -> None:
    for kwargs in ({"last_name": " ", "first_name": "Анна"}, {"last_name": "А", "first_name": ""}):
        with pytest.raises(ValidationError):
            PersonName(**kwargs)


def test_verification_result_states() -> None:
    now = datetime(2026, 10, 21, tzinfo=UTC)
    assert VerificationResult().status is VerificationStatus.UNVERIFIED
    assert VerificationResult.verified(now).checked_at == now
    mismatch = VerificationResult.mismatch(
        now, (Discrepancy("head_name", "Петров П. П.", "Сидоров С. С."),)
    )
    assert mismatch.status is VerificationStatus.MISMATCH

    with pytest.raises(ValueError):
        VerificationResult(VerificationStatus.VERIFIED)
    with pytest.raises(ValueError):
        VerificationResult(VerificationStatus.MISMATCH, now)
    with pytest.raises(ValueError):
        VerificationResult(VerificationStatus.VERIFIED, now, mismatch.discrepancies)
    with pytest.raises(ValueError):
        VerificationResult(VerificationStatus.UNVERIFIED, now)
    with pytest.raises(ValueError):
        VerificationResult.verified(datetime(2026, 10, 21))
