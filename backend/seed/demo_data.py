"""Demo data shared by seeds, mocks, golden tests and e2e (docs: 00-common §9).

INN/OGRN have valid check digits and must not change: seeds, external mocks
and golden tests depend on them. Dates are relative (months before "now"),
so the demo looks the same whenever it is started.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

LegalForm = Literal["LLC", "IE", "JSC"]
MemberRole = Literal["owner", "director", "accountant", "employee"]
Authority = Literal["registry", "power_of_attorney", "unconfirmed"]


@dataclass(frozen=True, slots=True)
class DemoPerson:
    last_name: str
    first_name: str
    middle_name: str | None = None


@dataclass(frozen=True, slots=True)
class DemoCompany:
    code: str
    name: str
    legal_form: LegalForm
    inn: str
    ogrn: str
    kpp: str | None
    okved_main: str
    okved_title: str
    registered_months_ago: int
    registry_status: Literal["active", "liquidating", "liquidated", "bankrupt"]
    registry_head: DemoPerson


@dataclass(frozen=True, slots=True)
class DemoFinancials:
    company_code: str
    declared_revenue: Decimal
    declared_revenue_previous_year: Decimal | None
    declared_expenses: Decimal
    fns_revenue: Decimal
    tax_arrears: Decimal
    # Short description of what the credit bureau mock returns.
    credit_bureau: str
    # Shape of the synthetic bank statement in seed/statements/<code>.csv.
    statement_profile: str


@dataclass(frozen=True, slots=True)
class DemoMembership:
    company_code: str
    role: MemberRole
    authority: Authority


@dataclass(frozen=True, slots=True)
class DemoAccount:
    email: str
    phone: str | None
    person: DemoPerson
    identity_role: Literal["client", "underwriter"]
    caption: str
    memberships: tuple[DemoMembership, ...] = ()


COMPANIES: tuple[DemoCompany, ...] = (
    DemoCompany(
        code="romashka",
        name="ООО «Ромашка»",
        legal_form="LLC",
        inn="7701158817",
        ogrn="1027700399869",
        kpp="770101001",
        okved_main="56.10",
        okved_title="Деятельность ресторанов и кафе",
        registered_months_ago=72,
        registry_status="active",
        registry_head=DemoPerson("Смирнова", "Анна", "Сергеевна"),
    ),
    DemoCompany(
        code="ivanov",
        name="ИП Иванов Иван Иванович",
        legal_form="IE",
        inn="770669871605",
        ogrn="325770689768464",
        kpp=None,
        okved_main="62.01",
        okved_title="Разработка компьютерного программного обеспечения",
        registered_months_ago=8,
        registry_status="active",
        registry_head=DemoPerson("Иванов", "Иван", "Иванович"),
    ),
    DemoCompany(
        code="vector",
        name="ООО «Вектор»",
        legal_form="LLC",
        inn="7702987976",
        ogrn="1037702309116",
        kpp="770201001",
        okved_main="41.20",
        okved_title="Строительство жилых и нежилых зданий",
        registered_months_ago=48,
        registry_status="active",
        # The cabinet says the director is Petrov: a registry mismatch on purpose (S-3).
        registry_head=DemoPerson("Сидоров", "Сергей", "Сергеевич"),
    ),
    DemoCompany(
        code="zakat",
        name="ООО «Закат»",
        legal_form="LLC",
        inn="7703417070",
        ogrn="1047703536451",
        kpp="770301001",
        okved_main="47.19",
        okved_title="Прочая розничная торговля в неспециализированных магазинах",
        registered_months_ago=108,
        registry_status="liquidating",
        registry_head=DemoPerson("Закатов", "Олег", "Олегович"),
    ),
    DemoCompany(
        code="progress",
        name="ООО «Прогресс»",
        legal_form="LLC",
        inn="7704568152",
        ogrn="1057704188442",
        kpp="770401001",
        okved_main="49.41",
        okved_title="Деятельность автомобильного грузового транспорта",
        registered_months_ago=36,
        registry_status="active",
        registry_head=DemoPerson("Прогрессов", "Павел", "Павлович"),
    ),
    DemoCompany(
        code="sboy",
        name="ООО «Сбой»",
        legal_form="LLC",
        inn="7705729405",
        ogrn="1067705557611",
        kpp="770501001",
        okved_main="46.90",
        okved_title="Торговля оптовая неспециализированная",
        registered_months_ago=60,
        registry_status="active",
        registry_head=DemoPerson("Сбоев", "Семён", "Семёнович"),
    ),
    # A startup (S-9): three months old, no turnover and no annual report yet.
    DemoCompany(
        code="start",
        name="ООО «Старт»",
        legal_form="LLC",
        inn="7706123455",
        ogrn="1267700123459",
        kpp="770601001",
        okved_main="62.01",
        okved_title="Разработка компьютерного программного обеспечения",
        registered_months_ago=3,
        registry_status="active",
        registry_head=DemoPerson("Стартов", "Степан", "Сергеевич"),
    ),
)

FINANCIALS: tuple[DemoFinancials, ...] = (
    DemoFinancials(
        "romashka",
        Decimal("48000000"),
        Decimal("40000000"),
        Decimal("41000000"),
        Decimal("47500000"),
        Decimal("0"),
        "1 кредит, платёж 180 000/мес, без просрочек",
        "ровный поток, разрыва нет",
    ),
    DemoFinancials(
        "ivanov",
        Decimal("6000000"),
        None,
        Decimal("4800000"),
        Decimal("5900000"),
        Decimal("0"),
        "истории нет",
        "неравномерные поступления, разрыв через 2 месяца",
    ),
    DemoFinancials(
        "vector",
        Decimal("30000000"),
        Decimal("27000000"),
        Decimal("26000000"),
        Decimal("29000000"),
        Decimal("0"),
        "2 кредита, без просрочек",
        "сезонность, небольшой разрыв зимой",
    ),
    DemoFinancials(
        "zakat",
        Decimal("20000000"),
        Decimal("24000000"),
        Decimal("21000000"),
        Decimal("18000000"),
        Decimal("350000"),
        "просрочка 120 дней",
        "падение поступлений",
    ),
    DemoFinancials(
        "progress",
        Decimal("36000000"),
        Decimal("30000000"),
        Decimal("30000000"),
        Decimal("12000000"),
        Decimal("0"),
        "1 кредит, без просрочек",
        "поступления около 1 млн в месяц",
    ),
    DemoFinancials(
        "sboy",
        Decimal("25000000"),
        Decimal("23000000"),
        Decimal("21000000"),
        Decimal("24000000"),
        Decimal("0"),
        "мок всегда отвечает 503",
        "ровный поток",
    ),
)

ACCOUNTS: tuple[DemoAccount, ...] = (
    DemoAccount(
        "owner@romashka.test",
        "+79990000001",
        DemoPerson("Смирнова", "Анна", "Сергеевна"),
        "client",
        "Директор ООО «Ромашка»",
        (DemoMembership("romashka", "director", "registry"),),
    ),
    DemoAccount(
        "accountant@romashka.test",
        "+79990000002",
        DemoPerson("Кузнецова", "Ольга", "Петровна"),
        "client",
        "Бухгалтер ООО «Ромашка» и ИП Иванова",
        (
            DemoMembership("romashka", "accountant", "unconfirmed"),
            DemoMembership("ivanov", "accountant", "unconfirmed"),
        ),
    ),
    DemoAccount(
        "ivanov@ip.test",
        "+79990000003",
        DemoPerson("Иванов", "Иван", "Иванович"),
        "client",
        "ИП Иванов",
        (DemoMembership("ivanov", "owner", "registry"),),
    ),
    DemoAccount(
        "petrov@vector.test",
        "+79990000004",
        DemoPerson("Петров", "Пётр", "Петрович"),
        "client",
        "Директор ООО «Вектор» (полномочие не подтверждено)",
        (DemoMembership("vector", "director", "unconfirmed"),),
    ),
    DemoAccount(
        "owner@zakat.test",
        "+79990000005",
        DemoPerson("Закатов", "Олег", "Олегович"),
        "client",
        "Директор ООО «Закат»",
        (DemoMembership("zakat", "director", "registry"),),
    ),
    DemoAccount(
        "owner@progress.test",
        "+79990000006",
        DemoPerson("Прогрессов", "Павел", "Павлович"),
        "client",
        "Директор ООО «Прогресс»",
        (DemoMembership("progress", "director", "registry"),),
    ),
    DemoAccount(
        "owner@sboy.test",
        "+79990000007",
        DemoPerson("Сбоев", "Семён", "Семёнович"),
        "client",
        "Директор ООО «Сбой»",
        (DemoMembership("sboy", "director", "registry"),),
    ),
    DemoAccount(
        "owner@start.test",
        "+79990000008",
        DemoPerson("Стартов", "Степан", "Сергеевич"),
        "client",
        "Учредитель и директор ООО «Старт» (стартап)",
        (DemoMembership("start", "director", "registry"),),
    ),
    DemoAccount(
        "underwriter@bank.test",
        "+79990000101",
        DemoPerson("Андеррайтеров", "Андрей"),
        "underwriter",
        "Андеррайтер",
    ),
)

PRODUCT_CODES: tuple[str, ...] = (
    "UNSECURED",
    "SECURED",
    "CREDIT_LINE",
    "OVERDRAFT",
    "AUTO",
    "MORTGAGE",
    "REFINANCE",
    "GOV_SUPPORT",
    "STARTUP",
)

COMPANIES_BY_CODE = {company.code: company for company in COMPANIES}
FINANCIALS_BY_CODE = {item.company_code: item for item in FINANCIALS}
ACCOUNTS_BY_EMAIL = {account.email: account for account in ACCOUNTS}
