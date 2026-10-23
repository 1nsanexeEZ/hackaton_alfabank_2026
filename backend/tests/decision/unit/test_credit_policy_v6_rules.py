"""Правила policy_v6: v5 и обязательные требования закона.

- 115-ФЗ: перечни Росфинмониторинга, решения МВК и ФРОМУ — отказ до скоринга; высокий риск ЗСК —
  отказ; ПДЛ, средний риск ЗСК и невыполненная проверка — только ручная проверка. Клиенту —
  нейтральные тексты: о мерах по 115-ФЗ его не информируют.
- ст. 16 152-ФЗ: отказ или встречное предложение ИП без его согласия на автоматизированное
  решение — человеку.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

from src.modules.decision.domain.model import (
    AmlHit,
    AmlInput,
    DecisionInput,
    PolicyDecision,
    ReasonCode,
    RequestInput,
)
from src.modules.decision.facade import review_kind
from src.modules.decision.infrastructure.config_loader import load_policy
from tests.decision.unit.test_credit_policy_rules import company
from tests.decision.unit.test_credit_policy_v3_rules import hit
from tests.decision.unit.test_credit_policy_v5_rules import models, v5

POLICY = load_policy("policy_v6")
KEY_RATE = POLICY.config.key_rate_reference
CLEAN = AmlInput(
    "ok",
    zsk_level="low",
    beneficial_owners=("Смирнова Анна Сергеевна — 100.00%",),
    lists_date="2026-10-21",
)
LISTED = AmlInput(
    "ok",
    list_hits=(AmlHit("бенефициар Цепочкин Цезарь Цезаревич", "перечень ФРОМУ, запись 42"),),
    zsk_level="low",
    lists_date="2026-10-21",
)
FOREIGN_PEP = AmlInput(
    "ok",
    pep_hits=(AmlHit("бенефициар Послов Пётр Павлович", "иностранное ПДЛ: Посол"),),
    foreign_pep=True,
    zsk_level="low",
)


def v6(**overrides: Any) -> DecisionInput:
    """Заявка без замечаний, обе модели в зелёной зоне, проверка по 115-ФЗ чистая."""
    return v5(**{"aml": CLEAN, **overrides})


def decide(inp: DecisionInput) -> PolicyDecision:
    return POLICY.decide(inp, key_rate=KEY_RATE)


def review(decision: PolicyDecision) -> str | None:
    return review_kind(decision.outcome, decision.reason_codes)


def test_clean_check_is_approved_and_traced_first() -> None:
    decision = decide(v6())
    assert decision.outcome == "APPROVE" and decision.policy_version == "policy_v6"
    assert decision.reason_codes == ()
    groups = list(dict.fromkeys(h.rule.split(".", 1)[0] for h in decision.rule_trace))
    assert groups[0] == "aml"  # 115-ФЗ — первым правилом
    lists = hit(decision, "aml.lists")
    assert not lists.matched
    assert lists.detail == (
        "совпадений с перечнями нет (перечни на 2026-10-21); бенефициары: "
        "Смирнова Анна Сергеевна — 100.00%"
    )


def test_listed_person_is_rejected_whatever_the_score() -> None:
    """Даже с лучшими оценками моделей: обслуживать лицо из перечня закон запрещает."""
    decision = decide(v6(aml=LISTED))
    assert decision.outcome == "REJECT"
    assert decision.reason_codes == (ReasonCode.STOP_AML_LISTED,)
    assert hit(decision, "aml.lists").detail == (
        "бенефициар Цепочкин Цезарь Цезаревич: перечень ФРОМУ, запись 42"
    )
    assert all(h.rule != "strategy.two_models" for h in decision.rule_trace)


def test_listed_person_is_rejected_even_without_a_score() -> None:
    decision = decide(v6(aml=LISTED, score=None))
    assert decision.outcome == "REJECT"
    assert decision.reason_codes == (ReasonCode.STOP_AML_LISTED,)


def test_high_zsk_risk_is_rejected() -> None:
    decision = decide(v6(aml=AmlInput("ok", zsk_level="high")))
    assert decision.outcome == "REJECT"
    assert decision.reason_codes == (ReasonCode.STOP_ZSK_HIGH_RISK,)
    assert hit(decision, "aml.zsk_stop").detail == "уровень риска ЗСК: высокий"


@pytest.mark.parametrize(
    ("aml", "reason", "kind"),
    [
        (AmlInput("ok", zsk_level="medium"), ReasonCode.ROUTE_ZSK_MEDIUM_RISK, "check"),
        (FOREIGN_PEP, ReasonCode.ROUTE_PEP, "check"),
        (AmlInput("failed"), ReasonCode.ROUTE_AML_INCOMPLETE, "dispute"),
        (AmlInput("not_requested"), ReasonCode.ROUTE_AML_INCOMPLETE, "dispute"),
        (None, ReasonCode.ROUTE_AML_INCOMPLETE, "dispute"),
    ],
)
def test_no_automatic_approval(aml: AmlInput | None, reason: ReasonCode, kind: str) -> None:
    decision = decide(v6(aml=aml))
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (reason,)
    assert review(decision) == kind


def test_foreign_pep_needs_the_head_of_the_bank() -> None:
    detail = hit(decide(v6(aml=FOREIGN_PEP)), "route.pep").detail
    assert detail == (
        "бенефициар Послов Пётр Павлович: иностранное ПДЛ: Посол — нужно письменное решение "
        "руководителя банка и источник средств"
    )


@pytest.mark.parametrize("aml", [LISTED, AmlInput("ok", zsk_level="high"), FOREIGN_PEP])
def test_client_texts_do_not_disclose_the_checks(aml: AmlInput) -> None:
    """115-ФЗ: о мерах по противодействию отмыванию клиента не информируют."""
    decision = decide(v6(aml=aml))
    for text in (decision.client_explanation, *decision.improvement_hints):
        for internal in ("перечень", "ПДЛ", "ЗСК", "террор", "МВК", "ФРОМУ", "отмыв", "бенефи"):
            assert internal.lower() not in text.lower(), (internal, text)


# --- ст. 16 152-ФЗ ------------------------------------------------------------------------------


def _entrepreneur(*, registry_status: str = "active", **overrides: Any) -> DecisionInput:
    base = v6(**overrides)
    ie = replace(base.company, legal_form="IE", registry_status=registry_status)
    return replace(base, company=ie)


def test_entrepreneur_rejected_without_consent_goes_to_a_person() -> None:
    decision = decide(_entrepreneur(registry_status="liquidated"))
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (
        ReasonCode.ROUTE_AUTOMATED_DECISION_CONSENT,
        ReasonCode.STOP_LIQUIDATION,
    )
    assert decision.client_explanation == (
        "Заявку рассмотрит специалист банка, обычно это занимает до двух рабочих дней. "
        "Вы не давали согласия на решение в автоматическом режиме, поэтому заявку рассмотрит "
        "специалист."
    )
    assert decision.improvement_hints == ()
    assert hit(decision, "consent.automated_decision").matched


def test_entrepreneur_rejected_with_consent_is_rejected_automatically() -> None:
    decision = decide(_entrepreneur(registry_status="liquidated", automated_decision_consent=True))
    assert decision.outcome == "REJECT"
    assert decision.reason_codes == (ReasonCode.STOP_LIQUIDATION,)
    assert not hit(decision, "consent.automated_decision").matched


def test_entrepreneur_counter_offer_without_consent_goes_to_a_person() -> None:
    big = _entrepreneur(request=RequestInput(Decimal("29000000"), 24))
    with_consent = decide(replace(big, automated_decision_consent=True))
    assert with_consent.outcome == "COUNTER_OFFER"
    decision = decide(big)
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes[0] == ReasonCode.ROUTE_AUTOMATED_DECISION_CONSENT
    assert decision.terms is None


def test_entrepreneur_approved_as_requested_needs_no_consent() -> None:
    decision = decide(_entrepreneur())
    assert decision.outcome == "APPROVE"


def test_company_needs_no_consent() -> None:
    decision = decide(v6(company=company(registry_status="liquidated")))
    assert decision.outcome == "REJECT"
    assert all(h.rule != "consent.automated_decision" for h in decision.rule_trace)


def test_aml_stop_of_an_entrepreneur_stays_a_reject() -> None:
    """Отказ по 115-ФЗ — не оценка банка, а запрет закона: человеку его не переносим."""
    decision = decide(_entrepreneur(aml=LISTED))
    assert decision.outcome == "REJECT"
    assert decision.reason_codes == (ReasonCode.STOP_AML_LISTED,)


def test_previous_policies_ignore_the_checks() -> None:
    """policy_v5 правил 115-ФЗ не знает: её golden не сдвигаются."""
    v5_policy = load_policy("policy_v5")
    decision = v5_policy.decide(v6(aml=LISTED), key_rate=KEY_RATE)
    assert decision.outcome == "APPROVE"
    assert all(not h.rule.startswith(("aml.", "consent.")) for h in decision.rule_trace)


def test_models_still_decide_after_a_clean_check() -> None:
    decision = decide(v6(score=models("red", "red")))
    assert decision.outcome == "REJECT"
    assert decision.reason_codes == (ReasonCode.STOP_MODELS_HIGH_RISK,)
