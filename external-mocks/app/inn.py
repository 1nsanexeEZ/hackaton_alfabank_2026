"""Проверка контрольных цифр ИНН (10 знаков — юрлицо, 12 — ИП/физлицо)."""

from __future__ import annotations


def _control_digit(digits: list[int], weights: list[int]) -> int:
    return sum(d * w for d, w in zip(digits, weights, strict=False)) % 11 % 10


def validate_inn(inn: str) -> bool:
    """True, если строка — корректный ИНН с верными контрольными цифрами."""
    if not inn.isdigit():
        return False
    digits = [int(ch) for ch in inn]
    if len(inn) == 10:
        return digits[9] == _control_digit(digits[:9], [2, 4, 10, 3, 5, 9, 4, 6, 8])
    if len(inn) == 12:
        n11 = _control_digit(digits[:10], [7, 2, 4, 10, 3, 5, 9, 4, 6, 8])
        n12 = _control_digit(digits[:11], [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8])
        return digits[10] == n11 and digits[11] == n12
    return False
