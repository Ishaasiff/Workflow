import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.org_memberships import OrgRole


class CreateInviteRequest(BaseModel):
    email: EmailStr
    role: OrgRole = OrgRole.member


class InviteOut(BaseModel):
    id: uuid.UUID
    email: str
    role: OrgRole
    expires_at: datetime
    accepted_at: datetime | None

    model_config = {"from_attributes": True}


class InviteTokenResponse(BaseModel):
    org_name: str
    inviter_name: str
    email: str
    role: OrgRole
    expires_at: datetime


class AcceptInviteRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)
