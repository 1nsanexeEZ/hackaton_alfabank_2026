"""Политика и тексты из YAML: валидный конфиг грузится, любая дыра — ошибка при старте."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import fields
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.decision.config import DecisionSettings
from src.decision.domain.model import ReasonCode
from src.decision.facade import ClientDecisionDTO, DecisionDTO
from src.decision.infrastructure.config_loader import (
    PolicyConfigError,
    default_policy,
    load_policy_files,
)

_CONFIG = Path(__file__).resolve().parents[3] / "src" / "decision" / "infrastructure" / "config"


def _raw(name: str) -> dict[str, Any]:
    return yaml.safe_load((_CONFIG / f"{name}.yaml").read_text(encoding="utf-8"))


def _load(
    tmp_path: Path,
    policy: Callable[[dict[str, Any]], None] | None = None,
    texts: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    raw_policy, raw_texts = _raw("policy_v1"), _raw("explanations_ru")
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
    assert policy.version == "policy_v1"
    assert policy.config.key_rate_reference == Decimal("16.50")
    assert policy.config.offer_valid_days == 7
    assert policy.config.revenue_multiplier["C"] == Decimal("0.25")


def test_roundtrip_of_shipped_files_is_valid(tmp_path: Path) -> None:
    _load(tmp_path)


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
