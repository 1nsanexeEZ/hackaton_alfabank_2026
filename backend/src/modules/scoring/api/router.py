"""Versions of the PD model for the admin: the built-in model from YAML is read only
and is in force until the admin activates a version of their own. Reading and preview
need `scoring.read`, keeping the versions — `scoring.update`."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from src.core.access.dependencies import require_permissions
from src.core.access.permissions import Permissions
from src.core.infrastructure.database.session import DbSession
from src.core.schemas.jwt_dto import OpenSubTokenDTO
from src.modules.scoring.api.dependencies import ModelVersionsDep, ScoringHistoryDep
from src.modules.scoring.api.schemas import (
    DraftCreate,
    DraftUpdate,
    ModelCatalogRead,
    ModelVersionRead,
    ModelVersionSummaryRead,
    PreviewRead,
)

router = APIRouter(prefix="/scoring/models", tags=["scoring"])

CanRead = [Depends(require_permissions(Permissions.SCORING_READ))]
Editor = Annotated[OpenSubTokenDTO, Depends(require_permissions(Permissions.SCORING_UPDATE))]

PREVIEW_LIMIT = 500


@router.get("", response_model=list[ModelVersionSummaryRead], dependencies=CanRead)
async def list_versions(versions: ModelVersionsDep) -> list[ModelVersionSummaryRead]:
    """The built-in model first, then the admin's versions in the order they were made.
    The one with `status: active` is in force."""
    return [ModelVersionSummaryRead.model_validate(v) for v in await versions.list_all()]


@router.get("/catalog", response_model=ModelCatalogRead, dependencies=CanRead)
async def get_catalog(versions: ModelVersionsDep) -> ModelCatalogRead:
    """What a model document is made of: segments, features (numeric or categorical,
    the categories that need a bin, required ones) and the grade scale."""
    return ModelCatalogRead.of(versions.catalog())


@router.get("/{version}", response_model=ModelVersionRead, dependencies=CanRead)
async def get_version(version: str, versions: ModelVersionsDep) -> ModelVersionRead:
    """A version with its document (`body`), the same as the YAML file."""
    return ModelVersionRead.of(await versions.get(version))


@router.post(
    "",
    response_model=ModelVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_draft(
    data: DraftCreate, token: Editor, versions: ModelVersionsDep, session: DbSession
) -> ModelVersionRead:
    """A draft copied from any version, under the next number: `pd_model_v2.1`,
    `pd_model_v2.2`… 404 — no such version."""
    draft = await versions.create_draft(data.based_on, data.comment, token.subject)
    await session.commit()
    return ModelVersionRead.of(draft)


@router.put("/{version}", response_model=ModelVersionRead)
async def update_draft(
    version: str,
    data: DraftUpdate,
    _: Editor,
    versions: ModelVersionsDep,
    session: DbSession,
) -> ModelVersionRead:
    """The whole document of a draft. It is checked as the YAML file is at startup:
    422 `validation_error` with `details.errors` — a list of `{path, message}`. Not a
    draft — 409 `invalid_transition`."""
    draft = await versions.update_draft(version, data.body, data.comment)
    await session.commit()
    return ModelVersionRead.of(draft)


@router.delete("/{version}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_draft(
    version: str, _: Editor, versions: ModelVersionsDep, session: DbSession
) -> None:
    """Only a draft; an active or archived version — 409 `invalid_transition`: results
    were scored by it."""
    await versions.delete_draft(version)
    await session.commit()


@router.post("/{version}/activate", response_model=ModelVersionRead)
async def activate_version(
    version: str, token: Editor, versions: ModelVersionsDep, session: DbSession
) -> ModelVersionRead:
    """A draft or an archived version (rollback) is put in force, the active one goes to
    the archive. The built-in version: the admin's active version goes to the archive and
    the YAML model is in force again. Already active — 409 `invalid_transition`.
    New applications and pre-approvals are scored by it; old results keep their
    `model_version`."""
    activated = await versions.activate(version, token.subject)
    await session.commit()
    return ModelVersionRead.of(activated)


@router.post("/{version}/preview", response_model=PreviewRead, dependencies=CanRead)
async def preview_version(
    version: str,
    versions: ModelVersionsDep,
    history: ScoringHistoryDep,
    limit: Annotated[int, Query(ge=1, le=PREVIEW_LIMIT)] = 50,
) -> PreviewRead:
    """The latest `limit` applications scored by the PD model, scored again by this
    version from their stored input: score, PD, grade and segment before and after, and
    how the grades moved. Nothing is written. scorecard_v1 results (no PD, grades A–E)
    are left out."""
    return PreviewRead.of(await versions.preview(version, limit, history))
