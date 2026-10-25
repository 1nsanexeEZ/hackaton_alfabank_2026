"""The provider choice, the local-endpoint guard and the OpenAI-compatible adapter."""

import json
from typing import Any

import httpx
import pytest

from src.modules.assistant.application.interfaces.language_model import (
    LanguageModelUnavailableError,
)
from src.modules.assistant.domain.prompt import ChatMessage
from src.modules.assistant.infrastructure.adapters.language_models import (
    EndpointNotAllowedError,
    OpenAICompatibleModel,
    build_language_model,
    check_local_endpoint,
)
from src.modules.assistant.infrastructure.config import AssistantSettings

OPEN_MODEL = "qwen3:4b-instruct-2507-q4_K_M"


def _settings(**values: Any) -> AssistantSettings:
    return AssistantSettings(_env_file=None, **values)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "url",
    [
        "http://ollama:11434/v1",
        "http://localhost:11434/v1",
        "http://127.0.0.1:8080/v1",
        "http://host.docker.internal:11434/v1",
    ],
)
def test_local_hosts_are_allowed(url: str) -> None:
    check_local_endpoint(url, OPEN_MODEL, frozenset())


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openai.com/v1",
        "https://my.openai.azure.com/openai",
        "https://api.anthropic.com/v1",
        "https://api.groq.com/openai/v1",
        "https://openrouter.ai/api/v1",
        "https://api.together.xyz/v1",
        "https://api.mistral.ai/v1",
        "https://api.deepseek.com/v1",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "https://gigachat.devices.sberbank.ru/api/v1",
        "https://llm.api.cloud.yandex.net/v1",
        "https://router.huggingface.co/v1",
    ],
)
def test_a_local_model_is_never_a_paid_provider(url: str) -> None:
    host = httpx.URL(url).host
    with pytest.raises(EndpointNotAllowedError):
        check_local_endpoint(url, OPEN_MODEL, frozenset({host}))


def test_an_unknown_host_needs_to_be_listed_for_a_local_model() -> None:
    with pytest.raises(EndpointNotAllowedError):
        check_local_endpoint("http://llm.example.org/v1", OPEN_MODEL, frozenset())
    check_local_endpoint("http://llm.example.org/v1", OPEN_MODEL, frozenset({"llm.example.org"}))


@pytest.mark.parametrize("model", ["gpt-4o-mini", "claude-3-haiku", "GigaChat-Pro", "yandexgpt"])
def test_closed_models_are_never_local(model: str) -> None:
    with pytest.raises(EndpointNotAllowedError):
        check_local_endpoint("http://localhost:11434/v1", model, frozenset())


def test_off_means_templates() -> None:
    setup = build_language_model(_settings(llm_provider="off"))
    assert setup.provider == "off" and setup.model is None
    assert setup.disabled_reason == "ASSISTANT_LLM_PROVIDER=off"


def test_a_local_model_inside_the_perimeter() -> None:
    setup = build_language_model(
        _settings(llm_provider="local", llm_base_url="http://ollama:11434/v1")
    )
    assert setup.model is not None
    assert setup.model.inside_perimeter is True
    assert setup.model.host == "ollama" and setup.model.model == OPEN_MODEL


def test_a_paid_host_as_a_local_model_leaves_templates() -> None:
    setup = build_language_model(
        _settings(
            llm_provider="local", llm_base_url="https://api.openai.com/v1", llm_model="gpt-4o"
        )
    )
    assert setup.model is None
    assert setup.disabled_reason is not None and setup.disabled_reason.startswith("blocked:")


def test_an_api_takes_any_host_and_stays_outside_the_perimeter() -> None:
    """The bank's own model behind an API: nothing changes but the env."""
    setup = build_language_model(
        _settings(
            llm_provider="api",
            llm_base_url="https://llm.bank.example/v1",
            llm_api_key="secret",
            llm_model="bank-llm-70b",
        )
    )
    assert setup.provider == "api"
    assert setup.model is not None
    assert setup.model.inside_perimeter is False
    assert setup.model.host == "llm.bank.example"


