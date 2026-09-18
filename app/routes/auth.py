from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers.auth_controller import (
    AuthContext,
    get_current_user,
    get_me,
    login_user,
    refresh,
    request_password_reset,
    reset_password,
    signup,
    validate_reset_token,
)
from app.database import get_db
from app.models.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    ResetPasswordRequest,
    ResetTokenResponse,
    SignupRequest,
    SignupResponse,
    TokenPair,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class MessageResponse(BaseModel):
    message: str


@router.post("/signup", response_model=SignupResponse, status_code=201)
async def signup_route(payload: SignupRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await signup(db, payload.org_name, payload.admin_email, payload.admin_password, payload.full_name)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/login", response_model=LoginResponse)
async def login_route(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await login_user(db, payload.email, payload.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/refresh", response_model=TokenPair)
def refresh_route(payload: RefreshRequest):
    try:
        return refresh(payload.refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/me", response_model=UserOut)
async def me_route(
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await get_me(db, ctx)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password_route(
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    await request_password_reset(db, payload.email)
    return MessageResponse(
        message="if an account exists for this email, a reset link has been sent"
    )


@router.get("/reset-password/{token}", response_model=ResetTokenResponse)
async def validate_reset_token_route(
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
async def reset_password_route(
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