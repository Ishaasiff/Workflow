import uuid
from bisect import bisect_right
from datetime import date, datetime, timezone, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers.auth_controller import AuthContext
from app.models import (
    Organization,
    Project,
    ProjectStatus,
    Task,
    TaskAssignee,
    TaskStatus,
    User,
)
from app.models.report_schemas import (
    BurndownPoint,
    OrgOverviewOut,
    WorkloadEntry,
    WorkloadUser,
)


async def _get_project(db: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise LookupError("project not found")
    return project


async def _get_project_for_org(
    db: AsyncSession, project_id: uuid.UUID, org_id: uuid.UUID
) -> Project:
    project = await _get_project(db, project_id)
    if project.org_id != org_id:
        raise PermissionError("not a member of this project")
    return project


async def _get_statuses(
    db: AsyncSession, project_id: uuid.UUID
) -> list[TaskStatus]:
    result = await db.execute(
        select(TaskStatus)
        .where(TaskStatus.project_id == project_id)
        .order_by(TaskStatus.order)
    )
    return list(result.scalars().all())


def _completed_status_id(statuses: list[TaskStatus]) -> uuid.UUID | None:
    return statuses[-1].id if statuses else None


def _in_progress_status_id(statuses: list[TaskStatus]) -> uuid.UUID | None:
    for status in statuses:
        if status.name.strip().lower() == "in progress":
            return status.id
    if len(statuses) >= 2:
        return statuses[1].id
    return None


async def get_burndown(
    db: AsyncSession, ctx: AuthContext, project_id: uuid.UUID
) -> list[BurndownPoint]:
    project = await _get_project_for_org(db, project_id, ctx.org_id)

    statuses = await _get_statuses(db, project_id)
    completed_id = _completed_status_id(statuses)

    result = await db.execute(select(Task).where(Task.project_id == project_id))
    tasks = list(result.scalars().all())

    start_date = project.created_at.date()
    today = date.today()
    end_date = today
    for t in tasks:
        if t.due_date is not None and t.due_date > end_date:
            end_date = t.due_date
    if end_date < start_date:
        end_date = start_date

    created_dates = sorted(t.created_at.date() for t in tasks)
    completed_dates = sorted(
        t.updated_at.date()
        for t in tasks
        if t.updated_at is not None
        and completed_id is not None
        and t.status_id == completed_id
    )

    total = len(tasks)
    span_days = max((end_date - start_date).days, 1)

    points = []
    for offset in range(span_days + 1):
        day = start_date + timedelta(days=offset)
        created_cum = bisect_right(created_dates, day)
        completed_cum = bisect_right(completed_dates, day)
        remaining = max(created_cum - completed_cum, 0)
        ideal = round(total * (1 - offset / span_days), 2)
        points.append(
            BurndownPoint(
                date=day,
                remaining_count=remaining,
                ideal_count=ideal,
            )
        )
    return points


async def get_workload(
    db: AsyncSession, ctx: AuthContext, project_id: uuid.UUID
) -> list[WorkloadEntry]:
    project = await _get_project_for_org(db, project_id, ctx.org_id)

    statuses = await _get_statuses(db, project_id)
    completed_id = _completed_status_id(statuses)
    in_progress_id = _in_progress_status_id(statuses)

    result = await db.execute(
        select(TaskAssignee, Task, User)
        .join(Task, Task.id == TaskAssignee.task_id)
        .join(User, User.id == TaskAssignee.user_id)
        .where(Task.project_id == project.id)
    )

    totals: dict[uuid.UUID, int] = {}
    in_progress: dict[uuid.UUID, int] = {}
    overdue: dict[uuid.UUID, int] = {}
    users: dict[uuid.UUID, User] = {}
    today = date.today()

    for ta, task, user in result.all():
        totals[user.id] = totals.get(user.id, 0) + 1
        users[user.id] = user
        if in_progress_id is not None and task.status_id == in_progress_id:
            in_progress[user.id] = in_progress.get(user.id, 0) + 1
        if (
            task.due_date is not None
            and task.due_date < today
            and task.status_id != completed_id
        ):
            overdue[user.id] = overdue.get(user.id, 0) + 1

    entries = [
        WorkloadEntry(
            user=WorkloadUser(
                user_id=uid,
                full_name=user.full_name,
                email=user.email,
            ),
            total_tasks=totals[uid],
            in_progress=in_progress.get(uid, 0),
            overdue=overdue.get(uid, 0),
        )
        for uid, user in users.items()
    ]
    entries.sort(key=lambda e: e.total_tasks, reverse=True)
    return entries


async def get_org_overview(
    db: AsyncSession, ctx: AuthContext, org_id: uuid.UUID
) -> OrgOverviewOut:
    org = await db.get(Organization, org_id)
    if org is None:
        raise LookupError("organization not found")

    project_result = await db.execute(
        select(Project).where(Project.org_id == org_id)
    )
    projects = list(project_result.scalars().all())
    active_projects = sum(1 for p in projects if p.status == ProjectStatus.active)

    total_tasks = 0
    completed_tasks = 0
    tasks_completed_this_week = 0

    if projects:
        count_result = await db.execute(
            select(func.count(Task.id)).where(
                Task.project_id.in_([p.id for p in projects])
            )
        )
        total_tasks = count_result.scalar_one()

        week_start = datetime.now(timezone.utc) - timedelta(days=7)
        for p in projects:
            statuses = await _get_statuses(db, p.id)
            completed_id = _completed_status_id(statuses)
            if completed_id is None:
                continue
            completed_result = await db.execute(
                select(func.count(Task.id)).where(
                    Task.project_id == p.id,
                    Task.status_id == completed_id,
                )
            )
            completed_tasks += completed_result.scalar_one()
            week_result = await db.execute(
                select(func.count(Task.id)).where(
                    Task.project_id == p.id,
                    Task.status_id == completed_id,
                    Task.updated_at >= week_start,
                )
            )
            tasks_completed_this_week += week_result.scalar_one()

    completion_rate = round(completed_tasks / total_tasks * 100, 2) if total_tasks else 0.0

    return OrgOverviewOut(
        total_projects=len(projects),
        active_projects=active_projects,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        completion_rate=completion_rate,
        tasks_completed_this_week=tasks_completed_this_week,
    )