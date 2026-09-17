import uuid
from datetime import date

from pydantic import BaseModel


class BurndownPoint(BaseModel):
    date: date
    remaining_count: int
    ideal_count: float


class WorkloadUser(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str


class WorkloadEntry(BaseModel):
    user: WorkloadUser
    total_tasks: int
    in_progress: int
    overdue: int


class OrgOverviewOut(BaseModel):
    total_projects: int
    active_projects: int
    total_tasks: int
    completed_tasks: int
    completion_rate: float
    tasks_completed_this_week: int