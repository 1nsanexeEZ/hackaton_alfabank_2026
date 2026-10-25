"""Seed of decision: pre-approved offers for demo companies.

Companies come from the clients seed, not from registration events, so the offers
are recalculated here with the same use case the `clients.events` consumer runs.
Idempotent: a recalculation replaces every offer of the company. No event is sent:
the seed runs on each start and must not notify anybody.
"""

import logging
from typing import TYPE_CHECKING

from seed.demo_data import COMPANIES
from src.modules.clients.facade import ClientsFacade
from src.modules.clients.infrastructure.repositories.organization import (
    SqlAlchemyOrganizationRepository,
)
from src.modules.decision.application.policy_versions import ActivePolicyProvider
from src.modules.decision.application.pre_approval import RecalculatePreApprovedUseCase
from src.modules.decision.infrastructure.config_loader import CreditPolicyDocuments
from src.modules.decision.infrastructure.repository import (
    SqlAlchemyPolicyVersionRepository,
    SqlAlchemyPreApprovedOfferRepository,
)
from src.modules.market.facade import MarketFacade
from src.modules.products.facade import ProductsFacade
from src.modules.scoring.facade import ScoringFacade

if TYPE_CHECKING:
    from seed.run import SeedContext

logger = logging.getLogger(__name__)

_NEEDED = (ClientsFacade, ProductsFacade, ScoringFacade, MarketFacade)


async def seed(context: "SeedContext") -> None:
    missing = [key.__name__ for key in _NEEDED if not context.facades.has(key)]
    if missing:
        logger.warning("Pre-approved offers are skipped, facades are not registered: %s", missing)
        return
    async with context.session_factory() as session:
        key_rate = (await context.facades.get(MarketFacade, session).key_rate()).value
        # Как у консьюмера: активная версия политики админа или встроенная.
        policy = await ActivePolicyProvider(CreditPolicyDocuments()).active(
            SqlAlchemyPolicyVersionRepository(session)
        )
        organizations = SqlAlchemyOrganizationRepository(session)
        use_case = RecalculatePreApprovedUseCase(
            SqlAlchemyPreApprovedOfferRepository(session),
            policy,
            context.facades.get(ClientsFacade, session),
            context.facades.get(ProductsFacade, session),
            context.facades.get(ScoringFacade, session),
            context.clock,
            key_rate,
        )
        for company in COMPANIES:
            org = await organizations.get_by_inn(company.inn)
            if org is None:
                logger.warning(
                    "Demo company %s is not seeded: no pre-approved offers", company.code
                )
                continue
            await use_case.recalculate(org.id)
        await session.commit()
