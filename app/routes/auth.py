from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers.auth_controller import (
    AuthContext,
    get_current_user,
    get_me,
    login_user,
    refresh,
    signup,
)
from app.database import get_db
from app.models.auth import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    SignupRequest,
    SignupResponse,
    TokenPair,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


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