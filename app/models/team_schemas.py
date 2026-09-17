import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.projects import ProjectStatus


class TeamCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    member_ids: list[uuid.UUID] = []


class TeamUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class TeamMemberAddRequest(BaseModel):
    user_id: uuid.UUID


class TeamMemberOut(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str
    joined_at: datetime

    model_config = {"from_attributes": True}


class TeamProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    status: ProjectStatus

    model_config = {"from_attributes": True}


class TeamOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    member_count: int
    created_at: datetime


class TeamDetailOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    created_at: datetime
    members: list[TeamMemberOut]
    projects: list[TeamProjectOut]