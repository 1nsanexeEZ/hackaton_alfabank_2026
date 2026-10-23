from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentUploadIn(BaseModel):
    type: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z_]*$")
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=128)
    size_bytes: int = Field(gt=0)


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    filename: str
    content_type: str
    size_bytes: int
    status: str
    uploaded_at: datetime | None
    info_request_id: UUID | None


class PresignedUploadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    url: str
    method: str
    headers: dict[str, str]
    expires_at: datetime


class DocumentUploadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document: DocumentOut
    upload: PresignedUploadOut


class DownloadOut(BaseModel):
    url: str
