import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.tasks import TaskPriority


class AssigneeOut(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str


class UpdatedByOut(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    status_id: uuid.UUID | None = None
    priority: TaskPriority = TaskPriority.medium
    due_date: date | None = None
    estimated_hours: float | None = None
    assignee_ids: list[uuid.UUID] = []


class TaskUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status_id: uuid.UUID | None = None
    priority: TaskPriority | None = None
    due_date: date | None = None
    estimated_hours: float | None = None


class SubtaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    status_id: uuid.UUID | None = None
    priority: TaskPriority = TaskPriority.medium
    due_date: date | None = None
    estimated_hours: float | None = None
    assignee_ids: list[uuid.UUID] = []


class AssigneeUpdateRequest(BaseModel):
    assignee_ids: list[uuid.UUID]


class TaskOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    parent_task_id: uuid.UUID | None
    title: str
    description: str | None
    status_id: uuid.UUID | None
    priority: TaskPriority
    due_date: date | None
    estimated_hours: float | None
    created_by: uuid.UUID | None
    updated_by: UpdatedByOut | None
    created_at: datetime
    updated_at: datetime
    assignees: list[AssigneeOut]
    subtask_count: int


class TaskListResponse(BaseModel):
    items: list[TaskOut]
    total: int
    offset: int
    limit: int


class TaskActivityOut(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None
    actor_email: str | None
    actor_full_name: str | None
    action: str
    entity_type: str
    entity_id: uuid.UUID
    extra_data: dict = Field(default_factory=dict)
    created_at: datetime


class TaskActivityListResponse(BaseModel):
    items: list[TaskActivityOut]
    total: int
    offset: int
    limit: int