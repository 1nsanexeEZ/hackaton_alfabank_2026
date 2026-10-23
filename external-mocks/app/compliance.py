"""Проверки по 115-ФЗ: перечни Росфинмониторинга, база публичных должностных лиц и уровень
риска на платформе «Знай своего клиента» (ЗСК) Банка России.

Три разные системы со своим форматом:
- перечни Росфинмониторинга (ст. 6, 7 115-ФЗ): причастные к экстремизму и терроризму, решения
  межведомственной комиссии (МВК) о замораживании, перечень по распространению оружия массового
  уничтожения (ФРОМУ). Банк сверяет компанию, руководителя, бенефициаров и представителей;
- база ПДЛ (ст. 7.3): иностранные, российские и должностные лица международных организаций —
  у банков это коммерческая база, а не реестр государства;
- ЗСК (ст. 7.6): уровень риска юрлица или ИП — низкий, средний или высокий.

Все записи синтетические. Демо-компании бэкенда (`DEMO`) чистые; сценарии — у компаний
`AML_DEMO`; у сгенерированных ИНН и сгенерированных ФИО — детерминированно по хешу.
"""

from __future__ import annotations

import hashlib
from datetime import date

from app.data import AML_DEMO, DEMO, Company

# Перечень → код в ответе Росфинмониторинга.
TERRORISM = "ЭКСТРЕМИЗМ_ТЕРРОРИЗМ"
FREEZE = "МВК"
WMD = "ФРОМУ"

LISTED_ORGANIZATIONS: dict[str, tuple[str, str]] = {
    "7707115016": (TERRORISM, "ЮЛ-2026-00317"),
}
LISTED_PERSONS: dict[str, tuple[str, str]] = {
    "морозов максим маркович": (FREEZE, "МВК-2026-0117"),
    "цепочкин цезарь цезаревич": (WMD, "ФРОМУ-2025-0042"),
}
# ИПДЛ — иностранное, РПДЛ — российское, МПДЛ — должностное лицо международной организации.
PEP_PERSONS: dict[str, tuple[str, str]] = {
    "послов пётр павлович": ("ИПДЛ", "Посол иностранного государства"),
}
ZSK_LEVELS: dict[str, str] = {
    "7707115048": "ВЫСОКИЙ",
    "7707115055": "СРЕДНИЙ",
}
# ФИО, которые генерирует мок для неизвестных ИНН: только у них совпадения «по хешу».
_GENERATED_NAMES = ("руководитель № ", "учредитель № ")


def normalize(fio: str) -> str:
    """Сверка ФИО: регистр, «ё», лишние пробелы."""
    return " ".join(fio.lower().replace("ё", "е").split())


def _seed(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")


def _generated(fio: str) -> bool:
    return normalize(fio).startswith(_GENERATED_NAMES)


_LISTED = {normalize(fio): hit for fio, hit in LISTED_PERSONS.items()}
_PEP = {normalize(fio): hit for fio, hit in PEP_PERSONS.items()}


def screen_organization(inn: str | None) -> list[dict]:
    if inn is None:
        return []
    hit = LISTED_ORGANIZATIONS.get(inn)
    if hit is not None:
        return [{"Перечень": hit[0], "НомерЗаписи": hit[1]}]
    if inn in DEMO or inn in AML_DEMO:
        return []
    # Каждая двухсотая сгенерированная компания — в перечне.
    if _seed("rfm:" + inn) % 200 == 0:
        return [{"Перечень": TERRORISM, "НомерЗаписи": f"ЮЛ-{inn[-6:]}"}]
    return []


def screen_person(fio: str) -> list[dict]:
    hit = _LISTED.get(normalize(fio))
    if hit is not None:
        return [{"Перечень": hit[0], "НомерЗаписи": hit[1]}]
    if _generated(fio) and _seed("rfm:" + normalize(fio)) % 100 == 0:
        return [{"Перечень": FREEZE, "НомерЗаписи": f"МВК-{_seed(fio) % 10_000:04d}"}]
    return []


def pep_status(fio: str) -> dict | None:
    hit = _PEP.get(normalize(fio))
    if hit is not None:
        return {"Категория": hit[0], "Должность": hit[1]}
    if _generated(fio) and _seed("pep:" + normalize(fio)) % 30 == 0:
        return {"Категория": "РПДЛ", "Должность": "Депутат законодательного собрания субъекта РФ"}
    return None


def zsk_level(company: Company) -> str:
    level = ZSK_LEVELS.get(company.inn)
    if level is not None:
        return level
    if company.inn in DEMO or company.inn in AML_DEMO:
        return "НИЗКИЙ"
    s = _seed("zsk:" + company.inn)
    if s % 40 == 0:
        return "ВЫСОКИЙ"
    if s % 8 == 1:
        return "СРЕДНИЙ"
    return "НИЗКИЙ"


def lists_date() -> str:
    """Перечни обновляются ежедневно — версия на сегодня."""
    return date.today().isoformat()
