"""The assistant's HTTP API: `assistant.use`, a client sees the applications of
their companies, a conversation is seen only by its author.

POST /assistant/conversations/{id}/messages answers with JSON, or with an SSE
stream when the request asks for `text/event-stream`: `status` right away,
`ping` while the model thinks, then the checked answer in `delta` chunks and
`done`. The text is released only after the post-check, so an unchecked token
never reaches the screen. Everything that may refuse the question (404, 422,
429) is answered as plain HTTP before the stream starts.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Coroutine
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, status
from fastapi.responses import StreamingResponse

from src.modules.assistant.application.dto.assistant import ReplyDTO
from src.modules.assistant.presentation.dependencies import (
    AcceptQuestionDep,
    AnswerQuestionDep,
    CurrentViewer,
    GetConversationDep,
    ListApplicationsDep,
    StartConversationDep,
    StatusDep,
)
from src.modules.assistant.presentation.schemas.assistant import (
    AssistantApplicationOut,
    AssistantConversationCreatedOut,
    AssistantConversationOut,
    AssistantQuestionIn,
    AssistantReplyOut,
    AssistantStatusOut,
)

log = logging.getLogger(__name__)
PING_EVERY_S = 5.0
CHUNK_CHARS = 24

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.get("/status", response_model=AssistantStatusOut)
async def get_status(use_case: StatusDep) -> AssistantStatusOut:
    """Open to anyone: the site shows the assistant's state before login."""
    return AssistantStatusOut.model_validate(await use_case.execute())


@router.get("/applications", response_model=list[AssistantApplicationOut])
async def list_applications(
    viewer: CurrentViewer, use_case: ListApplicationsDep
) -> list[AssistantApplicationOut]:
    """The applications of the client's companies to pick one for the chat; bank staff
    ask by an application id."""
    return [AssistantApplicationOut.model_validate(a) for a in await use_case.execute(viewer)]


@router.post(
    "/conversations",
    response_model=AssistantConversationCreatedOut,
    status_code=status.HTTP_201_CREATED,
)
async def start_conversation(
    viewer: CurrentViewer, use_case: StartConversationDep
) -> AssistantConversationCreatedOut:
    return AssistantConversationCreatedOut.model_validate(await use_case.execute(viewer))


@router.get("/conversations/{conversation_id}", response_model=AssistantConversationOut)
async def get_conversation(
    conversation_id: UUID, viewer: CurrentViewer, use_case: GetConversationDep
) -> AssistantConversationOut:
    """The history: someone else's conversation is 404."""
    return AssistantConversationOut.model_validate(await use_case.execute(viewer, conversation_id))


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=AssistantReplyOut,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def ask(
    conversation_id: UUID,
    body: AssistantQuestionIn,
    viewer: CurrentViewer,
    accept: AcceptQuestionDep,
    answer: AnswerQuestionDep,
    accept_header: Annotated[str | None, Header(alias="Accept")] = None,
) -> AssistantReplyOut | StreamingResponse:
    accepted = await accept.execute(viewer, conversation_id, body.text, body.application_id)
    if accept_header and "text/event-stream" in accept_header:
        return StreamingResponse(
            _stream(answer.execute(viewer, accepted)),
            media_type="text/event-stream",
            # nginx must not buffer the stream.
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return AssistantReplyOut.model_validate(await answer.execute(viewer, accepted))


async def _stream(pending: Coroutine[Any, Any, ReplyDTO]) -> AsyncIterator[str]:
    task = asyncio.ensure_future(pending)
    yield _event("status", {"state": "thinking"})
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=PING_EVERY_S)
            if done:
                break
            yield ": ping\n\n"
        reply = task.result()
    except Exception:
        log.exception("assistant stream failed")
        yield _event("error", {"detail": "assistant failed"})
        return
    finally:
        if not task.done():
            task.cancel()
    for start in range(0, len(reply.text), CHUNK_CHARS):
        yield _event("delta", {"text": reply.text[start : start + CHUNK_CHARS]})
    yield _event("done", AssistantReplyOut.model_validate(reply).model_dump(mode="json"))


def _event(name: str, data: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
