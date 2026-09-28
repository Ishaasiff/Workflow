import logging

from fastapi import FastAPI

logging.basicConfig(level=logging.DEBUG)

from app.routes.auth import router as auth_router
from app.routes.admin import router as admin_router
from app.routes.superadmin import router as superadmin_router
from app.routes.organzations import router as organizations_router
from app.routes.projects import router as projects_router
from app.routes.invites import router as invites_router
from app.routes.teams import router as teams_router
from app.routes.tasks import router as tasks_router
from app.routes.reports import router as reports_router

app = FastAPI(title="Workflow API", version="0.1.0")


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(superadmin_router)
app.include_router(organizations_router)
app.include_router(projects_router)
app.include_router(invites_router)
app.include_router(teams_router)
app.include_router(tasks_router)
app.include_router(reports_router)