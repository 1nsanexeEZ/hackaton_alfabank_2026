"""Правила policy_v8: третьи лица по 115-ФЗ.

- Выгодоприобретатель или залогодатель в перечне — отказ, как у всех участников проверки.
- Клиент действует к выгоде третьего лица — ручная проверка.
- Нет ответа о выгодоприобретателе или у залога третьего лица нет владельца — ручная проверка,
  только с `require_answers: true` (пока форма заявки не спрашивает, ключ выключен).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from src.modules.decision.domain.model import (
    AmlHit,
    AmlInput,
    DecisionInput,
    PolicyDecision,
    ReasonCode,
    ThirdPartiesInput,
)
from src.modules.decision.domain.policy import CreditPolicy
from src.modules.decision.facade import review_kind
from src.modules.decision.infrastructure.config_loader import (
    PolicyConfigError,
    load_policy,
    load_policy_files,
)
from tests.decision.unit.test_credit_policy_v3_rules import hit
from tests.decision.unit.test_credit_policy_v6_rules import CLEAN
from tests.decision.unit.test_credit_policy_v7_rules import v7

_CONFIG = Path(__file__).resolve().parents[3] / "src/modules/decision/infrastructure/config"
POLICY = load_policy("policy_v8")
KEY_RATE = POLICY.config.key_rate_reference
ANSWERED_NO = ThirdPartiesInput(beneficiary="none")
AGENT = ThirdPartiesInput(
    beneficiary="declared",
    beneficiary_name="ООО «Транзитный агент», ИНН 7707115094",
    basis="agency",
)


def v8(**overrides: Any) -> DecisionInput:
    """Заявка без замечаний, клиент ответил, что действует к своей выгоде."""
    return v7(**{"third_parties": ANSWERED_NO, **overrides})


def decide(inp: DecisionInput, policy: CreditPolicy = POLICY) -> PolicyDecision:
    return policy.decide(inp, key_rate=KEY_RATE)


def requiring_answers(tmp_path: Path) -> CreditPolicy:
    raw = yaml.safe_load((_CONFIG / "policy_v8.yaml").read_text(encoding="utf-8"))
    raw["compliance"]["third_parties"]["require_answers"] = True
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return load_policy_files(path, _CONFIG / "explanations_ru.yaml")


def test_acting_for_itself_is_approved() -> None:
    decision = decide(v8())
    assert decision.outcome == "APPROVE" and decision.policy_version == "policy_v8"
    assert hit(decision, "route.beneficiary").detail == "клиент действует к своей выгоде"
    assert hit(decision, "route.third_parties_unknown").detail == "сведения о третьих лицах есть"


def test_acting_for_a_third_party_goes_to_a_person() -> None:
    decision = decide(v8(third_parties=AGENT))
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (ReasonCode.ROUTE_THIRD_PARTY_BENEFICIARY,)
    assert review_kind(decision.outcome, decision.reason_codes) == "check"
    assert hit(decision, "route.beneficiary").detail == (
        "клиент действует к выгоде третьего лица: ООО «Транзитный агент», ИНН 7707115094 "
        "(агентский договор)"
    )


def test_listed_beneficiary_is_rejected() -> None:
    listed = AmlInput(
        "ok",
        list_hits=(AmlHit("выгодоприобретатель Посредников Павел Павлович", "перечень, запись 1"),),
        zsk_level="low",
    )
    decision = decide(v8(aml=listed, third_parties=AGENT))
    assert decision.outcome == "REJECT"
    assert decision.reason_codes == (ReasonCode.STOP_AML_LISTED,)


def test_no_answer_is_only_traced_while_the_form_does_not_ask() -> None:
    decision = decide(v8(third_parties=ThirdPartiesInput()))
    assert decision.outcome == "APPROVE"
    rule = hit(decision, "route.third_parties_unknown")
    assert not rule.matched and "правило выключено" in rule.detail


@pytest.mark.parametrize(
    "parties",
    [
        ThirdPartiesInput(),
        ThirdPartiesInput(beneficiary="none", pledgor="unknown"),
    ],
)
def test_no_answer_goes_to_a_person_when_required(
    tmp_path: Path, parties: ThirdPartiesInput
) -> None:
    decision = decide(v8(third_parties=parties), requiring_answers(tmp_path))
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (ReasonCode.ROUTE_THIRD_PARTIES_UNKNOWN,)
    assert review_kind(decision.outcome, decision.reason_codes) == "dispute"


def test_declared_pledgor_is_in_the_trace(tmp_path: Path) -> None:
    parties = ThirdPartiesInput(
        beneficiary="none", pledgor="declared", pledgor_name="Залогов Иван Иванович"
    )
    decision = decide(v8(third_parties=parties), requiring_answers(tmp_path))
    assert decision.outcome == "APPROVE"
    assert hit(decision, "route.third_parties_unknown").detail == (
        "залогодатель: Залогов Иван Иванович"
    )


def test_previous_policy_ignores_third_parties() -> None:
    decision = load_policy("policy_v7").decide(v8(third_parties=AGENT), key_rate=KEY_RATE)
    assert decision.outcome == "APPROVE"
    assert all(h.rule != "route.beneficiary" for h in decision.rule_trace)


def test_client_text_does_not_disclose_the_check() -> None:
    decision = decide(v8(third_parties=AGENT))
    for text in (decision.client_explanation, *decision.improvement_hints):
        for internal in ("перечень", "выгодоприобретател", "агент", "115"):
            assert internal not in text.lower(), (internal, text)


def test_third_parties_need_the_aml_section(tmp_path: Path) -> None:
    raw = yaml.safe_load((_CONFIG / "policy_v8.yaml").read_text(encoding="utf-8"))
    del raw["compliance"]["aml"]
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(PolicyConfigError, match="third_parties"):
        load_policy_files(path, _CONFIG / "explanations_ru.yaml")


def test_clean_check_constant_is_reused() -> None:
    assert v8().aml == CLEAN
