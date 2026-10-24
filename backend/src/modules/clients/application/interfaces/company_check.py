from typing import Protocol

from src.modules.clients.domain.inn_check import CompanyRecord


class CompanyCheckSource(Protocol):
    """What the external sources say about a company by its INN, before any application and
    whether or not the company is a client: ЕГРЮЛ/ЕГРИП, the tax service, Kontur, the bank
    stop list. On the stand — external-mocks through enrichment; a real provider is another
    adapter behind this port."""

    async def lookup(self, inn: str) -> CompanyRecord | None:
        """None — the registry does not know the INN. InfrastructureError — the registry did
        not answer or answered with data we cannot read. Another source that did not answer
        is None in the record."""
        ...
