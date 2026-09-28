import uuid

from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers.auth_controller import (
    AuthContext,
    refresh,
    request_password_reset,
    require_super_admin,
    reset_password,
    validate_reset_token,
)
from app.controllers import superadmin_controller as sa_fn
from app.database import get_db
from app.models.admin import (
    CreateOrganizationRequest,
    MembershipRoleUpdateRequest,
    OrganizationAdminOut,
    UserAdminOut,
)
from app.models.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    ResetPasswordRequest,
    ResetTokenResponse,
    TokenPair,
)

router = APIRouter(prefix="/superadmin", tags=["superadmin"])


class MessageResponse(BaseModel):
    message: str


@router.post("/organization", status_code=201)
async def create_organization(
    payload: CreateOrganizationRequest,
    ctx: AuthContext = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await sa_fn.create_organization(db, payload.name)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await sa_fn.login_super_admin(db, payload.email, payload.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/refresh", response_model=TokenPair)
async def refresh_route(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await refresh(payload.refresh_token, db, payload.org_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    await request_password_reset(db, payload.email)
    return MessageResponse(
        message="if an account exists for this email, a reset link has been sent"
    )


@router.get("/reset-password/{token}", response_model=ResetTokenResponse)
async def validate_reset_token(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await validate_reset_token(db, token)
    except LookupError as e:
        detail = str(e)
        if "already been used" in detail or "expired" in detail:
            raise HTTPException(status_code=410, detail=detail)
        raise HTTPException(status_code=404, detail=detail)


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        await reset_password(db, payload.token, payload.new_password)
    except LookupError as e:
        detail = str(e)
        if "already been used" in detail or "expired" in detail:
            raise HTTPException(status_code=410, detail=detail)
        raise HTTPException(status_code=404, detail=detail)
    return MessageResponse(message="password has been reset successfully")


@router.get("/organizations", response_model=list[OrganizationAdminOut])
async def list_organizations(
    ctx: AuthContext = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    return await sa_fn.list_organizations(db)


@router.get("/users", response_model=list[UserAdminOut])
async def list_users(
    ctx: AuthContext = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    return await sa_fn.list_users(db)


@router.patch("/users/{user_id}/suspend")
async def suspend_user(
    user_id: uuid.UUID,
    ctx: AuthContext = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await sa_fn.suspend_user(db, user_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/memberships/{membership_id}/role")
async def update_membership_role(
    membership_id: uuid.UUID,
    payload: MembershipRoleUpdateRequest,
    ctx: AuthContext = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await sa_fn.update_membership_role(db, membership_id, payload.org_id, payload.role)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))