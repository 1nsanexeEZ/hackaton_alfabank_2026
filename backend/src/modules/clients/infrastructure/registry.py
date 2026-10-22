"""ЕГРЮЛ/ЕГРИП for clients through the enrichment facade: the registry
extract DTO becomes our value objects."""

from src.core.exceptions.exceptions import InfrastructureError, ValidationError
from src.modules.clients.domain.value_objects import (
    Address,
    Inn,
    Kpp,
    Ogrn,
    OkvedCode,
    PersonName,
    RegistryExtract,
    RegistryStatus,
    parse_enum,
)
from src.modules.enrichment.facade import EnrichmentFacade, RegistryExtractDTO

# The registry gives the full name, the card keeps the short one.
_LEGAL_FORMS = (
    ("Общество с ограниченной ответственностью", "ООО"),
    ("Публичное акционерное общество", "ПАО"),
    ("Непубличное акционерное общество", "АО"),
    ("Акционерное общество", "АО"),
    ("Индивидуальный предприниматель", "ИП"),
)


def short_name(full_name: str) -> str:
    """`Общество с ограниченной ответственностью «Ромашка»` → `ООО «Ромашка»`."""
    name = " ".join(full_name.split())
    for full, short in _LEGAL_FORMS:
        if name.lower().startswith(full.lower()):
            return short + name[len(full) :]
    return name


def extract_of(dto: RegistryExtractDTO) -> RegistryExtract:
    """InfrastructureError if the registry answered with data our value
    objects do not accept: that is the registry's fault, not the client's."""
    try:
        return RegistryExtract(
            inn=Inn(dto.inn),
            ogrn=Ogrn(dto.ogrn),
            name=short_name(dto.full_name),
            address=Address(dto.address, dto.region_code),
            okved_main=OkvedCode(dto.okved_main),
            status=parse_enum(RegistryStatus, dto.status, "registry_status"),
            head=PersonName(dto.head_last_name, dto.head_first_name, dto.head_middle_name),
            kpp=Kpp(dto.kpp) if dto.kpp else None,
            okved_extra=tuple(OkvedCode(code) for code in dto.okved_extra),
        )
    except ValidationError as exc:
        raise InfrastructureError(
            "The registry answered with data we cannot read",
            details={"code": "bad_registry_data", "field": (exc.details or {}).get("field")},
        ) from exc


class EnrichmentRegistryLookup:
    """RegistryLookup on `EnrichmentFacade.lookup_registry`, past its cache."""

    def __init__(self, enrichment: EnrichmentFacade) -> None:
        self._enrichment = enrichment

    async def lookup(self, inn: str) -> RegistryExtract | None:
        dto = await self._enrichment.lookup_registry(inn, fresh=True)
        return extract_of(dto) if dto is not None else None
