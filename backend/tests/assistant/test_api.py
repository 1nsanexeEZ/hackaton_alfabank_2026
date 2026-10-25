import json
from typing import Any

from src.core.access.permissions import Permissions
from tests.assistant.fake_llm import FakeLlm


def test_without_a_token_nothing_is_answered(make_chat: Any) -> None:
    chat = make_chat()
    assert chat.client.post("/assistant/conversations").status_code == 401
    assert chat.client.get("/assistant/applications").status_code == 401


def test_without_the_right_the_assistant_is_closed(make_chat: Any) -> None:
    chat = make_chat()
    headers = chat.headers("ivanov", without=(Permissions.ASSISTANT_USE,))
    assert chat.client.post("/assistant/conversations", headers=headers).status_code == 403


def test_a_client_can_not_ask_about_another_company(make_chat: Any) -> None:
    chat = make_chat()
    response = chat.ask("ivanov", "Почему такое решение?", "S-1")
    assert response.status_code == 404


def test_a_client_sees_the_applications_of_their_companies(make_chat: Any) -> None:
    chat = make_chat()
    rows = chat.client.get("/assistant/applications", headers=chat.headers("ivanov")).json()
    assert {r["id"] for r in rows} == {str(chat.app_id("S-2")), str(chat.app_id("draft"))}


def test_a_conversation_belongs_to_its_author(make_chat: Any) -> None:
    chat = make_chat()
    conversation = chat.start("ivanov")
    stranger = chat.headers("romashka")
    read = chat.client.get(f"/assistant/conversations/{conversation}", headers=stranger)
    assert read.status_code == 404
    post = chat.client.post(
        f"/assistant/conversations/{conversation}/messages",
        json={"text": "Привет"},
        headers=stranger,
    )
    assert post.status_code == 404


def test_the_underwriter_asks_by_an_application_id(make_chat: Any) -> None:
    chat = make_chat()
    response = chat.ask("underwriter", "Что с заявкой?", "S-3")
    assert response.status_code == 200
    # Bank staff are not members of the companies: no list, only by id.
    headers = chat.headers("underwriter")
    assert chat.client.get("/assistant/applications", headers=headers).json() == []


def test_history_is_kept(make_chat: Any) -> None:
    chat = make_chat()
    headers = chat.headers("ivanov")
    conversation = chat.start("ivanov")
    url = f"/assistant/conversations/{conversation}/messages"
    chat.client.post(url, json={"text": "Привет"}, headers=headers)
    chat.client.post(url, json={"text": "Расскажи про овердрафт"}, headers=headers)
    history = chat.client.get(f"/assistant/conversations/{conversation}", headers=headers).json()
    assert [m["role"] for m in history["messages"]] == ["user", "assistant", "user", "assistant"]
    assert history["messages"][2]["text"] == "Расскажи про овердрафт"
    assert history["messages"][3]["mode"] == "rules"


def test_rate_limit_per_user(make_chat: Any) -> None:
    chat = make_chat(rate_limit_per_minute=3)
    for _ in range(3):
        assert chat.ask("ivanov", "Привет").status_code == 200
    limited = chat.ask("ivanov", "Привет")
    assert limited.status_code == 429
    assert limited.json()["code"] == "too_many_requests"
    assert int(limited.headers["Retry-After"]) >= 1
    # Another user has their own budget.
    assert chat.ask("romashka", "Привет").status_code == 200


def test_a_too_long_question_is_refused(make_chat: Any) -> None:
    chat = make_chat()
    assert chat.ask("ivanov", "а" * 1001).status_code == 422
    assert chat.ask("ivanov", "   ").status_code == 422


def test_the_answer_streams_as_sse(make_chat: Any) -> None:
    chat = make_chat(llm=FakeLlm())
    conversation = chat.start("ivanov")
    response = chat.client.post(
        f"/assistant/conversations/{conversation}/messages",
        json={"text": "Почему такое решение?", "application_id": str(chat.app_id("S-2"))},
        headers={**chat.headers("ivanov"), "Accept": "text/event-stream"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    events = [
        (block.split("\n")[0].removeprefix("event: "), json.loads(block.split("\n")[1][6:]))
        for block in response.text.strip().split("\n\n")
        if block.startswith("event:")
    ]
    names = [name for name, _ in events]
    assert names[0] == "status" and names[-1] == "done" and "delta" in names
    text = "".join(data["text"] for name, data in events if name == "delta")
    done = events[-1][1]
    assert done["mode"] == "llm"
    assert text == done["text"]
    assert "1 300 000 ₽" in text
    # The answer given by stream is in the history too: the session lives through the stream.
    history = chat.client.get(
        f"/assistant/conversations/{conversation}", headers=chat.headers("ivanov")
    ).json()
    assert history["messages"][-1]["text"] == text


def test_sse_errors_before_the_stream_are_plain_http(make_chat: Any) -> None:
    chat = make_chat()
    response = chat.ask("ivanov", "Почему?", "S-1", Accept="text/event-stream")
    assert response.status_code == 404


def test_status_without_a_model(make_chat: Any) -> None:
    status = make_chat().client.get("/assistant/status").json()
    assert status == {
        "enabled": False,
        "mode": "rules",
        "provider": "off",
        "model": None,
        "host": None,
        "reachable": False,
        "reason": "ASSISTANT_LLM_PROVIDER=off",
    }


def test_status_with_a_model(make_chat: Any) -> None:
    status = make_chat(llm=FakeLlm()).client.get("/assistant/status").json()
    assert status["mode"] == "llm" and status["reachable"] is True
    assert status["provider"] == "local" and status["model"] == "fake-open-model"
    down = make_chat(llm=FakeLlm(reachable=False)).client.get("/assistant/status").json()
    assert down["mode"] == "rules"
