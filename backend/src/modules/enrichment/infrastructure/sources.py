from __future__ import annotations

import httpx

from src.modules.enrichment.application.sources import Sources
from src.modules.enrichment.config import EnrichmentSettings
from src.modules.enrichment.infrastructure.adapters.bki_http import BkiHttpSource
from src.modules.enrichment.infrastructure.adapters.egrul_http import EgrulHttpSource
from src.modules.enrichment.infrastructure.adapters.fns_http import FnsHttpSource


def build_http_sources(config: EnrichmentSettings) -> Sources:
    client = httpx.AsyncClient(
        base_url=config.mocks_base_url, timeout=config.source_timeout_seconds
    )
    backoff = tuple(0.5 * 2**i for i in range(config.retries))
    return Sources(
        registry=EgrulHttpSource(client, backoff=backoff),
        tax=FnsHttpSource(client, backoff=backoff),
        bureau=BkiHttpSource(client, backoff=backoff),
    )
