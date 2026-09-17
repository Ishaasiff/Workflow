import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.project_members import ProjectRole
from app.models.projects import ProjectStatus


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: ProjectStatus | None = None


class ProjectOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    description: str | None
    status: ProjectStatus
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectMemberOut(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str
    role: ProjectRole
    added_at: datetime

    model_config = {"from_attributes": True}


class ProjectMemberAddRequest(BaseModel):
    user_id: uuid.UUID
    role: ProjectRole = ProjectRole.member


class ProjectRoleUpdateRequest(BaseModel):
    role: ProjectRole


class StatusOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    order: int
    color: str | None

    model_config = {"from_attributes": True}


class StatusCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str | None = None
    order: int | None = None


class StatusUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = None
    order: int | None = None


class StatusDeleteResponse(BaseModel):
    deleted: bool
    affected_tasks: int


class StatusCount(BaseModel):
    status_id: uuid.UUID
    name: str
    count: int


class ProgressOut(BaseModel):
    total_tasks: int
    completed_tasks: int
    open_tasks: int
    percent_done: float
    overdue_tasks: int
    by_status: list[StatusCount]