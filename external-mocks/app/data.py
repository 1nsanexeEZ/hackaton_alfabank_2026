"""Демо-компании (строго по 00-common.md §9.1–§9.2) и детерминированная генерация.

Ключи и единицы намеренно «чужие»: ЕГРЮЛ — кириллица, суммы — копейки целым числом,
даты — строки. ACL-адаптер в бэкенде переводит это в наши VO. Даты регистрации — относительно
сегодняшнего дня (`reg_days_ago`), остальные даты обязательств — фиксированные строки.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import date, timedelta

from app.inn import validate_inn


@dataclass(frozen=True)
class Obligation:
    kind: str  # loan | credit_line | overdraft | leasing | guarantee | mortgage | consumer | card
    creditor: str
    amount_kop: int
    outstanding_kop: int
    monthly_payment_kop: int
    opened: str
    closes: str
    overdue_days: int
    max_overdue_days: int


@dataclass(frozen=True)
class AccountBlock:
    """Решение ФНС о приостановлении операций по счетам."""

    decision_number: str
    date: str
    authority_code: str
    reason: str


@dataclass(frozen=True)
class Company:
    inn: str
    form: str  # ООО | АО | ИП
    name: str
    ogrn: str
    kpp: str | None
    okved: str
    status: str  # ACTIVE | LIQUIDATING | LIQUIDATED | BANKRUPT | REORGANIZING | EXCLUDED
    reg_days_ago: int
    head_fio: str
    head_position: str
    founders: tuple[tuple[str, int], ...]  # учредители-физлица: ФИО и доля, %
    address: str
    region_code: str
    mass_address: bool
    arrears_kop: int
    headcount: int
    revenue_kop: int
    expenses_kop: int
    tax_regime: str
    disqualified_head: bool
    msp_registry: bool
    bki_obligations: tuple[Obligation, ...]
    bki_inquiries_30d: int
    okved_extra: tuple[str, ...] = ()
    bki_no_history: bool = False
    account_blocks: tuple[AccountBlock, ...] = ()
    # Сколько дней назад внесена запись о нынешнем руководителе; None — с регистрации.
    head_days_ago: int | None = None
    # Учредители-юрлица: наименование, ИНН и доля, % — по ним банк идёт по цепочке владения.
    corporate_founders: tuple[tuple[str, str, int], ...] = ()
    # Отметки ЕГРЮЛ о недостоверности сведений: address | head | founder.
    unreliable: tuple[str, ...] = ()
    # ФНС «Прозрачный бизнес»: руководитель — массовый (руководит многими компаниями).
    mass_head: bool = False
    # Внутренний стоп-лист банка: причина, если компания в нём.
    bank_stop_list: str | None = None
    # Клиент банка столько дней (счёт открыт тогда); None — с регистрации.
    bank_client_days_ago: int | None = None


_RUB = 100  # копеек в рубле
_M = 1_000_000 * _RUB  # миллион рублей в копейках


DEMO: dict[str, Company] = {
    "7701158817": Company(
        inn="7701158817",
        form="ООО",
        name="Общество с ограниченной ответственностью «Ромашка»",
        ogrn="1027700399869",
        kpp="770101001",
        okved="56.10",
        status="ACTIVE",
        reg_days_ago=2190,
        head_fio="Смирнова Анна Сергеевна",
        head_position="Генеральный директор",
        founders=(("Смирнова Анна Сергеевна", 100),),
        address="г. Москва, ул. Тверская, д. 1",
        region_code="77",
        mass_address=False,
        arrears_kop=0,
        headcount=12,
        revenue_kop=475 * _M // 10,  # 47,5 млн
        expenses_kop=41 * _M,
        tax_regime="УСН",
        disqualified_head=False,
        msp_registry=True,
        bki_obligations=(
            Obligation(
                kind="loan",
                creditor="АО «Банк»",
                amount_kop=5 * _M,
                outstanding_kop=3 * _M,
                monthly_payment_kop=180_000 * _RUB,
                opened="2023-06-01",
                closes="2028-06-01",
                overdue_days=0,
                max_overdue_days=0,
            ),
        ),
        bki_inquiries_30d=1,
    ),
    "770669871605": Company(
        inn="770669871605",
        form="ИП",
        name="Индивидуальный предприниматель Иванов Иван Иванович",
        ogrn="325770689768464",
        kpp=None,
        okved="62.01",
        status="ACTIVE",
        reg_days_ago=243,
        head_fio="Иванов Иван Иванович",
        head_position="Индивидуальный предприниматель",
        founders=(),
        address="г. Москва",
        region_code="77",
        mass_address=False,
        arrears_kop=0,
        headcount=2,
        revenue_kop=59 * _M // 10,  # 5,9 млн
        expenses_kop=48 * _M // 10,  # 4,8 млн
        tax_regime="УСН",
        disqualified_head=False,
        msp_registry=True,
        bki_obligations=(),
        bki_inquiries_30d=0,
        bki_no_history=True,
    ),
    "7702987976": Company(
        inn="7702987976",
        form="ООО",
        name="Общество с ограниченной ответственностью «Вектор»",
        ogrn="1037702309116",
        kpp="770201001",
        okved="41.20",
        status="ACTIVE",
        reg_days_ago=1460,
        head_fio="Сидоров Сергей Сергеевич",  # ≠ заявленному в кабинете Петрову → расхождение
        head_position="Генеральный директор",
        founders=(("Сидоров Сергей Сергеевич", 100),),
        address="г. Москва, ш. Энтузиастов, д. 10",
        region_code="77",
        mass_address=False,
        arrears_kop=0,
        headcount=30,
        revenue_kop=29 * _M,
        expenses_kop=26 * _M,
        tax_regime="ОСН",
        disqualified_head=False,
        msp_registry=True,
        bki_obligations=(
            Obligation(
                "loan",
                "АО «Банк»",
                8 * _M,
                5 * _M,
                250_000 * _RUB,
                "2022-03-01",
                "2027-03-01",
                0,
                0,
            ),
            Obligation(
                "credit_line",
                "ПАО «Кредит»",
                4 * _M,
                1 * _M,
                90_000 * _RUB,
                "2024-01-01",
                "2026-01-01",
                0,
                0,
            ),
        ),
        bki_inquiries_30d=2,
    ),
    "7703417070": Company(
        inn="7703417070",
        form="ООО",
        name="Общество с ограниченной ответственностью «Закат»",
        ogrn="1047703536451",
        kpp="770301001",
        okved="47.19",
        status="LIQUIDATING",
        reg_days_ago=3285,
        head_fio="Закатов Олег Олегович",
        head_position="Генеральный директор",
        founders=(("Закатов Олег Олегович", 100),),
        address="г. Москва, ул. Закатная, д. 5",
        region_code="77",
        mass_address=False,
        arrears_kop=350_000 * _RUB,
        headcount=15,
        revenue_kop=18 * _M,
        expenses_kop=21 * _M,
        tax_regime="УСН",
        disqualified_head=False,
        msp_registry=True,
        bki_obligations=(
            Obligation(
                "loan",
                "АО «Банк»",
                10 * _M,
                8 * _M,
                300_000 * _RUB,
                "2021-01-01",
                "2026-01-01",
                120,
                120,
            ),
        ),
        bki_inquiries_30d=3,
        account_blocks=(
            AccountBlock(
                decision_number="4512",
                date="2026-09-30",
                authority_code="7703",
                reason="Неуплата налогов",
            ),
        ),
    ),
    "7704568152": Company(
        inn="7704568152",
        form="ООО",
        name="Общество с ограниченной ответственностью «Прогресс»",
        ogrn="1057704188442",
        kpp="770401001",
        okved="49.41",
        status="ACTIVE",
        reg_days_ago=1095,
        head_fio="Прогрессов Павел Павлович",
        head_position="Генеральный директор",
        founders=(("Прогрессов Павел Павлович", 100),),
        address="г. Москва, ул. Грузовая, д. 3",
        region_code="77",
        mass_address=False,
        arrears_kop=0,
        headcount=10,
        revenue_kop=12 * _M,  # ФНС 12 млн против заявленных 36 млн → расхождение выручки
        expenses_kop=9 * _M,
        tax_regime="УСН",
        disqualified_head=False,
        msp_registry=True,
        bki_obligations=(
            Obligation(
                "loan",
                "АО «Банк»",
                6 * _M,
                2 * _M,
                150_000 * _RUB,
                "2023-09-01",
                "2027-09-01",
                0,
                0,
            ),
        ),
        bki_inquiries_30d=1,
    ),
    "7705729405": Company(
        inn="7705729405",
        form="ООО",
        name="Общество с ограниченной ответственностью «Сбой»",
        ogrn="1067705557611",
        kpp="770501001",
        okved="46.90",
        status="ACTIVE",
        reg_days_ago=1825,
        head_fio="Сбоев Семён Семёнович",
        head_position="Генеральный директор",
        founders=(("Сбоев Семён Семёнович", 100),),
        address="г. Москва, ул. Оптовая, д. 7",
        region_code="77",
        mass_address=False,
        arrears_kop=0,
        headcount=20,
        revenue_kop=24 * _M,
        expenses_kop=21 * _M,
        tax_regime="ОСН",
        disqualified_head=False,
        msp_registry=True,
        bki_obligations=(  # БКИ для «Сбоя» всегда 503, но данные держим для полноты
            Obligation(
                "loan",
                "АО «Банк»",
                5 * _M,
                3 * _M,
                120_000 * _RUB,
                "2022-05-01",
                "2027-05-01",
                0,
                0,
            ),
        ),
        bki_inquiries_30d=1,
    ),
    # Стартап (S-9): три месяца, выручки и кредитной истории ещё нет.
    "7706123455": Company(
        inn="7706123455",
        form="ООО",
        name="Общество с ограниченной ответственностью «Старт»",
        ogrn="1267700123459",
        kpp="770601001",
        okved="62.01",
        status="ACTIVE",
        reg_days_ago=91,
        head_fio="Стартов Степан Сергеевич",
        head_position="Генеральный директор",
        founders=(("Стартов Степан Сергеевич", 100),),
        address="г. Москва, ул. Большая Новодмитровская, д. 36",
        region_code="77",
        mass_address=False,
        arrears_kop=0,
        headcount=3,
        revenue_kop=0,
        expenses_kop=0,
        tax_regime="УСН",
        disqualified_head=False,
        msp_registry=True,
        bki_obligations=(),
        bki_inquiries_30d=0,
        bki_no_history=True,
    ),
}


def _clean(
    inn: str,
    name: str,
    ogrn: str,
    head_fio: str,
    *,
    founders: tuple[tuple[str, int], ...] = (),
    corporate_founders: tuple[tuple[str, str, int], ...] = (),
    okved: str = "46.90",
) -> Company:
    """Компания для сценариев ПОД/ФТ: финансы и кредитная история чистые, чтобы решение
    определяли только проверки по 115-ФЗ (`app/compliance.py`)."""
    return Company(
        inn=inn,
        form="ООО",
        name=f"Общество с ограниченной ответственностью «{name}»",
        ogrn=ogrn,
        kpp=inn[:4] + "01001",
        okved=okved,
        status="ACTIVE",
        reg_days_ago=1460,
        head_fio=head_fio,
        head_position="Генеральный директор",
        founders=founders,
        corporate_founders=corporate_founders,
        address="г. Москва, ул. Складочная, д. 1",
        region_code="77",
        mass_address=False,
        arrears_kop=0,
        headcount=15,
        revenue_kop=30 * _M,
        expenses_kop=25 * _M,
        tax_regime="УСН",
        disqualified_head=False,
        msp_registry=True,
        bki_obligations=(),
        bki_inquiries_30d=0,
    )


# Компании для проверок по 115-ФЗ (`docs/compliance-115.md`): в сидах бэкенда их нет, жюри
# заводит их в кабинете по ИНН. Что с каждой не так — в `app/compliance.py`.
AML_DEMO: dict[str, Company] = {
    company.inn: company
    for company in (
        # Сама компания — в перечне причастных к экстремизму и терроризму.
        _clean(
            "7707115016",
            "Северный ветер",
            "1157707115015",
            "Ветров Виктор Викторович",
            founders=(("Ветров Виктор Викторович", 100),),
        ),
        # Руководитель — в решении МВК о замораживании.
        _clean(
            "7707115023",
            "Ледник",
            "1157707115026",
            "Морозов Максим Маркович",
            founders=(("Морозов Максим Маркович", 100),),
        ),
        # Бенефициар (75%) — иностранное публичное должностное лицо.
        _clean(
            "7707115030",
            "Посольский двор",
            "1157707115037",
            "Дворов Денис Дмитриевич",
            founders=(("Послов Пётр Павлович", 75), ("Дворов Денис Дмитриевич", 25)),
        ),
        # Платформа ЗСК: высокий уровень риска.
        _clean(
            "7707115048",
            "Транзит-Сервис",
            "1157707115048",
            "Транзитов Тимур Тимурович",
            founders=(("Транзитов Тимур Тимурович", 100),),
        ),
        # Платформа ЗСК: средний уровень риска.
        _clean(
            "7707115055",
            "Логистика Плюс",
            "1157707115059",
            "Логинов Лев Львович",
            founders=(("Логинов Лев Львович", 100),),
        ),
        # 80% у «Холдинга Восток», которым владеет лицо из перечня ФРОМУ: прямые учредители
        # чистые, бенефициар виден только по цепочке.
        _clean(
            "7707115062",
            "Северная дочка",
            "1157707115060",
            "Дочкин Дмитрий Данилович",
            founders=(("Дочкин Дмитрий Данилович", 20),),
            corporate_founders=(("ООО «Холдинг Восток»", "7707115070", 80),),
        ),
        _clean(
            "7707115070",
            "Холдинг Восток",
            "1157707115070",
            "Холдингов Харитон Харитонович",
            founders=(("Цепочкин Цезарь Цезаревич", 100),),
            okved="64.20",
        ),
        # Пять участников по 20%: никто не владеет больше 25% — бенефициаром признаётся
        # руководитель.
        _clean(
            "7707115087",
            "Пять партнёров",
            "1157707115081",
            "Партнёров Павел Петрович",
            founders=tuple((f"Партнёр № {i}", 20) for i in range(1, 6)),
        ),
    )
}


# Компании для стоп-факторов общей схемы, которых нет у демо-клиентов (`docs/modules/decision.md`,
# policy_v7): финансы и кредитная история чистые, отказ даёт только своё стоп-правило. Как и
# AML_DEMO, в сидах бэкенда их нет — жюри заводит их в кабинете по ИНН.
STOP_DEMO: dict[str, Company] = {
    company.inn: company
    for company in (
        # ЕГРЮЛ: идёт реорганизация.
        replace(
            _clean("7707146014", "Перестройка", "1157707146013", "Перестроев Пётр Павлович"),
            status="REORGANIZING",
        ),
        # ЕГРЮЛ: исключена из реестра как недействующая.
        replace(
            _clean("7707146021", "Тень", "1157707146024", "Тенев Тимофей Тарасович"),
            status="EXCLUDED",
        ),
        # ЕГРЮЛ: отметки о недостоверности адреса и руководителя.
        replace(
            _clean("7707146039", "Мираж", "1157707146035", "Миражов Марк Михайлович"),
            unreliable=("address", "head"),
        ),
        # ФНС: массовый руководитель.
        replace(
            _clean("7707146046", "Номинал", "1157707146046", "Номиналов Никита Никитич"),
            mass_head=True,
        ),
        # Внутренний стоп-лист банка.
        replace(
            _clean("7707146053", "Стоп-Трейд", "1157707146057", "Стопов Сергей Семёнович"),
            bank_stop_list="Подложные документы в заявке 2025 года",
        ),
    )
}


_GEN_OKVED = ("62.01", "56.10", "47.19", "41.20", "49.41", "46.90", "69.10", "86.10")
_GEN_STATUS = ("ACTIVE", "ACTIVE", "ACTIVE", "ACTIVE", "ACTIVE", "LIQUIDATING")


def _seed(inn: str) -> int:
    return int.from_bytes(hashlib.sha256(inn.encode()).digest()[:8], "big")


def generate_company(inn: str) -> Company:
    """Детерминированный профиль по хешу ИНН: тот же ИНН → тот же ответ."""
    s = _seed(inn)
    is_ie = len(inn) == 12
    status = _GEN_STATUS[s % len(_GEN_STATUS)]
    okved = _GEN_OKVED[(s >> 3) % len(_GEN_OKVED)]
    reg_days = 200 + (s >> 6) % 3600
    revenue_kop = (5 + (s >> 9) % 95) * _M
    arrears_kop = 0 if (s >> 15) % 4 else ((s >> 17) % 500_000) * _RUB
    headcount = 1 + (s >> 12) % 60
    overdue = 0 if (s >> 22) % 3 else (s >> 23) % 150
    obligations: tuple[Obligation, ...] = ()
    if (s >> 24) % 3:
        obligations = (
            Obligation(
                kind="loan",
                creditor="АО «Банк»",
                amount_kop=(1 + (s >> 25) % 10) * _M,
                outstanding_kop=(s >> 26) % 5 * _M,
                monthly_payment_kop=(50_000 + (s >> 27) % 200_000) * _RUB,
                opened="2023-01-01",
                closes="2028-01-01",
                overdue_days=overdue,
                max_overdue_days=overdue,
            ),
        )
    blocks: tuple[AccountBlock, ...] = ()
    if arrears_kop and (s >> 40) % 3 == 0:
        blocks = (
            AccountBlock(
                decision_number=str(1000 + (s >> 41) % 9000),
                date="2026-09-15",
                authority_code=inn[:4],
                reason="Неуплата налогов",
            ),
        )
    suffix = inn[-4:]
    # Каждая восьмая компания недавно сменила руководителя (1–6 месяцев назад).
    head_days_ago = 30 + (s >> 43) % 150 if (s >> 42) % 8 == 0 else None
    # Каждая десятая перешла в банк недавно (2–5 месяцев назад): оборотов в банке меньше полугода.
    bank_days_ago = 60 + (s >> 50) % 90 if (s >> 49) % 10 == 0 else None
    return Company(
        inn=inn,
        form="ИП" if is_ie else "ООО",
        name=(
            f"Индивидуальный предприниматель № {suffix}"
            if is_ie
            else f"Общество с ограниченной ответственностью № {suffix}"
        ),
        ogrn=("3" + inn[:14]).ljust(15, "0") if is_ie else ("1" + inn[:12]).ljust(13, "0"),
        kpp=None if is_ie else inn[:4] + "01001",
        okved=okved,
        status=status,
        reg_days_ago=reg_days,
        head_fio=f"Руководитель № {suffix}",
        head_position="Индивидуальный предприниматель" if is_ie else "Генеральный директор",
        founders=() if is_ie else ((f"Учредитель № {suffix}", 100),),
        address="г. Москва",
        region_code="77",
        mass_address=(s >> 21) % 15 == 0,
        arrears_kop=arrears_kop,
        headcount=headcount,
        revenue_kop=revenue_kop,
        expenses_kop=int(revenue_kop * 0.8),
        tax_regime="УСН" if revenue_kop <= 200 * _M else "ОСН",
        disqualified_head=(s >> 20) % 20 == 0,
        msp_registry=revenue_kop <= 2000 * _M,
        bki_obligations=obligations,
        bki_inquiries_30d=(s >> 28) % 6,
        account_blocks=blocks,
        head_days_ago=min(head_days_ago, reg_days) if head_days_ago is not None else None,
        bank_client_days_ago=min(bank_days_ago, reg_days) if bank_days_ago is not None else None,
    )


def get_company(inn: str) -> Company | None:
    """Демо-компания, иначе детерминированная генерация; невалидный ИНН → None (404)."""
    if inn in DEMO:
        return DEMO[inn]
    if inn in AML_DEMO:
        return AML_DEMO[inn]
    if inn in STOP_DEMO:
        return STOP_DEMO[inn]
    if not validate_inn(inn):
        return None
    return generate_company(inn)


def _reg_date(company: Company) -> str:
    return (date.today() - timedelta(days=company.reg_days_ago)).isoformat()


def _head_date(company: Company) -> str:
    if company.head_days_ago is None:
        return _reg_date(company)
    return (date.today() - timedelta(days=company.head_days_ago)).isoformat()


_UNRELIABLE = {"address": "Адрес", "head": "Руководитель", "founder": "Учредитель"}


def egrul_response(company: Company) -> dict:
    data: dict = {
        "ИНН": company.inn,
        "ОГРН": company.ogrn,
        "НаимПолн": company.name,
        "Статус": {"Код": company.status},
        "ДатаРег": _reg_date(company),
        "ОКВЭДОсн": {"Код": company.okved},
        "ОКВЭДДоп": [{"Код": code} for code in company.okved_extra],
        "Руководитель": {
            "ФИО": company.head_fio,
            "Должность": company.head_position,
            "ДатаЗаписи": _head_date(company),
        },
        "Учредители": [
            *({"ФИО": fio, "Доля": share} for fio, share in company.founders),
            *(
                {"Наим": name, "ИНН": inn, "Доля": share}
                for name, inn, share in company.corporate_founders
            ),
        ],
        "Адрес": {"Полный": company.address, "КодРегиона": company.region_code},
        "МассовыйАдрес": company.mass_address,
        "ОрганизационнаяФорма": company.form,
        # Записи о недостоверности сведений (по результатам проверки налоговым органом).
        "СведНедостоверн": [
            {"Сведения": _UNRELIABLE[kind], "ДатаЗаписи": _reg_date(company)}
            for kind in company.unreliable
        ],
    }
    if company.kpp:
        data["КПП"] = company.kpp
    return data


def fns_response(company: Company) -> dict:
    return {
        "inn": company.inn,
        "arrears_kop": company.arrears_kop,
        "avg_headcount": company.headcount,
        "revenue_kop": company.revenue_kop,
        "expenses_kop": company.expenses_kop,
        "tax_regime": company.tax_regime,
        "disqualified_head": company.disqualified_head,
        "mass_head": company.mass_head,
        "msp_registry": company.msp_registry,
        "report_year": date.today().year - 1,
        "account_blocks": [
            {
                "decision_number": block.decision_number,
                "date": block.date,
                "authority_code": block.authority_code,
                "reason": block.reason,
            }
            for block in company.account_blocks
        ],
    }


_TURNOVER_MONTHS = 24


def _month_back(today: date, months: int) -> date:
    """Первое число месяца, отстоящего от текущего на `months` назад."""
    index = today.year * 12 + today.month - 1 - months
    return date(index // 12, index % 12 + 1, 1)


def _wobble(inn: str, month: str, salt: str) -> float:
    """Детерминированное колебание ±8% по ИНН и месяцу."""
    digest = hashlib.sha256(f"{inn}:{month}:{salt}".encode()).digest()
    return (digest[0] / 255 - 0.5) * 0.16


def bank_accounts_response(company: Company) -> dict:
    """АБС: клиент банка с какой даты и обороты по его расчётному счёту — по месяцам за 24
    полных месяца (без текущего), не раньше открытия счёта. Поступления — около выручки / 12,
    списания — около расходов / 12."""
    today = date.today()
    client_days = (
        company.bank_client_days_ago
        if company.bank_client_days_ago is not None
        else company.reg_days_ago
    )
    client_since = today - timedelta(days=client_days)
    opened = date(client_since.year, client_since.month, 1)
    months = []
    for back in range(_TURNOVER_MONTHS, 0, -1):
        start = _month_back(today, back)
        if start < opened:
            continue
        month = start.strftime("%Y-%m")
        credit = int(company.revenue_kop / 12 * (1 + _wobble(company.inn, month, "in")))
        debit = int(company.expenses_kop / 12 * (1 + _wobble(company.inn, month, "out")))
        months.append({"month": month, "credit_kop": credit, "debit_kop": debit})
    return {
        "inn": company.inn,
        "client_since": client_since.isoformat(),
        "turnover": months,
        "simulated": True,
    }


def bank_stop_list_response(company: Company) -> dict:
    """Внутренний стоп-лист банка (АБС): компания в нём или нет и почему."""
    listed = company.bank_stop_list is not None
    return {
        "inn": company.inn,
        "listed": listed,
        "reason": company.bank_stop_list,
        "listed_at": _reg_date(company) if listed else None,
    }


def obligations_response(obligations: tuple[Obligation, ...]) -> list[dict]:
    return [
        {
            "type": o.kind,
            "creditor": o.creditor,
            "amount_kop": o.amount_kop,
            "outstanding_kop": o.outstanding_kop,
            "monthly_payment_kop": o.monthly_payment_kop,
            "opened": o.opened,
            "closes": o.closes,
            "overdue_days": o.overdue_days,
            "max_overdue_days": o.max_overdue_days,
        }
        for o in obligations
    ]


def bki_response(company: Company) -> dict:
    return {
        "obligations": obligations_response(company.bki_obligations),
        "inquiries_30d": company.bki_inquiries_30d,
    }
