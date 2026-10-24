"""Imports every SQLAlchemy model so Base.metadata is complete (Alembic, tests).
A new module adds its ORM models (`infrastructure.database.models`) here."""

import src.core.messaging.inbox  # noqa: F401
import src.core.messaging.outbox  # noqa: F401
import src.modules.applications.infrastructure.database.models  # noqa: F401
import src.modules.clients.infrastructure.database.models  # noqa: F401
import src.modules.decision.infrastructure.models  # noqa: F401
import src.modules.enrichment.infrastructure.database.models  # noqa: F401
import src.modules.identity.infrastructure.database.models  # noqa: F401
import src.modules.notifications.infrastructure.database.models  # noqa: F401
import src.modules.process.infrastructure.database.models  # noqa: F401
import src.modules.products.infrastructure.models  # noqa: F401
import src.modules.projector.infrastructure.database.models  # noqa: F401
import src.modules.scoring.infrastructure.models  # noqa: F401
import src.modules.support.infrastructure.database.models  # noqa: F401
from src.core.infrastructure.database.base import Base

metadata = Base.metadata
