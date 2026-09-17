import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.admin import MemberOut
from app.models.organization import PlanTier


class OrgUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    logo_url: str | None = None
    plan_tier: PlanTier | None = None


class OrgProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    logo_url: str | None
    plan_tier: PlanTier
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MemberListResponse(BaseModel):
    items: list[MemberOut]
    total: int
    offset: int
    limit: int


class ActivityLogOut(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: uuid.UUID
    metadata: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class ActivityLogListResponse(BaseModel):
    items: list[ActivityLogOut]
    total: int
    offset: int
    limit: int