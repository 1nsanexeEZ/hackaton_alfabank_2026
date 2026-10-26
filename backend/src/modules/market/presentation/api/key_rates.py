"""The key rate: the one in force is public (open data, the calculator may show it); the
history is read with `scoring.read` and kept with `scoring.update`, as the credit policy."""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from src.modules.market.application.dto.key_rates import KeyRateCreate as KeyRateCreateDTO
from src.modules.market.presentation.dependencies import (
    AddKeyRateDep,
    CanRead,
    Editor,
    GetKeyRateDep,
    ListKeyRatesDep,
    RemoveKeyRateDep,
)
from src.modules.market.presentation.schemas.key_rates import (
    KeyRateCreate,
    KeyRateHistoryRead,
    KeyRateRead,
    KeyRateRecordRead,
)

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/key-rate", response_model=KeyRateRead)
async def get_key_rate(
    use_case: GetKeyRateDep,
    on: Annotated[dt.date | None, Query(description="Moscow date; today by default")] = None,
) -> KeyRateRead:
    """The key rate in force on the date. Nothing entered for it — `KEY_RATE` from the
    settings with `source: settings`."""
    return KeyRateRead.model_validate(await use_case.execute(on))


@router.get("/key-rates", response_model=KeyRateHistoryRead, dependencies=CanRead)
async def list_key_rates(use_case: ListKeyRatesDep) -> KeyRateHistoryRead:
    """The history, newest first, and the rate in force today (`current`)."""
    return KeyRateHistoryRead.model_validate(await use_case.execute())


@router.post("/key-rates", response_model=KeyRateRecordRead, status_code=status.HTTP_201_CREATED)
async def add_key_rate(
    data: KeyRateCreate, token: Editor, use_case: AddKeyRateDep
) -> KeyRateRecordRead:
    """A rate from a date on; the date is the admin's (the Bank of Russia's rate takes effect
    on the next working day after the decision). A rate from this date exists — 409
    `conflict`; `decided_on` after `effective_from` — 422."""
    record = await use_case.execute(KeyRateCreateDTO(**data.model_dump()), token.subject)
    return KeyRateRecordRead.model_validate(record)


@router.delete("/key-rates/{effective_from}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_key_rate(
    effective_from: dt.date, _: Editor, use_case: RemoveKeyRateDep
) -> Response:
    """Only a rate not in force yet or from today: one that has been in force is history —
    409 `invalid_transition`. No such rate — 404."""
    await use_case.execute(effective_from)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
