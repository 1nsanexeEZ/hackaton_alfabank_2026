"""Check of a company by INN before an application — a tool of the bank employee.

The company may be unknown to the bank. What the sources say about it (ЕГРЮЛ/ЕГРИП, the tax
service, Kontur, the bank stop list) comes as a `CompanyRecord`; the rules here turn it into
a list of checks and a verdict: the worst status of the checks. The requisites from the
client's documents (OGRN, KPP, name) may come with the INN: then the INN is matched against
them too.

Texts of the checks are in Russian: the bank employee reads them as they are.
"""

# No `from __future__ import annotations`: the `date: date` fields would point at themselves.
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from src.modules.clients.domain.enums import LegalForm, RegistryStatus, VerificationStatus
from src.modules.clients.domain.value_objects import Inn, RegistryExtract, VerificationResult


class CheckStatus(StrEnum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    # The source did not answer: nothing to judge by.
    SKIPPED = "skipped"


class Verdict(StrEnum):
    OK = "ok"
    # A person should look: a warning or a source that did not answer.
    WARNING = "warning"
    FAIL = "fail"
    # ЕГРЮЛ/ЕГРИП do not know the INN.
    NOT_FOUND = "not_found"


class CheckSource(StrEnum):
    # The INN itself and the requisites passed with it.
    INPUT = "input"
    EGRUL = "egrul"
    FNS = "fns"
    KONTUR = "kontur"
    # The bank's own data: the stop list, the client card.
    BANK = "bank"


@dataclass(frozen=True, slots=True)
class Declared:
    """Requisites from the client's documents to match the INN against; any may be omitted."""

    ogrn: str | None = None
    kpp: str | None = None
    name: str | None = None


@dataclass(frozen=True, slots=True)
class Founder:
    name: str
    share_percent: Decimal
    # A legal entity founder — by its INN; a person — by the name only.
    inn: str | None = None


@dataclass(frozen=True, slots=True)
class RegistryRecord:
    """ЕГРЮЛ/ЕГРИП beyond the extract the card follows: what the check needs and the bank
    employee sees."""

    extract: RegistryExtract
    legal_form: LegalForm
    full_name: str
    registered_at: date
    head_position: str
    head_since: date | None = None
    mass_address: bool = False
    # Records of unreliable data: address | head | founder.
    unreliable: tuple[str, ...] = ()
    founders: tuple[Founder, ...] = ()


@dataclass(frozen=True, slots=True)
class AccountBlock:
    """A decision of the tax service to suspend operations on the accounts."""

    decision_number: str
    date: date
    reason: str


@dataclass(frozen=True, slots=True)
class TaxRecord:
    """The tax service («Прозрачный бизнес»), rubles."""

    tax_regime: str
    avg_headcount: int
    reported_revenue: Decimal | None
    report_year: int | None
    tax_arrears: Decimal
    in_msp_registry: bool
    disqualified_head: bool
    # None — the tax service did not say.
    mass_head: bool | None = None
    account_blocks: tuple[AccountBlock, ...] = ()


@dataclass(frozen=True, slots=True)
class BankruptcyNotice:
    date: date
    kind: str
    case: str


@dataclass(frozen=True, slots=True)
class CourtRecord:
    """Kontur: courts, bailiffs, bankruptcy; rubles."""

    reliability: str
    notes: tuple[str, ...]
    arbitration_as_defendant: int
    arbitration_defendant_sum: Decimal
    enforcement_active: int
    enforcement_sum: Decimal
    bankruptcy: tuple[BankruptcyNotice, ...] = ()


@dataclass(frozen=True, slots=True)
class StopListRecord:
    listed: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class CompanyRecord:
    """What the sources say about a company by its INN. A source that did not answer is None:
    its checks are skipped."""

    registry: RegistryRecord
    tax: TaxRecord | None = None
    court: CourtRecord | None = None
    stop_list: StopListRecord | None = None


@dataclass(frozen=True, slots=True)
class Check:
    code: str
    title: str
    status: CheckStatus
    message: str
    source: CheckSource


@dataclass(frozen=True, slots=True)
class InnCheck:
    inn: str
    verdict: Verdict
    summary: str
    checks: tuple[Check, ...]
    # None — nothing found: an unknown INN or a typo in it.
    record: CompanyRecord | None = None


# Every check: its title and where its data comes from, in the order of the answer.
_CHECKS: dict[str, tuple[str, CheckSource]] = {
    "inn_checksum": ("Контрольная сумма ИНН", CheckSource.INPUT),
    "registry_found": ("Запись в реестре", CheckSource.EGRUL),
    "ogrn_match": ("ОГРН", CheckSource.INPUT),
    "kpp_match": ("КПП", CheckSource.INPUT),
    "name_match": ("Наименование", CheckSource.INPUT),
    "registry_status": ("Статус в реестре", CheckSource.EGRUL),
    "unreliable_data": ("Достоверность сведений", CheckSource.EGRUL),
    "mass_address": ("Массовый адрес", CheckSource.EGRUL),
    "company_age": ("Возраст бизнеса", CheckSource.EGRUL),
    "tax_arrears": ("Недоимка по налогам", CheckSource.FNS),
    "account_blocks": ("Блокировка счетов", CheckSource.FNS),
    "disqualified_head": ("Дисквалификация руководителя", CheckSource.FNS),
    "mass_head": ("Массовый руководитель", CheckSource.FNS),
    "bankruptcy": ("Банкротство", CheckSource.KONTUR),
    "enforcement": ("Исполнительные производства", CheckSource.KONTUR),
    "bank_stop_list": ("Стоп-лист банка", CheckSource.BANK),
    "bank_client": ("Клиент банка", CheckSource.BANK),
}

PASSED, WARNING, FAILED, SKIPPED = (
    CheckStatus.PASSED,
    CheckStatus.WARNING,
    CheckStatus.FAILED,
    CheckStatus.SKIPPED,
)


def _check(code: str, status: CheckStatus, message: str, *, title: str | None = None) -> Check:
    default_title, source = _CHECKS[code]
    return Check(code, title or default_title, status, message, source)


# --- entry points -----------------------------------------------------------------------------


def inn_typo(inn: str) -> InnCheck:
    """10 or 12 digits, but the check digit is wrong: no company can have this INN."""
    check = _check("inn_checksum", FAILED, "Контрольная цифра не сходится: в номере ошибка")
    return InnCheck(inn, Verdict.FAIL, "Не пройдена: в ИНН ошибка", (check,))


def not_found(inn: Inn) -> InnCheck:
    message = f"ИНН не найден в {_registry_name(inn)}"
    checks = (_checksum_passed(), _check("registry_found", FAILED, message))
    return InnCheck(inn.value, Verdict.NOT_FOUND, message, checks)


def assess(
    inn: Inn,
    declared: Declared,
    record: CompanyRecord,
    today: date,
    client: VerificationResult | None = None,
) -> InnCheck:
    """`client` — the check of the bank's card of this company against the registry; None —
    the company is not a client of the bank."""
    extract = record.registry.extract
    checks = [
        _checksum_passed(),
        _check("registry_found", PASSED, f"Найдена в {_registry_name(inn)}: {extract.name}"),
        *_declared_checks(inn, declared, extract),
        *_registry_checks(inn, record.registry, today),
        *_tax_checks(record.tax),
        *_court_checks(record.court),
        _stop_list_check(record.stop_list),
    ]
    if client is not None:
        checks.append(_client_check(client))
    return InnCheck(inn.value, _verdict(checks), _summary(checks), tuple(checks), record)


# --- the requisites passed with the INN --------------------------------------------------------

_MATCHES = "Совпадает с реестром"


def _declared_checks(inn: Inn, declared: Declared, extract: RegistryExtract) -> list[Check]:
    checks = []
    if declared.ogrn is not None:
        title = "ОГРНИП" if inn.is_entrepreneur else "ОГРН"
        registry_ogrn = extract.ogrn.value
        if declared.ogrn == registry_ogrn:
            checks.append(_check("ogrn_match", PASSED, _MATCHES, title=title))
        else:
            message = (
                f"По этому ИНН в реестре {title} {registry_ogrn}: ИНН и {title} — "
                "от разных компаний"
            )
            checks.append(_check("ogrn_match", FAILED, message, title=title))
    if declared.kpp is not None:
        checks.append(_kpp_check(inn, declared.kpp, extract))
    if declared.name is not None:
        if _core_name(declared.name) == _core_name(extract.name):
            checks.append(_check("name_match", PASSED, _MATCHES))
        else:
            message = (
                f"По этому ИНН в реестре — {extract.name}: ИНН другой компании или ошибка "
                "в названии"
            )
            checks.append(_check("name_match", FAILED, message))
    return checks


def _kpp_check(inn: Inn, kpp: str, extract: RegistryExtract) -> Check:
    if inn.is_entrepreneur:
        return _check("kpp_match", WARNING, "У предпринимателя КПП нет")
    if extract.kpp is None:
        return _check("kpp_match", SKIPPED, "Реестр не сообщил КПП")
    if kpp == extract.kpp.value:
        return _check("kpp_match", PASSED, _MATCHES)
    message = (
        f"В реестре КПП {extract.kpp.value}: компания могла встать на учёт в другой налоговой — "
        "уточните реквизиты"
    )
    return _check("kpp_match", WARNING, message)


_LEGAL_FORMS = (
    "общество с ограниченной ответственностью",
    "публичное акционерное общество",
    "непубличное акционерное общество",
    "закрытое акционерное общество",
    "открытое акционерное общество",
    "акционерное общество",
    "индивидуальный предприниматель",
    "ооо",
    "пао",
    "зао",
    "оао",
    "ао",
    "ип",
)


def _core_name(name: str) -> str:
    """`ООО «Ромашка»`, `Общество с ограниченной ответственностью "Ромашка"` and `ромашка` are
    one name: no legal form, quotes, punctuation and case; ё is е."""
    text = " ".join(re.sub(r"[^\w]+", " ", name.lower().replace("ё", "е")).split())
    for form in _LEGAL_FORMS:
        if text == form:
            return ""
        if text.startswith(form + " "):
            return text[len(form) + 1 :]
    return text


# --- ЕГРЮЛ / ЕГРИП ------------------------------------------------------------------------------

_STATUS_TEXTS = {
    RegistryStatus.ACTIVE: "Действует",
    RegistryStatus.LIQUIDATING: "В процессе ликвидации",
    RegistryStatus.LIQUIDATED: "Ликвидирована, деятельность прекращена",
    RegistryStatus.BANKRUPT: "Признана банкротом",
    RegistryStatus.REORGANIZING: "В процессе реорганизации",
    RegistryStatus.EXCLUDED: "Исключена из реестра как недействующая",
}
_UNRELIABLE = {"address": "адрес", "head": "руководитель", "founder": "учредитель"}
_YOUNG_MONTHS = 12


def _registry_checks(inn: Inn, registry: RegistryRecord, today: date) -> list[Check]:
    extract = registry.extract
    active = extract.status is RegistryStatus.ACTIVE
    checks = [
        _check("registry_status", PASSED if active else FAILED, _STATUS_TEXTS[extract.status])
    ]
    if registry.unreliable:
        marks = ", ".join(_UNRELIABLE.get(mark, mark) for mark in registry.unreliable)
        message = f"В {_registry_name(inn)} отметка о недостоверности: {marks}"
        checks.append(_check("unreliable_data", FAILED, message))
    else:
        checks.append(_check("unreliable_data", PASSED, "Отметок о недостоверности нет"))
    if registry.mass_address:
        message = f"Адрес массовой регистрации: {extract.address.full}"
        checks.append(_check("mass_address", FAILED, message))
    else:
        checks.append(_check("mass_address", PASSED, "Адрес не массовый"))
    registered = f"Зарегистрирована {_ru_date(registry.registered_at)}"
    if _months_between(registry.registered_at, today) < _YOUNG_MONTHS:
        checks.append(_check("company_age", WARNING, f"{registered} — меньше года назад"))
    else:
        checks.append(_check("company_age", PASSED, registered))
    return checks


def _months_between(start: date, end: date) -> int:
    months = (end.year - start.year) * 12 + end.month - start.month
    return months - 1 if end.day < start.day else months


# --- the tax service ----------------------------------------------------------------------------


def _tax_checks(tax: TaxRecord | None) -> list[Check]:
    codes = ("tax_arrears", "account_blocks", "disqualified_head", "mass_head")
    if tax is None:
        return [_check(code, SKIPPED, "ФНС не ответила — не проверено") for code in codes]
    if tax.tax_arrears > 0:
        arrears = _check("tax_arrears", WARNING, f"Недоимка {_rub(tax.tax_arrears)}")
    else:
        arrears = _check("tax_arrears", PASSED, "Недоимки нет")
    if tax.account_blocks:
        decisions = "; ".join(
            f"решение № {b.decision_number} от {_ru_date(b.date)} ({b.reason})"
            for b in tax.account_blocks
        )
        message = f"ФНС приостановила операции по счетам: {decisions}"
        blocks = _check("account_blocks", FAILED, message)
    else:
        blocks = _check("account_blocks", PASSED, "Решений о приостановлении операций нет")
    if tax.disqualified_head:
        disqualified = _check("disqualified_head", FAILED, "Руководитель дисквалифицирован")
    else:
        disqualified = _check("disqualified_head", PASSED, "Руководитель не дисквалифицирован")
    if tax.mass_head is None:
        mass_head = _check("mass_head", SKIPPED, "ФНС не сообщила")
    elif tax.mass_head:
        mass_head = _check(
            "mass_head", FAILED, "Руководитель массовый: руководит многими компаниями"
        )
    else:
        mass_head = _check("mass_head", PASSED, "Руководитель не массовый")
    return [arrears, blocks, disqualified, mass_head]


# --- Kontur ---------------------------------------------------------------------------------------


def _court_checks(court: CourtRecord | None) -> list[Check]:
    if court is None:
        message = "Контур не ответил — не проверено"
        return [_check("bankruptcy", SKIPPED, message), _check("enforcement", SKIPPED, message)]
    if court.bankruptcy:
        notices = "; ".join(
            f"{n.kind} от {_ru_date(n.date)}, дело {n.case}" for n in court.bankruptcy
        )
        bankruptcy = _check("bankruptcy", FAILED, notices)
    else:
        bankruptcy = _check("bankruptcy", PASSED, "Сообщений о банкротстве нет")
    if court.enforcement_active > 0:
        message = (
            f"Открыто производств: {court.enforcement_active} на {_rub(court.enforcement_sum)}"
        )
        enforcement = _check("enforcement", WARNING, message)
    else:
        enforcement = _check("enforcement", PASSED, "Открытых производств нет")
    return [bankruptcy, enforcement]


# --- the bank's own data --------------------------------------------------------------------------


def _stop_list_check(stop_list: StopListRecord | None) -> Check:
    if stop_list is None:
        return _check("bank_stop_list", SKIPPED, "Стоп-лист не ответил — не проверено")
    if stop_list.listed:
        reason = f": {stop_list.reason}" if stop_list.reason else ""
        return _check("bank_stop_list", FAILED, f"Компания во внутреннем стоп-листе банка{reason}")
    return _check("bank_stop_list", PASSED, "Во внутреннем стоп-листе нет")


_FIELDS = {"head_name": "руководитель"}


def _client_check(verification: VerificationResult) -> Check:
    """The company is a client: its card was checked against the registry before (on request
    or after an application) — a mismatch found then is shown."""
    if verification.status is VerificationStatus.UNVERIFIED or verification.checked_at is None:
        return _check("bank_client", PASSED, "Клиент банка, карточка с реестром ещё не сверялась")
    checked = _ru_date(verification.checked_at.date())
    if verification.status is VerificationStatus.MISMATCH:
        found = "; ".join(
            f"{_FIELDS.get(d.field, d.field)}: заявлен {d.declared or '—'}, "
            f"в реестре {d.registry or '—'}"
            for d in verification.discrepancies
        )
        message = f"Клиент банка, при сверке {checked} карточка разошлась с реестром — {found}"
        return _check("bank_client", WARNING, message)
    return _check("bank_client", PASSED, f"Клиент банка, карточка сверена {checked}")


# --- verdict ------------------------------------------------------------------------------------


def _verdict(checks: list[Check]) -> Verdict:
    statuses = {check.status for check in checks}
    if FAILED in statuses:
        return Verdict.FAIL
    if statuses & {WARNING, SKIPPED}:
        return Verdict.WARNING
    return Verdict.OK


def _summary(checks: list[Check]) -> str:
    failed = [c.title for c in checks if c.status is FAILED]
    if failed:
        return "Не пройдена: " + _titles(failed)
    doubtful = [c.title for c in checks if c.status in (WARNING, SKIPPED)]
    if doubtful:
        return "Есть замечания: " + _titles(doubtful)
    return "Проверка пройдена"


def _titles(titles: list[str]) -> str:
    """`Статус в реестре`, `ОГРН` → `статус в реестре, ОГРН`: an abbreviation keeps its case."""
    return ", ".join(t if t[:2].isupper() else t[0].lower() + t[1:] for t in titles)


# --- helpers ------------------------------------------------------------------------------------


def _registry_name(inn: Inn) -> str:
    return "ЕГРИП" if inn.is_entrepreneur else "ЕГРЮЛ"


def _checksum_passed() -> Check:
    return _check("inn_checksum", PASSED, "Номер записан без ошибок")


def _ru_date(day: date) -> str:
    return day.strftime("%d.%m.%Y")


def _rub(amount: Decimal) -> str:
    """`1240000` → `1 240 000 ₽`, kopecks only when there are any: `350 000,50 ₽`."""
    rubles = int(amount)
    kopecks = int((abs(amount) - abs(rubles)) * 100)
    text = f"{rubles:,}".replace(",", " ")
    return f"{text},{kopecks:02d} ₽" if kopecks else f"{text} ₽"
