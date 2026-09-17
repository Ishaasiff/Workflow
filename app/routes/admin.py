import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers.auth_controller import AuthContext, require_org_admin
from app.controllers import admin_controller as admin_fn
from app.database import get_db
from app.models.admin import MemberCreateRequest, MemberOut, RoleUpdateRequest

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/members", response_model=list[MemberOut])
async def list_members(
    ctx: AuthContext = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    return await admin_fn.list_members(db, ctx.org_id)


@router.post("/members", response_model=MemberOut, status_code=201)
async def add_member(
    payload: MemberCreateRequest,
    ctx: AuthContext = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await admin_fn.add_member(db, ctx.org_id, payload.email, payload.role, payload.full_name, payload.password)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.patch("/members/{user_id}/role", response_model=MemberOut)
async def update_member_role(
    user_id: uuid.UUID,
    payload: RoleUpdateRequest,
    ctx: AuthContext = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await admin_fn.update_member_role(db, ctx.org_id, user_id, payload.role)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/members/{user_id}/suspend", response_model=MemberOut)
async def suspend_member(
    user_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await admin_fn.suspend_member(db, ctx.org_id, user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/members/{user_id}", status_code=204)
async def remove_member(
    user_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        await admin_fn.remove_member(db, ctx.org_id, user_id, ctx.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return None