import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers import organization_controller as org_fn
from app.controllers.auth_controller import (
    AuthContext,
    require_org_admin,
    require_org_member,
)
from app.database import get_db
from app.models.admin import MemberOut, RoleUpdateRequest
from app.models.organization_schemas import (
    ActivityLogListResponse,
    MemberListResponse,
    OrgProfileOut,
    OrgUpdateRequest,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _require_org_match(ctx: AuthContext, org_id: uuid.UUID) -> None:
    if ctx.org_id != org_id:
        raise HTTPException(status_code=403, detail="not a member of this organization")


@router.get("/{org_id}", response_model=OrgProfileOut)
async def get_organization_profile(
    org_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    _require_org_match(ctx, org_id)
    try:
        return await org_fn.get_org(db, org_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{org_id}", response_model=OrgProfileOut)
async def update_organization(
    org_id: uuid.UUID,
    payload: OrgUpdateRequest,
    ctx: AuthContext = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    _require_org_match(ctx, org_id)
    try:
        return await org_fn.update_org(
            db,
            org_id,
            ctx.user_id,
            payload.name if "name" in payload.model_fields_set else None,
            payload.logo_url if "logo_url" in payload.model_fields_set else None,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{org_id}/members", response_model=MemberListResponse)
async def list_org_members(
    org_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    _require_org_match(ctx, org_id)
    try:
        items = await org_fn.list_members(db, org_id, offset, limit)
        total = await org_fn.count_members(db, org_id)
        return MemberListResponse(items=items, total=total, offset=offset, limit=limit)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{org_id}/members/{user_id}", response_model=MemberOut)
async def update_org_member_role(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: RoleUpdateRequest,
    ctx: AuthContext = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    _require_org_match(ctx, org_id)
    try:
        return await org_fn.update_member_role(db, org_id, user_id, payload.role, ctx.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{org_id}/members/{user_id}", status_code=204)
async def remove_org_member(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    _require_org_match(ctx, org_id)
    try:
        await org_fn.remove_member(db, org_id, user_id, ctx.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return None


@router.get("/{org_id}/activity-log", response_model=ActivityLogListResponse)
async def get_org_activity_log(
    org_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
    user: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None),
    from_dt: datetime | None = Query(default=None, alias="from"),
    to_dt: datetime | None = Query(default=None, alias="to"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    _require_org_match(ctx, org_id)
    try:
        return await org_fn.list_activity_log(
            db, org_id, user, action, from_dt, to_dt, offset, limit
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))