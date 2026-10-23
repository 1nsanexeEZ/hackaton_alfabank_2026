"""Политика и тексты из YAML: валидный конфиг грузится, любая дыра — ошибка при старте."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import fields, replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.modules.decision.config import DecisionSettings
from src.modules.decision.domain.model import ReasonCode
from src.modules.decision.facade import ClientDecisionDTO, DecisionDTO
from src.modules.decision.infrastructure.config_loader import (
    PolicyConfigError,
    default_policy,
    load_policy,
    load_policy_files,
)

_BACKEND = Path(__file__).resolve().parents[3]
_CONFIG = _BACKEND / "src" / "modules" / "decision" / "infrastructure" / "config"


def _raw(name: str) -> dict[str, Any]:
    return yaml.safe_load((_CONFIG / f"{name}.yaml").read_text(encoding="utf-8"))


def _load(
    tmp_path: Path,
    policy: Callable[[dict[str, Any]], None] | None = None,
    texts: Callable[[dict[str, Any]], None] | None = None,
    version: str = "policy_v1",
) -> None:
    raw_policy, raw_texts = _raw(version), _raw("explanations_ru")
    if policy is not None:
        policy(raw_policy)
    if texts is not None:
        texts(raw_texts)
    policy_path, texts_path = tmp_path / "policy.yaml", tmp_path / "texts.yaml"
    policy_path.write_text(yaml.safe_dump(raw_policy, allow_unicode=True), encoding="utf-8")
    texts_path.write_text(yaml.safe_dump(raw_texts, allow_unicode=True), encoding="utf-8")
    load_policy_files(policy_path, texts_path)


def test_default_policy_loads() -> None:
    policy = default_policy()
    assert policy.version == "policy_v4"
    assert policy.config.startup_products == frozenset({"STARTUP"})
    assert policy.config.key_rate_reference == Decimal("16.50")
    assert policy.config.offer_valid_days == 7
    assert policy.config.grade_scale == tuple("ABCDEFGHIJ")
    assert policy.config.revenue_multiplier["C"] == Decimal("0.4")


def test_v4_keeps_the_v3_strategy_and_adds_the_startup_branch() -> None:
    v3, v4 = load_policy("policy_v3").config, default_policy().config
    assert v3.startup_products == frozenset()
    assert v4.startup_products == frozenset({"STARTUP"})
    assert replace(v4, version=v3.version, startup_products=frozenset()) == v3


def test_v3_strategy_lives_in_yaml() -> None:
    config = load_policy("policy_v3").config
    assert [band.label for band in config.risk_matrix] == ["A–C", "D–E", "F–G", "H–J"]
    assert config.band("E") is not None and config.band("E").approve_up_to == Decimal("15000000")
    assert config.trigger_tax_arrears and config.trigger_head_change_months == 6
    assert (config.trigger_turnover_months, config.trigger_turnover_ratio) == (3, Decimal("1.5"))
    assert config.turnover_multiplier == Decimal("0.5")
    assert config.grade_max_amount["J"] == Decimal(0)
    assert config.group_exposure_max == Decimal("100000000")
    assert config.rate_components is not None
    assert config.rate_components.lgd_unsecured == Decimal("0.45")
    assert config.guarantee_grades == frozenset({"F", "G"})
    # Грейд отсекает матрица, а не стоп-фактор и не маршрут по грейду.
    assert config.stop_grades == frozenset() and config.manual_review_grades == frozenset()
    assert not config.route_tax_arrears


def test_v2_thresholds_live_in_yaml() -> None:
    config = load_policy("policy_v2").config
    assert config.stop_current_overdue_days == 30
    assert config.stop_tax_arrears_above == Decimal("300000")
    assert config.stop_enforcement_share == Decimal("0.1")
    assert config.stop_lawsuits_share == Decimal("0.2")
    assert config.stop_okved_classes == frozenset({"92"})
    assert config.stop_account_blocks and config.stop_bankruptcy_messages
    assert config.stop_negative_equity and config.stop_mass_address and config.route_tax_arrears


def test_v1_keeps_new_rules_off() -> None:
    config = load_policy("policy_v1").config
    assert config.stop_current_overdue_days is None
    assert config.stop_tax_arrears_above is None
    assert config.stop_enforcement_share is None and config.stop_lawsuits_share is None
    assert config.stop_okved_classes == frozenset()
    assert not (config.stop_account_blocks or config.stop_bankruptcy_messages)
    assert not (config.stop_negative_equity or config.stop_mass_address)
    assert not config.route_tax_arrears


@pytest.mark.parametrize("version", ["policy_v1", "policy_v2"])
def test_earlier_versions_keep_v3_rules_off(version: str) -> None:
    config = load_policy(version).config
    assert config.grade_scale == tuple("ABCDE")
    assert config.risk_matrix == () and config.rate_components is None
    assert not config.full_limits and not config.trigger_tax_arrears
    assert config.trigger_head_change_months is None and config.trigger_turnover_ratio is None
    assert config.guarantee_grades == frozenset() and config.guarantee_amount_above is None


@pytest.mark.parametrize("version", ["policy_v1", "policy_v2", "policy_v3", "policy_v4"])
def test_roundtrip_of_shipped_files_is_valid(tmp_path: Path, version: str) -> None:
    _load(tmp_path, version=version)


@pytest.mark.parametrize(
    "breaks",
    [
        lambda p: p.update({"grades": ["A", "B", "C"]}),
        lambda p: p["limits"]["revenue_multiplier"].pop("J"),
        lambda p: p["limits"]["grade_max_amount"].pop("F"),
        lambda p: p["strategy"]["risk_matrix"].pop(),
        lambda p: p["strategy"]["risk_matrix"][0]["grades"].append("D"),
        lambda p: p["strategy"]["risk_matrix"][1].update({"manual_up_to": "1000000"}),
        lambda p: p["strategy"]["guarantee"].update({"grades": ["Z"]}),
        lambda p: p["strategy"]["soft_triggers"]["turnover_spike"].update({"ratio": "1"}),
        lambda p: p["pricing"]["components"].update({"lgd_unsecured": "1.5"}),
        lambda p: p["pricing"].pop("components"),  # без компонент нужна надбавка за грейд
    ],
)
def test_invalid_v3_strategy_is_rejected(
    tmp_path: Path, breaks: Callable[[dict[str, Any]], None]
) -> None:
    with pytest.raises(PolicyConfigError):
        _load(tmp_path, policy=breaks, version="policy_v3")


@pytest.mark.parametrize(
    "breaks",
    [
        lambda p: p["stop_factors"].update({"okved_classes": ["9"]}),
        lambda p: p["stop_factors"].update({"okved_classes": ["92.1"]}),
        lambda p: p["stop_factors"].update({"enforcement_revenue_share": "1.5"}),
        lambda p: p["stop_factors"].update({"lawsuits_revenue_share": "0"}),
        lambda p: p["stop_factors"].update({"current_overdue_days": 0}),
        lambda p: p["stop_factors"].update({"tax_arrears_above": "-1"}),
    ],
)
def test_invalid_v2_thresholds_are_rejected(
    tmp_path: Path, breaks: Callable[[dict[str, Any]], None]
) -> None:
    with pytest.raises(PolicyConfigError):
        _load(tmp_path, policy=breaks, version="policy_v2")


def test_default_key_rate_matches_policy_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    """Каталог откалиброван под опорную ставку: по умолчанию ставки не сдвигаются."""
    monkeypatch.delenv("DECISION_KEY_RATE", raising=False)
    settings = DecisionSettings(_env_file=None)  # type: ignore[call-arg]
    assert settings.key_rate == default_policy().config.key_rate_reference


def test_key_rate_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECISION_KEY_RATE", "18.25")
    assert DecisionSettings(_env_file=None).key_rate == Decimal("18.25")  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "breaks",
    [
        lambda p: p["limits"]["revenue_multiplier"].pop("D"),
        lambda p: p["pricing"]["grade_premium"].pop("A"),
        lambda p: p["routing"]["flags"].update({"thin_file": "ROUTE_THIN_FILE"}),
        lambda p: p["stop_factors"]["registry_statuses"].update({"active": "STOP_UNKNOWN"}),
        lambda p: p["limits"].update({"payment_share": "1.5"}),
        lambda p: p.pop("key_rate_reference"),
        lambda p: p.update({"unexpected": True}),
        lambda p: p["alternatives"].update({"cash_gap_products": ["FACTORING"]}),
    ],
)
def test_invalid_policy_is_rejected(
    tmp_path: Path, breaks: Callable[[dict[str, Any]], None]
) -> None:
    with pytest.raises(PolicyConfigError):
        _load(tmp_path, policy=breaks)


@pytest.mark.parametrize(
    "breaks",
    [
        lambda t: t["reasons"].pop(ReasonCode.STOP_LIQUIDATION.value),
        lambda t: t["outcomes"].pop("COUNTER_OFFER"),
        lambda t: t["notes"].pop("alternative"),
        lambda t: t["conditions"].pop("cash_gap"),
        lambda t: t["reasons"][ReasonCode.LIMIT_BY_REVENUE.value].update({"text": "{score}"}),
        lambda t: t["collateral_types"].pop("vehicle"),
    ],
)
def test_invalid_explanations_are_rejected(
    tmp_path: Path, breaks: Callable[[dict[str, Any]], None]
) -> None:
    with pytest.raises(PolicyConfigError):
        _load(tmp_path, texts=breaks)


def test_broken_yaml_is_rejected(tmp_path: Path) -> None:
    broken = tmp_path / "policy.yaml"
    broken.write_text("version: [unclosed", encoding="utf-8")
    with pytest.raises(PolicyConfigError):
        load_policy_files(broken, _CONFIG / "explanations_ru.yaml")


def test_client_contract_has_no_internal_fields() -> None:
    """Граница раскрытия: клиентский DTO физически не несёт причин и трассы правил."""
    client = {f.name for f in fields(ClientDecisionDTO)}
    bank = {f.name for f in fields(DecisionDTO)}
    internal = {"reason_codes", "rule_trace", "limits", "key_rate", "policy_version"}
    assert internal <= bank
    assert not internal & client
