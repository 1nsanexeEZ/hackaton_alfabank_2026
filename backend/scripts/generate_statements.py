"""Генерация синтетических выписок по счёту для демо-компаний (§9.2).

Детерминированный (без случайности): тот же запуск → те же файлы. Пишет
`backend/seed/statements/<код>.csv`, 12 месяцев, формат:
`date;amount;counterparty_inn;counterparty_name;purpose` (поступление > 0, списание < 0).

Запуск: `uv run python -m scripts.generate_statements`
"""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

_OUT_DIR = Path(__file__).resolve().parent.parent / "seed" / "statements"

# 12 месяцев: октябрь 2025 … сентябрь 2026.
_MONTHS: list[tuple[int, int]] = [
    (2025, 10),
    (2025, 11),
    (2025, 12),
    (2026, 1),
    (2026, 2),
    (2026, 3),
    (2026, 4),
    (2026, 5),
    (2026, 6),
    (2026, 7),
    (2026, 8),
    (2026, 9),
]

# Помесячные поступления и списания в рублях (ровно под профили §9.2).
_PROFILES: dict[str, tuple[list[int], list[int]]] = {
    # ровный поток, годовой оборот 48 млн — подтверждает заявленную выручку, разрыва нет
    "romashka": ([4_000_000] * 12, [3_400_000] * 12),
    # неравномерные поступления, оборот ~6 млн — с новым кредитом прогноз уходит в разрыв
    "ivanov": (
        [
            1_000_000,
            200_000,
            800_000,
            100_000,
            900_000,
            300_000,
            700_000,
            200_000,
            600_000,
            400_000,
            500_000,
            300_000,
        ],
        [400_000] * 12,
    ),
    # сезонность: зимой поступления падают
    "vector": (
        [
            3_000_000,
            2_500_000,
            1_500_000,
            1_000_000,
            1_500_000,
            2_000_000,
            2_500_000,
            3_000_000,
            3_500_000,
            3_500_000,
            3_000_000,
            3_000_000,
        ],
        [2_000_000] * 12,
    ),
    # падение поступлений
    "zakat": (
        [
            2_500_000,
            2_300_000,
            2_100_000,
            1_900_000,
            1_700_000,
            1_500_000,
            1_500_000,
            1_300_000,
            1_200_000,
            1_100_000,
            1_000_000,
            900_000,
        ],
        [1_750_000] * 12,
    ),
    # поступления ~1 млн/мес (оборот 12 млн) подтверждают ФНС, а не заявленные 36 млн
    "progress": ([1_000_000] * 12, [750_000] * 12),
    # ровный поток
    "sboy": ([2_000_000] * 12, [1_750_000] * 12),
}


def _rows_for_month(year: int, month: int, inflow: int, outflow: int) -> list[list[str]]:
    inflow_1 = (Decimal(inflow) * 6 // 10).quantize(Decimal("1"))
    inflow_2 = Decimal(inflow) - inflow_1
    rent = (Decimal(outflow) * 3 // 10).quantize(Decimal("1"))
    salary = (Decimal(outflow) * 4 // 10).quantize(Decimal("1"))
    suppliers = Decimal(outflow) - rent - salary

    def line(day: int, amount: Decimal, inn: str, name: str, purpose: str) -> list[str]:
        return [f"{year:04d}-{month:02d}-{day:02d}", f"{amount:.2f}", inn, name, purpose]

    return [
        line(5, inflow_1, "7708123456", "ООО «Покупатель-1»", "Оплата по счёту"),
        line(20, inflow_2, "7709234567", "ООО «Покупатель-2»", "Оплата по счёту"),
        line(10, -rent, "7710345678", "ООО «Аренда»", "Аренда помещения"),
        line(15, -salary, "", "Зарплата сотрудникам", "Выплата зарплаты"),
        line(25, -suppliers, "7711456789", "ООО «Поставщик»", "Оплата поставщику"),
    ]


def main() -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    for code, (inflows, outflows) in _PROFILES.items():
        path = _OUT_DIR / f"{code}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(["date", "amount", "counterparty_inn", "counterparty_name", "purpose"])
            for (year, month), inflow, outflow in zip(_MONTHS, inflows, outflows, strict=True):
                writer.writerows(_rows_for_month(year, month, inflow, outflow))
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
