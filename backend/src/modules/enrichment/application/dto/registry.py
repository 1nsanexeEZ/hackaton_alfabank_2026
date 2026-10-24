"""ЕГРЮЛ / ЕГРИП: выписка из реестра."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class FounderDTO:
    """Учредитель: физлицо — ФИО, юрлицо — наименование и ИНН (по нему идём по цепочке)."""

    name: str
    share_percent: Decimal
    inn: str | None = None
    # Страна места жительства или регистрации (ISO 3166-1 alpha-2), если не Россия.
    country: str | None = None


@dataclass(frozen=True, slots=True)
class RegistryExtractDTO:
    inn: str
    ogrn: str
    legal_form: str
    full_name: str
    status: str
    registered_at: date
    okved_main: str
    okved_extra: tuple[str, ...]
    head_last_name: str
    head_first_name: str
    head_middle_name: str | None
    head_position: str
    founders: tuple[FounderDTO, ...]
    address: str
    region_code: str
    mass_address: bool
    # None for an entrepreneur and in snapshots taken before it was stored.
    kpp: str | None = None
    # Дата записи о нынешнем руководителе; None — реестр её не сообщил (снимки до неё).
    head_since: date | None = None
    # Отметки о недостоверности сведений: address | head | founder.
    unreliable: tuple[str, ...] = ()
