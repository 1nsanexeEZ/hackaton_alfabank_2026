"""The question set on a live model. Not run by default, nor by the CI integration job:

ASSISTANT_LIVE_MODEL=1 ASSISTANT_LLM_PROVIDER=local \
    ASSISTANT_LLM_BASE_URL=http://localhost:11434/v1 uv run pytest -m integration tests/assistant
"""

import os

import pytest

from tests.assistant.evaluate import run

pytestmark = pytest.mark.integration


@pytest.mark.skipif(os.environ.get("ASSISTANT_LIVE_MODEL") != "1", reason="needs a live model")
def test_question_set_on_a_live_model() -> None:
    result = run(runs=1)
    # The post-check guarantees these whatever the model says.
    assert result["leaks"] == 0
    assert result["intent"] >= 0.95
    assert result["expected"] >= 0.9
    # A model that fails the post-check on most answers is useless, not dangerous.
    assert result["passed"] >= 0.5, result["fallbacks"]
