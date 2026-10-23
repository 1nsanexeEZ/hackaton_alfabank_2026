"""Companies of the client: card, members and their rights, financial reports.

`organizations.read` / `organizations.update` with the `org_member` policy:
somebody else's company is 404. Inside the company the rights table decides:
no `manage_members` / `edit_financials` — 403. Bank staff (no policy) read
every company and run the registry check, but change nothing else — 403.
"""

from fastapi import APIRouter

from src.modules.clients.presentation.api import financial_reports, members, organizations

router = APIRouter()
router.include_router(organizations.router)
router.include_router(members.router)
router.include_router(financial_reports.router)
