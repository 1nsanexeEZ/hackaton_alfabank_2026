"""Бенефициары по 115-ФЗ: больше 25% прямо или по цепочке, иначе — руководитель."""

from decimal import Decimal

import pytest

from src.modules.enrichment.domain.beneficial_owners import (
    BeneficialOwner,
    OwnershipUnresolved,
    Stake,
    beneficial_owners,
    person_shares,
)

D = Decimal


def test_direct_owner_above_a_quarter() -> None:
    shares = person_shares((Stake("Иванов", D(75)), Stake("Петров", D(25))), {})
    assert beneficial_owners(shares, head="Петров", entrepreneur=False) == (
        BeneficialOwner("Иванов", "ownership", D("75.00")),
    )


def test_exactly_a_quarter_is_not_enough() -> None:
    """Порог — больше 25%: ровно 25% бенефициаром не делает."""
    shares = person_shares(tuple(Stake(f"У{i}", D(25)) for i in range(4)), {})
    assert beneficial_owners(shares, head="Руководитель", entrepreneur=False) == (
        BeneficialOwner("Руководитель", "head_by_default"),
    )


def test_indirect_share_through_a_company() -> None:
    """80% у холдинга, холдингом на 100% владеет человек — у него 80% косвенно."""
    stakes = (Stake("Дочкин", D(20)), Stake("Холдинг", D(80), inn="7707115070"))
    shares = person_shares(stakes, {"7707115070": (Stake("Цепочкин", D(100)),)})
    assert shares == {"Дочкин": D(20), "Цепочкин": D(80)}
    assert beneficial_owners(shares, head="Дочкин", entrepreneur=False) == (
        BeneficialOwner("Цепочкин", "ownership", D("80.00")),
    )


def test_shares_by_different_chains_add_up() -> None:
    """20% напрямую и 50% × 40% через компанию — итого 40%."""
    stakes = (Stake("Сидоров", D(20)), Stake("ООО", D(50), inn="1"))
    shares = person_shares(stakes, {"1": (Stake("Сидоров", D(40)), Stake("Другой", D(60)))})
    assert shares["Сидоров"] == D(40)
    owners = beneficial_owners(shares, head="Х", entrepreneur=False)
    assert [o.name for o in owners] == ["Сидоров", "Другой"]  # 40% и 30%


def test_an_entrepreneur_is_their_own_owner() -> None:
    assert beneficial_owners({}, head="Иванов Иван", entrepreneur=True) == (
        BeneficialOwner("Иванов Иван", "entrepreneur"),
    )


def test_unknown_company_in_the_chain() -> None:
    with pytest.raises(OwnershipUnresolved, match="не найден"):
        person_shares((Stake("ООО", D(100), inn="1"),), {})


def test_a_cycle_is_unresolved() -> None:
    companies = {"1": (Stake("Б", D(100), inn="2"),), "2": (Stake("А", D(100), inn="1"),)}
    with pytest.raises(OwnershipUnresolved, match="цикл"):
        person_shares((Stake("А", D(100), inn="1"),), companies)
