from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers.auth_controller import (
    AuthContext,
    require_org_admin,
)
from app.controllers.invite_controller import (
    accept_invite,
    create_invite,
    validate_invite_token,
)
from app.core.plans import PlanLimitError
from app.database import get_db
from app.models.auth import TokenPair, UserOut
from app.models.invite_schemas import (
    AcceptInviteRequest,
    CreateInviteRequest,
    InviteOut,
    InviteTokenResponse,
)

router = APIRouter(prefix="/invites", tags=["invites"])


class AcceptInviteResponse(BaseModel):
    user: UserOut
    token: TokenPair


@router.post("", response_model=InviteOut, status_code=201)
async def create_invite_route(
    payload: CreateInviteRequest,
    ctx: AuthContext = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        invite = await create_invite(db, ctx, payload.email, payload.role)
        return invite
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except PlanLimitError as e:
        raise HTTPException(status_code=402, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/{token}", response_model=InviteTokenResponse)
async def get_invite_route(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await validate_invite_token(db, token)
    except LookupError as e:
        detail = str(e)
        if "already been accepted" in detail or "expired" in detail:
            raise HTTPException(status_code=410, detail=detail)
        raise HTTPException(status_code=404, detail=detail)


@router.post("/{token}/accept", response_model=AcceptInviteResponse)
async def accept_invite_route(
    token: str,
    payload: AcceptInviteRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await accept_invite(db, token, payload.full_name, payload.password)
        return AcceptInviteResponse(
            user=UserOut.model_validate(result["user"]),
            token=result["token"],
        )
    except PlanLimitError as e:
        raise HTTPException(status_code=402, detail=str(e))
    except LookupError as e:
        detail = str(e)
        if "already been accepted" in detail or "expired" in detail:
            raise HTTPException(status_code=410, detail=detail)
        raise HTTPException(status_code=404, detail=detail)