def test_an_api_may_be_openrouter_with_an_open_model() -> None:
    """The organizers allow OpenRouter for open-weights models (chat, 25.10.2026)."""
    setup = build_language_model(
        _settings(
            llm_provider="api",
            llm_base_url="https://openrouter.ai/api/v1",
            llm_model="qwen/qwen-2.5-72b-instruct",
        )
    )
    assert setup.model is not None and setup.model.host == "openrouter.ai"


@pytest.mark.parametrize("model", ["openai/gpt-4o-mini", "anthropic/claude-3.5-haiku", "GigaChat"])
def test_an_api_never_serves_a_closed_model(model: str) -> None:
    setup = build_language_model(
        _settings(llm_provider="api", llm_base_url="https://openrouter.ai/api/v1", llm_model=model)
    )
    assert setup.model is None
    assert setup.disabled_reason is not None and "open-weights" in setup.disabled_reason


def test_an_api_needs_a_url() -> None:
    setup = build_language_model(_settings(llm_provider="api", llm_base_url="not a url"))
    assert setup.model is None and setup.disabled_reason is not None


async def test_the_api_key_goes_as_a_bearer_token() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"choices": [{"message": {"content": "Ответ."}}]})

    setup = build_language_model(
        _settings(llm_provider="api", llm_base_url="https://llm.bank.example/v1", llm_api_key="k1"),
        transport=httpx.MockTransport(handler),
    )
    assert setup.model is not None
    assert await setup.model.complete([ChatMessage("user", "вопрос")]) == "Ответ."
    assert seen["auth"] == "Bearer k1"


def _client(handler: Any) -> OpenAICompatibleModel:
    return OpenAICompatibleModel(
        "http://ollama:11434/v1",
        "",
        OPEN_MODEL,
        5.0,
        inside_perimeter=True,
        transport=httpx.MockTransport(handler),
    )


async def test_the_client_speaks_openai_chat_completions() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        answer = "<think>посчитаю</think>Банк предлагает 1 300 000 ₽."
        return httpx.Response(200, json={"choices": [{"message": {"content": answer}}]})

    text = await _client(handler).complete([ChatMessage("user", "вопрос")])
    assert text == "Банк предлагает 1 300 000 ₽."
    assert seen["url"] == "http://ollama:11434/v1/chat/completions"
    assert seen["body"]["model"] == OPEN_MODEL
    assert seen["body"]["temperature"] == 0.1
    assert seen["body"]["stream"] is False


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text="boom"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {"content": "  "}}]}),
        httpx.Response(200, text="not json"),
    ],
)
async def test_bad_answers_become_unavailable(response: httpx.Response) -> None:
    with pytest.raises(LanguageModelUnavailableError):
        await _client(lambda request: response).complete([ChatMessage("user", "вопрос")])


@pytest.mark.parametrize(
    ("response", "reachable"),
    [
        (httpx.Response(200, json={"data": [{"id": OPEN_MODEL}]}), True),
        # Ollama is up, the model is not pulled yet.
        (httpx.Response(200, json={"object": "list", "data": []}), False),
        (httpx.Response(200, json={"data": [{"id": "qwen2.5:1.5b"}]}), False),
        (httpx.Response(200, text="not json"), False),
        (httpx.Response(500, text="boom"), False),
    ],
)
async def test_ping_needs_the_model_on_the_server(
    response: httpx.Response, reachable: bool
) -> None:
    assert await _client(lambda request: response).ping() is reachable


async def test_the_warm_up_asks_for_one_token_and_never_fails() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "З"}}]})

    await _client(handler).warm_up()
    assert seen[0]["max_tokens"] == 1 and seen[0]["model"] == OPEN_MODEL

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    await _client(refuse).warm_up()


async def test_a_refused_connection_becomes_unavailable() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = _client(refuse)
    with pytest.raises(LanguageModelUnavailableError):
        await client.complete([ChatMessage("user", "вопрос")])
    assert await client.ping() is False
