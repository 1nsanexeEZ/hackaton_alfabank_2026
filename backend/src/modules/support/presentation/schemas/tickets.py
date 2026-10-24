from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.core.types import SafeString
from src.modules.support.domain.enums import Side, TicketStatus
from src.modules.support.domain.value_objects import SUBJECT_MAX_LENGTH, TEXT_MAX_LENGTH

# HTML is stripped; a text that is blank after that is 422 from the domain.
Subject = Annotated[SafeString, Field(min_length=1, max_length=SUBJECT_MAX_LENGTH)]
MessageText = Annotated[SafeString, Field(min_length=1, max_length=TEXT_MAX_LENGTH)]


class TicketCreate(BaseModel):
    subject: Subject
    text: MessageText = Field(description="The first message of the chat")
    organization_id: UUID | None = Field(
        default=None, description="The company the question is about; the client is its member"
    )
    application_id: UUID | None = Field(
        default=None,
        description="The application the question is about; its company is taken for the ticket",
    )


class MessageCreate(BaseModel):
    text: MessageText


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    author_id: UUID
    author_name: str | None
    side: Side
    text: str
    created_at: datetime


class TicketListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    number: str
    subject: str
    status: TicketStatus
    author_id: UUID
    organization_id: UUID | None
    application_id: UUID | None
    assignee_id: UUID | None = Field(description="The employee who took the ticket")
    taken_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    message_count: int
    last_message_at: datetime | None
    last_message_side: Side | None = Field(
        description="`client` in a ticket that is not closed: the bank owes an answer"
    )
    version: int
    created_at: datetime
    updated_at: datetime


class TicketOut(TicketListItem):
    author_name: str | None
    assignee_name: str | None
    messages: list[MessageOut]
