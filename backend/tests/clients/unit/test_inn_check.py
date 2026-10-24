"""Rules of the check by INN before an application: checks, statuses, the verdict."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from src.modules.clients.domain.enums import LegalForm, RegistryStatus
from src.modules.clients.domain.inn_check import (
    AccountBlock,
    BankruptcyNotice,
    CheckStatus,
    CompanyRecord,
    CourtRecord,
    Declared,
    InnCheck,
    RegistryRecord,
    StopListRecord,
    TaxRecord,
    Verdict,
    assess,
    inn_typo,
    not_found,
)
from src.modules.clients.domain.value_objects import (
    Address,
    Discrepancy,
    Inn,
    Kpp,
    Ogrn,
    OkvedCode,
    PersonName,
    RegistryExtract,
    VerificationResult,
)
from tests.clients.unit.factories import NOW

TODAY = NOW.date()
INN = Inn("7701158817")

EXTRACT = RegistryExtract(
    inn=INN,
    ogrn=Ogrn("1027700399869"),
    name="ООО «Ромашка»",
    address=Address("г. Москва, ул. Тверская, д. 1", "77"),
    okved_main=OkvedCode("56.10"),
    status=RegistryStatus.ACTIVE,
    head=PersonName("Смирнова", "Анна", "Сергеевна"),
    kpp=Kpp("770101001"),
)
REGISTRY = RegistryRecord(
    extract=EXTRACT,
    legal_form=LegalForm.LLC,
    full_name="Общество с ограниченной ответственностью «Ромашка»",
    registered_at=date(2020, 10, 21),
    head_position="Генеральный директор",
)
TAX = TaxRecord(
    tax_regime="УСН",
    avg_headcount=12,
    reported_revenue=Decimal(47_500_000),
    report_year=2025,
    tax_arrears=Decimal(0),
    in_msp_registry=True,
    disqualified_head=False,
    mass_head=False,
)
COURT = CourtRecord(
    reliability="green",
    notes=(),
    arbitration_as_defendant=0,
    arbitration_defendant_sum=Decimal(0),
    enforcement_active=0,
    enforcement_sum=Decimal(0),
)
GOOD = CompanyRecord(REGISTRY, TAX, COURT, StopListRecord(listed=False))
NOTHING_DECLARED = Declared()


def check(
    record: CompanyRecord = GOOD,
    declared: Declared = NOTHING_DECLARED,
    client: VerificationResult | None = None,
    inn: Inn = INN,
) -> InnCheck:
    return assess(inn, declared, record, TODAY, client)


def statuses(result: InnCheck) -> dict[str, CheckStatus]:
    return {c.code: c.status for c in result.checks}


def message(result: InnCheck, code: str) -> str:
    return next(c.message for c in result.checks if c.code == code)


def registry(**changes: object) -> CompanyRecord:
    return replace(GOOD, registry=replace(REGISTRY, **changes))  # type: ignore[arg-type]


def test_good_company_passes_every_check() -> None:
    result = check()

    assert result.verdict is Verdict.OK and result.summary == "Проверка пройдена"
    assert [c.code for c in result.checks] == [
        "inn_checksum",
        "registry_found",
        "registry_status",
        "unreliable_data",
        "mass_address",
        "company_age",
        "tax_arrears",
        "account_blocks",
        "disqualified_head",
        "mass_head",
        "bankruptcy",
        "enforcement",
        "bank_stop_list",
    ]
    assert set(statuses(result).values()) == {CheckStatus.PASSED}
    assert message(result, "registry_found") == "Найдена в ЕГРЮЛ: ООО «Ромашка»"
    assert result.record is GOOD


# --- what was passed with the INN -------------------------------------------------------------


def test_declared_requisites_that_match() -> None:
    declared = Declared(
        ogrn="1027700399869",
        kpp="770101001",
        name='Общество с ограниченной ответственностью "РОМАШКА"',
    )

    result = check(declared=declared)

    assert result.verdict is Verdict.OK
    found = statuses(result)
    assert found["ogrn_match"] == found["kpp_match"] == found["name_match"] == CheckStatus.PASSED


def test_inn_of_another_company() -> None:
    """The INN of «Ромашка» with the OGRN and the name of «Вектор»."""
    result = check(declared=Declared(ogrn="1037702309116", name="ООО «Вектор»"))

    assert result.verdict is Verdict.FAIL
    assert result.summary == "Не пройдена: ОГРН, наименование"
    assert message(result, "ogrn_match") == (
        "По этому ИНН в реестре ОГРН 1027700399869: ИНН и ОГРН — от разных компаний"
    )
    assert message(result, "name_match").startswith("По этому ИНН в реестре — ООО «Ромашка»")


def test_other_kpp_is_a_warning() -> None:
    result = check(declared=Declared(kpp="770201001"))

    assert result.verdict is Verdict.WARNING
    assert statuses(result)["kpp_match"] is CheckStatus.WARNING
    assert "В реестре КПП 770101001" in message(result, "kpp_match")


def test_entrepreneur_has_no_kpp_and_an_ogrnip() -> None:
    inn = Inn("770669871605")
    extract = replace(
        EXTRACT, inn=inn, ogrn=Ogrn("325770689768464"), name="ИП Иванов Иван Иванович", kpp=None
    )
    record = registry(extract=extract, legal_form=LegalForm.IE)

    result = check(
        record,
        Declared(ogrn="325770689768464", kpp="770101001", name="Иванов Иван Иванович"),
        inn=inn,
    )

    found = {c.code: c for c in result.checks}
    assert found["ogrn_match"].title == "ОГРНИП"
    assert found["ogrn_match"].status is CheckStatus.PASSED
    assert found["name_match"].status is CheckStatus.PASSED
    assert found["kpp_match"].status is CheckStatus.WARNING
    assert message(result, "registry_found") == "Найдена в ЕГРИП: ИП Иванов Иван Иванович"


@pytest.mark.parametrize(
    "name", ["Ромашка", "ромашка", "ООО Ромашка", "ООО «Ромашка»", "  ооо   'РОМАШКА' "]
)
def test_name_is_compared_without_the_form_quotes_and_case(name: str) -> None:
    assert statuses(check(declared=Declared(name=name)))["name_match"] is CheckStatus.PASSED


@pytest.mark.parametrize("name", ["ООО", "Ромашка Плюс", "ООО «Ромашка-2»"])
def test_other_name_is_a_mismatch(name: str) -> None:
    assert statuses(check(declared=Declared(name=name)))["name_match"] is CheckStatus.FAILED


# --- the registry -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "text"),
    [
        (RegistryStatus.LIQUIDATING, "В процессе ликвидации"),
        (RegistryStatus.BANKRUPT, "Признана банкротом"),
        (RegistryStatus.EXCLUDED, "Исключена из реестра как недействующая"),
        (RegistryStatus.REORGANIZING, "В процессе реорганизации"),
    ],
)
def test_company_that_does_not_act_fails(status: RegistryStatus, text: str) -> None:
    result = check(registry(extract=replace(EXTRACT, status=status)))

    assert result.verdict is Verdict.FAIL
    assert message(result, "registry_status") == text
    assert result.summary == "Не пройдена: статус в реестре"


def test_registry_marks() -> None:
    result = check(registry(mass_address=True, unreliable=("address", "head")))

    assert result.verdict is Verdict.FAIL
    assert message(result, "unreliable_data") == (
        "В ЕГРЮЛ отметка о недостоверности: адрес, руководитель"
    )
    assert message(result, "mass_address") == (
        "Адрес массовой регистрации: г. Москва, ул. Тверская, д. 1"
    )


def test_young_company_is_a_warning() -> None:
    young = check(registry(registered_at=date(2025, 10, 22)))
    year_old = check(registry(registered_at=date(2025, 10, 21)))

    assert young.verdict is Verdict.WARNING
    assert message(young, "company_age") == "Зарегистрирована 22.10.2025 — меньше года назад"
    assert young.summary == "Есть замечания: возраст бизнеса"
    assert statuses(year_old)["company_age"] is CheckStatus.PASSED


# --- the tax service, Kontur, the stop list ----------------------------------------------------


def test_debts_are_warnings() -> None:
    tax = replace(TAX, tax_arrears=Decimal("1240000.50"))
    court = replace(COURT, enforcement_active=3, enforcement_sum=Decimal(1_860_000))

    result = check(replace(GOOD, tax=tax, court=court))

    assert result.verdict is Verdict.WARNING
    assert message(result, "tax_arrears") == "Недоимка 1 240 000,50 ₽"
    assert message(result, "enforcement") == "Открыто производств: 3 на 1 860 000 ₽"


def test_blocked_accounts_bankruptcy_and_the_stop_list_fail() -> None:
    tax = replace(
        TAX,
        disqualified_head=True,
        mass_head=True,
        account_blocks=(AccountBlock("4512", date(2026, 9, 30), "Неуплата налогов"),),
    )
    court = replace(
        COURT,
        bankruptcy=(
            BankruptcyNotice(date(2026, 6, 15), "Признание должника банкротом", "А40-1/2026"),
        ),
    )
    stop_list = StopListRecord(listed=True, reason="Подложные документы")

    result = check(replace(GOOD, tax=tax, court=court, stop_list=stop_list))

    assert result.verdict is Verdict.FAIL
    assert message(result, "account_blocks") == (
        "ФНС приостановила операции по счетам: решение № 4512 от 30.09.2026 (Неуплата налогов)"
    )
    assert (
        message(result, "bankruptcy")
        == "Признание должника банкротом от 15.06.2026, дело А40-1/2026"
    )
    assert message(result, "bank_stop_list") == (
        "Компания во внутреннем стоп-листе банка: Подложные документы"
    )
    assert result.summary == (
        "Не пройдена: блокировка счетов, дисквалификация руководителя, массовый руководитель, "
        "банкротство, стоп-лист банка"
    )


def test_sources_that_did_not_answer_are_skipped() -> None:
    result = check(CompanyRecord(REGISTRY))

    skipped = [code for code, status in statuses(result).items() if status is CheckStatus.SKIPPED]
    assert skipped == [
        "tax_arrears",
        "account_blocks",
        "disqualified_head",
        "mass_head",
        "bankruptcy",
        "enforcement",
        "bank_stop_list",
    ]
    assert result.verdict is Verdict.WARNING
    assert message(result, "tax_arrears") == "ФНС не ответила — не проверено"


# --- the bank's client --------------------------------------------------------------------------


def test_client_card_checked_before() -> None:
    verified = check(client=VerificationResult.verified(NOW))
    mismatch = check(
        client=VerificationResult.mismatch(
            NOW, (Discrepancy("head_name", "Петров П. П.", "Сидоров С. С."),)
        )
    )

    assert message(verified, "bank_client") == "Клиент банка, карточка сверена 21.10.2026"
    assert verified.verdict is Verdict.OK
    assert mismatch.verdict is Verdict.WARNING
    assert message(mismatch, "bank_client") == (
        "Клиент банка, при сверке 21.10.2026 карточка разошлась с реестром — "
        "руководитель: заявлен Петров П. П., в реестре Сидоров С. С."
    )
    unverified = check(client=VerificationResult())
    assert statuses(unverified)["bank_client"] is CheckStatus.PASSED


# --- nothing to check -----------------------------------------------------------------------------


def test_typo_and_unknown_inn() -> None:
    typo = inn_typo("7701158818")
    assert typo.verdict is Verdict.FAIL and typo.record is None
    assert [(c.code, c.status) for c in typo.checks] == [("inn_checksum", CheckStatus.FAILED)]

    unknown = not_found(Inn("7707177990"))
    assert unknown.verdict is Verdict.NOT_FOUND and unknown.record is None
    assert unknown.summary == "ИНН не найден в ЕГРЮЛ"
    assert statuses(unknown) == {
        "inn_checksum": CheckStatus.PASSED,
        "registry_found": CheckStatus.FAILED,
    }
    assert not_found(Inn("770669871605")).summary == "ИНН не найден в ЕГРИП"
