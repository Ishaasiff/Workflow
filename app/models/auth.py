import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.organization import PlanTier


class SignupRequest(BaseModel):
    org_name: str = Field(min_length=1, max_length=100)
    admin_email: EmailStr
    admin_password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=100)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    org_id: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class ResetTokenResponse(BaseModel):
    email: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_super_admin: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    plan_tier: PlanTier

    model_config = {"from_attributes": True}


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class SignupResponse(BaseModel):
    user: UserOut
    org: OrganizationOut
    token: TokenPair


class LoginResponse(BaseModel):
    user: UserOut
    token: TokenPair