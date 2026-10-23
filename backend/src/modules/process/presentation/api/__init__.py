"""Back office API of the engine: underwriter tasks, where an application is in
its route and the routes themselves (`tasks.read` / `tasks.update`)."""

from fastapi import APIRouter

from src.modules.process.presentation.api import processes, tasks, workflows

router = APIRouter()
router.include_router(tasks.router)
router.include_router(processes.router)
router.include_router(workflows.router)
