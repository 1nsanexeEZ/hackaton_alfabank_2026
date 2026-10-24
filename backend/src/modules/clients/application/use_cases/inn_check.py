"""Check of a company by INN before an application (back office): the company may be unknown
to the bank. Nothing is stored and nothing is published: the check only reads."""

from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import ValidationError
from src.modules.clients.application.dto.inn_check import InnCheckDTO, InnCheckRequestDTO
from src.modules.clients.application.interfaces.company_check import CompanyCheckSource
from src.modules.clients.application.interfaces.repositories import OrganizationRepository
from src.modules.clients.domain.inn_check import Declared, assess, inn_typo, not_found
from src.modules.clients.domain.value_objects import Inn


class CheckInnUseCase:
    def __init__(
        self, source: CompanyCheckSource, organizations: OrganizationRepository, clock: Clock
    ) -> None:
        self._source = source
        self._organizations = organizations
        self._clock = clock

    async def execute(self, request: InnCheckRequestDTO) -> InnCheckDTO:
        """A typo in the INN (check digit) — verdict `fail`, the sources are not asked; an
        INN the registry does not know — `not_found`; the registry did not answer —
        InfrastructureError (503)."""
        now = self._clock.now()
        try:
            inn = Inn(request.inn)
        except ValidationError as exc:
            if (exc.details or {}).get("code") != "bad_checksum":
                raise
            return InnCheckDTO.of(inn_typo(request.inn), now)
        record = await self._source.lookup(inn.value)
        if record is None:
            return InnCheckDTO.of(not_found(inn), now)
        client = await self._organizations.get_by_inn(inn.value)
        declared = Declared(ogrn=request.ogrn, kpp=request.kpp, name=request.name)
        result = assess(
            inn,
            declared,
            record,
            now.date(),
            client=client.verification if client is not None else None,
        )
        return InnCheckDTO.of(result, now, client.id if client is not None else None)
