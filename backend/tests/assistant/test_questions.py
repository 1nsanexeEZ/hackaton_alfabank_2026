"""The question set (tests/questions.json): S-1…S-8, products, payments,
off-topic and injection. In rules mode every answer is checked against the
expected intent and text; the same set runs on a live model in
test_live_model.py."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from tests.assistant.fake_llm import FakeLlm

QUESTIONS: list[dict[str, Any]] = json.loads(
    (Path(__file__).parent / "data" / "questions.json").read_text(encoding="utf-8")
)
INTERNAL_MARKERS = ("скор", "грейд", "rule_trace", "reason_code", "STOP_", "LIMIT_BY", "ROUTE_")


def test_the_set_covers_every_scenario_and_the_guards() -> None:
    scenarios = {q["scenario"] for q in QUESTIONS}
    intents = {q["intent"] for q in QUESTIONS}
    assert {"S-1", "S-2", "S-3", "S-4", "S-5a", "S-5b", "S-6", "S-7", "S-8"} <= scenarios
    assert {"injection", "off_topic", "internal_data", "payment", "products"} <= intents
    assert 30 <= len(QUESTIONS) <= 50


@pytest.mark.parametrize("q", QUESTIONS, ids=[q["id"] for q in QUESTIONS])
def test_rules_mode_answers(make_chat: Any, q: dict[str, Any]) -> None:
    chat = make_chat()
    response = chat.ask(q["user"], q["text"], q["scenario"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["intent"] == q["intent"], body["text"]
    assert body["mode"] == "rules"
    for fragment in q["contains"]:
        assert fragment.lower() in body["text"].lower(), body["text"]
    for fragment in q["absent"]:
        assert fragment.lower() not in body["text"].lower(), body["text"]


@pytest.mark.parametrize("q", QUESTIONS, ids=[q["id"] for q in QUESTIONS])
def test_internal_data_never_reaches_the_prompt(make_chat: Any, q: dict[str, Any]) -> None:
    llm = FakeLlm()
    chat = make_chat(llm=llm)
    chat.ask(q["user"], q["text"], q["scenario"])
    prompts = llm.prompts
    for marker in INTERNAL_MARKERS:
        assert marker not in prompts
    # No score of the golden files (S-1…S-7) in any prompt, as a whole number.
    numbers = set(re.findall(r"\d{1,3}(?: \d{3})+|\d+", prompts))
    assert not numbers & {"790", "565", "620", "395", "700", "685", "760"}
