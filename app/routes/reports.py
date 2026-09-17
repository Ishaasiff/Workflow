import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers import reports_controller as report_fn
from app.controllers.auth_controller import (
    AuthContext,
    assert_project_access,
    require_org_admin,
    require_org_member,
)
from app.database import get_db
from app.models.report_schemas import (
    BurndownPoint,
    OrgOverviewOut,
    WorkloadEntry,
)

router = APIRouter(tags=["reports"])


@router.get(
    "/projects/{project_id}/reports/burndown",
    response_model=list[BurndownPoint],
)
async def get_burndown(
    project_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    await assert_project_access(ctx, db, project_id)
    try:
        return await report_fn.get_burndown(db, ctx, project_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get(
    "/projects/{project_id}/reports/workload",
    response_model=list[WorkloadEntry],
)
async def get_workload(
    project_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    await assert_project_access(ctx, db, project_id)
    try:
        return await report_fn.get_workload(db, ctx, project_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get(
    "/organizations/{org_id}/reports/overview",
    response_model=OrgOverviewOut,
)
async def get_org_overview(
    org_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    if ctx.org_id != org_id:
        raise HTTPException(
            status_code=403, detail="not a member of this organization"
        )
    try:
        return await report_fn.get_org_overview(db, ctx, org_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))