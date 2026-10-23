from __future__ import annotations

import httpx

from src.modules.enrichment.application.interfaces.sources import Sources
from src.modules.enrichment.infrastructure.adapters.aml_http import (
    PepHttpSource,
    RfmHttpSource,
    ZskHttpSource,
)
from src.modules.enrichment.infrastructure.adapters.bank_stop_list_http import (
    BankStopListHttpSource,
)
from src.modules.enrichment.infrastructure.adapters.bki_http import BkiHttpSource
from src.modules.enrichment.infrastructure.adapters.bki_person_http import BkiPersonHttpSource
from src.modules.enrichment.infrastructure.adapters.egrul_http import EgrulHttpSource
from src.modules.enrichment.infrastructure.adapters.fns_http import FnsHttpSource
from src.modules.enrichment.infrastructure.adapters.gir_bo_http import GirBoHttpSource
from src.modules.enrichment.infrastructure.adapters.kontur_http import KonturHttpSource
from src.modules.enrichment.infrastructure.config import EnrichmentSettings


def build_http_sources(config: EnrichmentSettings) -> Sources:
    client = httpx.AsyncClient(
        base_url=config.mocks_base_url, timeout=config.source_timeout_seconds
    )
    backoff = tuple(0.5 * 2**i for i in range(config.retries))
    return Sources(
        registry=EgrulHttpSource(client, backoff=backoff),
        tax=FnsHttpSource(client, backoff=backoff),
        bureau=BkiHttpSource(client, backoff=backoff),
        accounting=GirBoHttpSource(client, backoff=backoff),
        counterparty=KonturHttpSource(client, backoff=backoff),
        person_bureau=BkiPersonHttpSource(client, backoff=backoff),
        aml_lists=RfmHttpSource(client, backoff=backoff),
        pep=PepHttpSource(client, backoff=backoff),
        zsk=ZskHttpSource(client, backoff=backoff),
        bank_stop_list=BankStopListHttpSource(client, backoff=backoff),
    )
