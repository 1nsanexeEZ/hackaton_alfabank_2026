"""Imports every SQLAlchemy model so Base.metadata is complete (Alembic, tests).
A new module adds its `infrastructure.models` here."""

import src.applications.infrastructure.models  # noqa: F401
import src.clients.infrastructure.models  # noqa: F401
import src.core.messaging.inbox  # noqa: F401
import src.core.messaging.outbox  # noqa: F401
import src.decision.infrastructure.models  # noqa: F401
import src.enrichment.infrastructure.models  # noqa: F401
import src.identity.models  # noqa: F401
import src.notifications.infrastructure.models  # noqa: F401
import src.process.infrastructure.models  # noqa: F401
import src.products.infrastructure.models  # noqa: F401
import src.projector.infrastructure.models  # noqa: F401
import src.scoring.infrastructure.models  # noqa: F401
from src.core.infrastructure.database.base import Base

metadata = Base.metadata
