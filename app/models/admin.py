import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.org_memberships import OrgRole
from app.models.organization import PlanTier


class MemberCreateRequest(BaseModel):
    email: EmailStr
    role: OrgRole = OrgRole.member
    full_name: str | None = Field(default=None, max_length=100)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class RoleUpdateRequest(BaseModel):
    role: OrgRole


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    role: OrgRole
    joined_at: datetime

    model_config = {"from_attributes": True}


class OrganizationAdminOut(BaseModel):
    id: uuid.UUID
    name: str
    plan_tier: PlanTier
    member_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class MembershipRoleUpdateRequest(BaseModel):
    org_id: uuid.UUID
    role: OrgRole


class UserAdminOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    created_at: datetime
    orgs: list[dict]

    model_config = {"from_attributes": True}


class CreateOrganizationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)