"""Imports every SQLAlchemy model so Base.metadata is complete (Alembic, tests).
A new module adds its `infrastructure.models` here."""

import src.core.messaging.inbox  # noqa: F401
import src.core.messaging.outbox  # noqa: F401
import src.modules.applications.infrastructure.models  # noqa: F401
import src.modules.clients.infrastructure.models  # noqa: F401
import src.modules.decision.infrastructure.models  # noqa: F401
import src.modules.enrichment.infrastructure.models  # noqa: F401
import src.modules.identity.models  # noqa: F401
import src.modules.notifications.infrastructure.models  # noqa: F401
import src.modules.process.infrastructure.models  # noqa: F401
import src.modules.products.infrastructure.models  # noqa: F401
import src.modules.projector.infrastructure.models  # noqa: F401
import src.modules.scoring.infrastructure.models  # noqa: F401
from src.core.infrastructure.database.base import Base

metadata = Base.metadata
