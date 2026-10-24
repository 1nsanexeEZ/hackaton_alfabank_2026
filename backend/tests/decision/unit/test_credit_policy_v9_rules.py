"""Правила policy_v9: группа риска клиента по 115-ФЗ и лицензия.

- Группа риска совершения подозрительных операций (ст. 7 п. 1 подп. 3.1): высокая — участник
  из государства, не выполняющего рекомендации ФАТФ, иностранное ПДЛ, расхождение названных
  клиентом бенефициаров с ЕГРЮЛ, перечни, высокий риск ЗСК; средняя — средний риск ЗСК, ПДЛ,
  иностранный участник, выгодоприобретатель, вид деятельности повышенного риска; иначе низкая.
  Высокая — ручная проверка с мерами по снижению риска (подп. 3.2).
- Лицензируемый основной вид деятельности без действующей лицензии — отказ (ст. 7 п. 15).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.modules.decision.domain.model import (
    DecisionInput,
    PolicyDecision,
    ReasonCode,
)
from src.modules.decision.domain.policy import CreditPolicy
from src.modules.decision.facade import review_kind
from src.modules.decision.infrastructure.config_loader import (
    PolicyConfigError,
    load_policy,
    load_policy_files,
)
from tests.decision.unit.test_credit_policy_v3_rules import hit
from tests.decision.unit.test_credit_policy_v6_rules import CLEAN, FOREIGN_PEP
from tests.decision.unit.test_credit_policy_v8_rules import AGENT, v8

_CONFIG = Path(__file__).resolve().parents[3] / "src/modules/decision/infrastructure/config"
POLICY = load_policy("policy_v9")
KEY_RATE = POLICY.config.key_rate_reference
CHECKED = replace(CLEAN, licensed_okved=())


def v9(*, okved: str | None = None, **aml: Any) -> DecisionInput:
    """Заявка без замечаний; `aml` — поля проверки по 115-ФЗ поверх чистой."""
    base = v8(aml=replace(CHECKED, **aml))
    if okved is None:
        return base
    return replace(base, company=replace(base.company, okved_main=okved))


def decide(inp: DecisionInput, policy: CreditPolicy = POLICY) -> PolicyDecision:
    return policy.decide(inp, key_rate=KEY_RATE)


def group(decision: PolicyDecision) -> str:
    return hit(decision, "aml.risk_group").detail


def test_clean_client_is_in_the_low_group() -> None:
    decision = decide(v9())
    assert decision.outcome == "APPROVE" and decision.policy_version == "policy_v9"
    assert group(decision) == (
        "группа риска по 115-ФЗ: низкая — факторов риска нет; бенефициаров клиент не называл"
    )
    assert not hit(decision, "aml.risk_group").matched


def test_participant_from_a_fatf_listed_state_goes_to_a_person() -> None:
    decision = decide(v9(foreign_participants=(("учредитель Хоссейни Али Реза", "IR"),)))
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (ReasonCode.ROUTE_AML_HIGH_RISK,)
    assert review_kind(decision.outcome, decision.reason_codes) == "check"
    assert group(decision) == (
        "группа риска по 115-ФЗ: высокая — учредитель Хоссейни Али Реза — IR, государство не "
        "выполняет рекомендации ФАТФ; бенефициаров клиент не называл"
    )
    assert "источник средств" in hit(decision, "route.aml_high_risk").detail


def test_other_foreign_participant_is_the_medium_group() -> None:
    decision = decide(v9(foreign_participants=(("учредитель Шмидт Ганс", "DE"),)))
    assert decision.outcome == "APPROVE"
    assert group(decision).startswith(
        "группа риска по 115-ФЗ: средняя — учредитель Шмидт Ганс — иностранный участник (DE)"
    )


def test_owners_named_by_the_client_differ_from_the_registry() -> None:
    decision = decide(
        v9(
            owners_declared=True,
            owner_discrepancies=("Смирнова Анна Сергеевна — бенефициар по ЕГРЮЛ не назван",),
        )
    )
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (ReasonCode.ROUTE_AML_HIGH_RISK,)
    assert group(decision) == (
        "группа риска по 115-ФЗ: высокая — бенефициары со слов клиента: Смирнова Анна Сергеевна "
        "— бенефициар по ЕГРЮЛ не назван"
    )


def test_owners_named_and_matching() -> None:
    decision = decide(v9(owners_declared=True))
    assert decision.outcome == "APPROVE"
    assert group(decision) == "группа риска по 115-ФЗ: низкая — факторов риска нет"


def test_high_risk_activity_is_the_medium_group() -> None:
    decision = decide(v9(okved="47.77"))
    assert decision.outcome == "APPROVE"
    assert "вид деятельности 47.77 — повышенного риска по национальной оценке" in group(decision)


def test_acting_for_a_third_party_raises_the_group() -> None:
    decision = decide(replace(v9(), third_parties=AGENT))
    assert decision.reason_codes == (ReasonCode.ROUTE_THIRD_PARTY_BENEFICIARY,)
    assert "средняя — клиент действует к выгоде третьего лица" in group(decision)


def test_foreign_pep_is_the_high_group() -> None:
    decision = decide(v9(foreign_pep=FOREIGN_PEP.foreign_pep, pep_hits=FOREIGN_PEP.pep_hits))
    assert decision.reason_codes == (ReasonCode.ROUTE_PEP, ReasonCode.ROUTE_AML_HIGH_RISK)
    assert "высокая — иностранное ПДЛ" in group(decision)


def test_licensed_activity_without_a_license_is_rejected() -> None:
    decision = decide(v9(okved="86.10"))
    assert decision.outcome == "REJECT"
    assert decision.reason_codes == (ReasonCode.STOP_UNLICENSED_ACTIVITY,)
    assert hit(decision, "aml.license").detail == (
        "ОКВЭД 86.10 лицензируется: действующей лицензии нет"
    )
    assert "лицензи" in decision.client_explanation


def test_licensed_activity_with_a_license_passes() -> None:
    decision = decide(v9(okved="86.10", licensed_okved=("86.10",)))
    assert decision.outcome == "APPROVE"
    assert hit(decision, "aml.license").detail == (
        "ОКВЭД 86.10 лицензируется: действующая лицензия есть"
    )


def test_license_registry_not_requested_is_not_a_stop() -> None:
    """Снимки до policy_v9 без реестра лицензий: отказать нельзя, правило только в трассе."""
    decision = decide(v9(okved="86.10", licensed_okved=None))
    assert decision.outcome == "APPROVE"
    assert hit(decision, "aml.license").detail == "реестр лицензий не запрашивался"


def test_no_license_stops_before_scoring() -> None:
    screened = POLICY.screen(v9(okved="86.10"), key_rate=KEY_RATE)
    assert screened is not None and screened.outcome == "REJECT"
    assert screened.reason_codes == (ReasonCode.STOP_UNLICENSED_ACTIVITY,)


def test_high_group_only_traced_when_review_is_off(tmp_path: Path) -> None:
    raw = yaml.safe_load((_CONFIG / "policy_v9.yaml").read_text(encoding="utf-8"))
    raw["compliance"]["aml_risk"]["high_group_review"] = False
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    policy = load_policy_files(path, _CONFIG / "explanations_ru.yaml")
    decision = decide(v9(foreign_participants=(("учредитель Хоссейни Али Реза", "IR"),)), policy)
    assert decision.outcome == "APPROVE"
    assert hit(decision, "aml.risk_group").matched


def test_previous_policy_has_no_group_and_no_license_rule() -> None:
    inp = v9(okved="86.10", foreign_participants=(("учредитель Хоссейни Али Реза", "IR"),))
    decision = load_policy("policy_v8").decide(inp, key_rate=KEY_RATE)
    assert decision.outcome == "APPROVE"
    assert all(h.rule not in ("aml.risk_group", "aml.license") for h in decision.rule_trace)


def test_client_text_does_not_disclose_the_group() -> None:
    decision = decide(v9(foreign_participants=(("учредитель Хоссейни Али Реза", "IR"),)))
    for text in (decision.client_explanation, *decision.improvement_hints):
        for internal in ("риск", "ФАТФ", "115", "иностран", "IR"):
            assert internal not in text, (internal, text)


@pytest.mark.parametrize("section", ["aml_risk", "licensing"])
def test_new_sections_need_the_aml_section(tmp_path: Path, section: str) -> None:
    raw = yaml.safe_load((_CONFIG / "policy_v9.yaml").read_text(encoding="utf-8"))
    del raw["compliance"]["aml"]
    for other in ("third_parties", "aml_risk", "licensing"):
        if other != section:
            raw["compliance"].pop(other)
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(PolicyConfigError, match=section):
        load_policy_files(path, _CONFIG / "explanations_ru.yaml")


def test_country_codes_are_checked(tmp_path: Path) -> None:
    raw = yaml.safe_load((_CONFIG / "policy_v9.yaml").read_text(encoding="utf-8"))
    raw["compliance"]["aml_risk"]["high_risk_countries"] = ["Iran"]
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(PolicyConfigError):
        load_policy_files(path, _CONFIG / "explanations_ru.yaml")


def test_stays_clean_input() -> None:
    assert v9().aml == CHECKED


def test_hints_of_the_two_refusals() -> None:
    """Подсказка отказа без лицензии — про реестр лицензий; у отказа по ЗСК — про пересмотр."""
    unlicensed = decide(v9(okved="86.10"))
    assert unlicensed.improvement_hints == (
        "Если лицензия есть, проверьте, что она внесена в реестр лицензий, и подайте заявку снова.",
    )
    zsk = decide(v9(zsk_level="high"))
    assert zsk.reason_codes == (ReasonCode.STOP_ZSK_HIGH_RISK,)
    assert zsk.improvement_hints == (
        "Если считаете решение ошибочным, обратитесь в банк: порядок пересмотра установлен "
        "законом.",
    )
