"""Versions of the credit policy for the admin: the built-in policy from YAML is read only
and is in force until the admin activates a version of their own. Reading and preview
need `scoring.read`, keeping the versions — `scoring.update` (the same pair as the
versions of the PD model)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from src.core.access.dependencies import require_permissions
from src.core.access.permissions import Permissions
from src.core.infrastructure.database.session import DbSession
from src.core.schemas.jwt_dto import OpenSubTokenDTO
from src.modules.decision.api.dependencies import (
    DecisionHistoryDep,
    InputBuildersDep,
    KeyRateDep,
    PolicyVersionsDep,
)
from src.modules.decision.api.policy_schemas import (
    DraftCreate,
    DraftUpdate,
    PolicyCatalogRead,
    PolicyVersionRead,
    PolicyVersionSummaryRead,
    PreviewRead,
)

router = APIRouter(prefix="/decision/policies", tags=["decision"])

CanRead = [Depends(require_permissions(Permissions.SCORING_READ))]
Editor = Annotated[OpenSubTokenDTO, Depends(require_permissions(Permissions.SCORING_UPDATE))]

PREVIEW_LIMIT = 500


@router.get("", response_model=list[PolicyVersionSummaryRead], dependencies=CanRead)
async def list_versions(versions: PolicyVersionsDep) -> list[PolicyVersionSummaryRead]:
    """The built-in policy first, then the admin's versions in the order they were made.
    The one with `status: active` is in force."""
    return [PolicyVersionSummaryRead.model_validate(v) for v in await versions.list_all()]


@router.get("/catalog", response_model=PolicyCatalogRead, dependencies=CanRead)
async def get_catalog(versions: PolicyVersionsDep) -> PolicyCatalogRead:
    """What a policy document is made of: the grade scales, the outcomes, the reason codes
    with their client texts (not editable here: a code without a text is refused), the
    stop-factor keys, registry statuses, routing flags, zones of the two models and the
    names of collateral types and alternative products."""
    return PolicyCatalogRead.of(versions.catalog())


@router.get("/{version}", response_model=PolicyVersionRead, dependencies=CanRead)
async def get_version(version: str, versions: PolicyVersionsDep) -> PolicyVersionRead:
    """A version with its document (`body`), the same as the YAML file."""
    return PolicyVersionRead.of(await versions.get(version))


@router.post(
    "",
    response_model=PolicyVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_draft(
    data: DraftCreate, token: Editor, versions: PolicyVersionsDep, session: DbSession
) -> PolicyVersionRead:
    """A draft copied from any version, under the next number: `policy_v10.1`,
    `policy_v10.2`… 404 — no such version."""
    draft = await versions.create_draft(data.based_on, data.comment, token.subject)
    await session.commit()
    return PolicyVersionRead.of(draft)


@router.put("/{version}", response_model=PolicyVersionRead)
async def update_draft(
    version: str,
    data: DraftUpdate,
    _: Editor,
    versions: PolicyVersionsDep,
    session: DbSession,
) -> PolicyVersionRead:
    """The whole document of a draft. It is checked as the YAML file is at startup:
    422 `validation_error` with `details.errors` — a list of `{path, message}` (a grade
    off the scale, a broken matrix, a reason code without a client text…). Not a draft —
    409 `invalid_transition`."""
    draft = await versions.update_draft(version, data.body, data.comment)
    await session.commit()
    return PolicyVersionRead.of(draft)


@router.delete("/{version}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_draft(
    version: str, _: Editor, versions: PolicyVersionsDep, session: DbSession
) -> None:
    """Only a draft; an active or archived version — 409 `invalid_transition`: decisions
    were made by it."""
    await versions.delete_draft(version)
    await session.commit()


@router.post("/{version}/activate", response_model=PolicyVersionRead)
async def activate_version(
    version: str, token: Editor, versions: PolicyVersionsDep, session: DbSession
) -> PolicyVersionRead:
    """A draft or an archived version (rollback) is put in force, the active one goes to
    the archive. The built-in version: the admin's active version goes to the archive and
    the YAML policy is in force again. Already active — 409 `invalid_transition`.
    New decisions, pre-approvals and the nightly refresh go by it; old decisions keep
    their `policy_version`."""
    activated = await versions.activate(version, token.subject)
    await session.commit()
    return PolicyVersionRead.of(activated)


@router.post("/{version}/preview", response_model=PreviewRead, dependencies=CanRead)
async def preview_version(
    version: str,
    versions: PolicyVersionsDep,
    history: DecisionHistoryDep,
    inputs: InputBuildersDep,
    key_rate: KeyRateDep,
    limit: Annotated[int, Query(ge=1, le=PREVIEW_LIMIT)] = 50,
) -> PreviewRead:
    """A try-on, not an exact replay: the latest `limit` applications with an automatic
    decision are decided again by this version — stop factors first, then the decision,
    as the process does. The input is gathered anew from the current data (the
    application, its latest enrichment snapshot and scoring result, the product catalog)
    with the current key rate, so `after` may differ from `before` even with the same
    policy when the data has changed since. Outcome and reason codes before (the stored
    decision and its `policy_version`) and after, and how the outcomes moved. Nothing is
    written; an application whose input cannot be gathered any more is counted in
    `skipped`."""
    return PreviewRead.of(await versions.preview(version, limit, history, inputs, key_rate))
