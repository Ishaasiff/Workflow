import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers import team_controller as team_fn
from app.controllers.auth_controller import (
    AuthContext,
    require_org_admin,
    require_org_member,
)
from app.database import get_db
from app.models.team_schemas import (
    TeamCreateRequest,
    TeamDetailOut,
    TeamMemberAddRequest,
    TeamMemberOut,
    TeamOut,
    TeamUpdateRequest,
)

router = APIRouter(prefix="/teams", tags=["teams"])


@router.post("", response_model=TeamOut, status_code=201)
async def create_team(
    payload: TeamCreateRequest,
    ctx: AuthContext = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await team_fn.create_team(db, ctx, payload.name, payload.member_ids)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("", response_model=list[TeamOut])
async def list_teams(
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    return await team_fn.list_teams(db, ctx)


@router.get("/{team_id}", response_model=TeamDetailOut)
async def get_team(
    team_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await team_fn.get_team(db, ctx, team_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.patch("/{team_id}", response_model=TeamOut)
async def update_team(
    team_id: uuid.UUID,
    payload: TeamUpdateRequest,
    ctx: AuthContext = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await team_fn.update_team(db, ctx, team_id, payload.name)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/{team_id}", status_code=204)
async def delete_team(
    team_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        await team_fn.delete_team(db, ctx, team_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return None


@router.post("/{team_id}/members", response_model=TeamMemberOut, status_code=201)
async def add_member(
    team_id: uuid.UUID,
    payload: TeamMemberAddRequest,
    ctx: AuthContext = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await team_fn.add_member(db, ctx, team_id, payload.user_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/{team_id}/members/{user_id}", status_code=204)
async def remove_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        await team_fn.remove_member(db, ctx, team_id, user_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return None