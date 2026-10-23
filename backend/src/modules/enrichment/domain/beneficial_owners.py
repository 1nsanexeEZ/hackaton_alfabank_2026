"""Бенефициарные владельцы (ст. 3 и ст. 7 п. 1 подп. 2 115-ФЗ).

Бенефициар — физлицо, которое прямо или косвенно (через другие юрлица) владеет больше чем 25%
капитала клиента. Косвенная доля — произведение долей по цепочке, доли одного человека по разным
цепочкам складываются. Нет никого больше 25% — бенефициаром признаётся руководитель
(единоличный исполнительный орган). У ИП бенефициар — он сам.

Цепочку собирает слой application (запросы в ЕГРЮЛ по учредителям-юрлицам), здесь — только
расчёт. Чистые функции, `Decimal`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

BENEFICIAL_SHARE = Decimal(25)  # больше этой доли, % — бенефициар
MAX_DEPTH = 5  # уровней цепочки владения, дальше — не установить
_HUNDRED = Decimal(100)

Basis = Literal["ownership", "head_by_default", "entrepreneur"]


class OwnershipUnresolved(Exception):
    """Цепочку владения не установить: учредитель-юрлицо не найден, цикл или слишком глубоко."""


@dataclass(frozen=True, slots=True)
class Stake:
    """Доля в капитале: физлица — по ФИО, юрлица — с ИНН."""

    name: str
    share_percent: Decimal
    inn: str | None = None


@dataclass(frozen=True, slots=True)
class BeneficialOwner:
    name: str
    basis: Basis
    share_percent: Decimal | None = None


def person_shares(
    stakes: tuple[Stake, ...], companies: Mapping[str, tuple[Stake, ...]]
) -> dict[str, Decimal]:
    """Итоговая доля каждого физлица, %. `companies` — учредители каждого юрлица цепочки по ИНН."""
    shares: dict[str, Decimal] = {}
    _walk(stakes, Decimal(1), companies, shares, path=(), depth=0)
    return shares


def _walk(
    stakes: tuple[Stake, ...],
    weight: Decimal,
    companies: Mapping[str, tuple[Stake, ...]],
    shares: dict[str, Decimal],
    *,
    path: tuple[str, ...],
    depth: int,
) -> None:
    if depth >= MAX_DEPTH:
        raise OwnershipUnresolved(f"цепочка владения длиннее {MAX_DEPTH} уровней")
    for stake in stakes:
        portion = weight * stake.share_percent / _HUNDRED
        if stake.inn is None:
            shares[stake.name] = shares.get(stake.name, Decimal(0)) + portion * _HUNDRED
            continue
        if stake.inn in path:
            raise OwnershipUnresolved(f"цикл владения через ИНН {stake.inn}")
        owners = companies.get(stake.inn)
        if owners is None:
            raise OwnershipUnresolved(f"учредитель {stake.name} (ИНН {stake.inn}) не найден")
        _walk(owners, portion, companies, shares, path=(*path, stake.inn), depth=depth + 1)


def beneficial_owners(
    shares: Mapping[str, Decimal], *, head: str, entrepreneur: bool
) -> tuple[BeneficialOwner, ...]:
    """Больше 25% — бенефициары по доле, от большей к меньшей; никого — руководитель."""
    if entrepreneur:
        return (BeneficialOwner(head, "entrepreneur"),)
    owners = sorted(
        ((name, share) for name, share in shares.items() if share > BENEFICIAL_SHARE),
        key=lambda item: (-item[1], item[0]),
    )
    if not owners:
        return (BeneficialOwner(head, "head_by_default"),)
    return tuple(
        BeneficialOwner(name, "ownership", share.quantize(Decimal("0.01")))
        for name, share in owners
    )
