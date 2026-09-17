import uuid
from datetime import date

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers.auth_controller import AuthContext, is_project_manager
from app.models import (
    ActivityLog,
    OrgMembership,
    Project,
    ProjectMember,
    Task,
    TaskAssignee,
    TaskStatus,
    User,
)
from app.models.project_members import ProjectRole
from app.models.task_schemas import (
    AssigneeOut,
    SubtaskCreateRequest,
    TaskActivityListResponse,
    TaskActivityOut,
    TaskListResponse,
    TaskOut,
    UpdatedByOut,
)


ASSIGNEE_ALLOWED_FIELDS = {"status_id"}


class SubtaskInUseError(Exception):
    def __init__(self, count: int):
        self.count = count
        super().__init__(f"task has {count} subtasks")


async def _log_activity(
    db: AsyncSession,
    org_id: uuid.UUID,
    project_id: uuid.UUID | None,
    actor_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    extra_data: dict | None = None,
) -> None:
    db.add(
        ActivityLog(
            org_id=org_id,
            project_id=project_id,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            extra_data=extra_data or {},
        )
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


async def _get_task(db: AsyncSession, task_id: uuid.UUID) -> Task:
    task = await db.get(Task, task_id)
    if task is None:
        raise LookupError("task not found")
    return task


async def _get_task_for_org(
    db: AsyncSession, task_id: uuid.UUID, org_id: uuid.UUID
) -> tuple[Task, Project]:
    task = await _get_task(db, task_id)
    project = await _get_project_for_org(db, task.project_id, org_id)
    return task, project


async def _first_status_id(
    db: AsyncSession, project_id: uuid.UUID
) -> uuid.UUID | None:
    result = await db.execute(
        select(TaskStatus)
        .where(TaskStatus.project_id == project_id)
        .order_by(TaskStatus.order)
        .limit(1)
    )
    status = result.scalar_one_or_none()
    return status.id if status else None


async def _validate_status_for_project(
    db: AsyncSession, project_id: uuid.UUID, status_id: uuid.UUID | None
) -> uuid.UUID | None:
    if status_id is None:
        return await _first_status_id(db, project_id)
    result = await db.execute(
        select(TaskStatus).where(
            TaskStatus.id == status_id,
            TaskStatus.project_id == project_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise LookupError("status not found in this project")
    return status_id


async def _require_org_membership(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == user_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise ValueError("user is not a member of this org")


async def _is_task_assignee(
    db: AsyncSession, task_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    result = await db.execute(
        select(TaskAssignee.id).where(
            TaskAssignee.task_id == task_id,
            TaskAssignee.user_id == user_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def _get_assignees(
    db: AsyncSession, task_id: uuid.UUID
) -> list[AssigneeOut]:
    result = await db.execute(
        select(TaskAssignee, User)
        .join(User, User.id == TaskAssignee.user_id)
        .where(TaskAssignee.task_id == task_id)
    )
    return [
        AssigneeOut(user_id=a.user_id, full_name=u.full_name, email=u.email)
        for a, u in result.all()
    ]


async def _subtask_count(db: AsyncSession, task_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count(Task.id)).where(Task.parent_task_id == task_id)
    )
    return result.scalar_one()


async def _updated_by_out(
    db: AsyncSession, user_id: uuid.UUID | None
) -> UpdatedByOut | None:
    if user_id is None:
        return None
    user = await db.get(User, user_id)
    if user is None:
        return None
    return UpdatedByOut(user_id=user.id, full_name=user.full_name, email=user.email)


async def _task_out(db: AsyncSession, task: Task) -> TaskOut:
    assignees = await _get_assignees(db, task.id)
    count = await _subtask_count(db, task.id)
    updated_by = await _updated_by_out(db, task.updated_by)
    return TaskOut(
        id=task.id,
        project_id=task.project_id,
        parent_task_id=task.parent_task_id,
        title=task.title,
        description=task.description,
        status_id=task.status_id,
        priority=task.priority,
        due_date=task.due_date,
        estimated_hours=task.estimated_hours,
        created_by=task.created_by,
        updated_by=updated_by,
        created_at=task.created_at,
        updated_at=task.updated_at,
        assignees=assignees,
        subtask_count=count,
    )


async def _set_assignees(
    db: AsyncSession, task_id: uuid.UUID, assignee_ids: list[uuid.UUID]
) -> None:
    await db.execute(
        select(TaskAssignee).where(TaskAssignee.task_id == task_id)
    )
    for user_id in assignee_ids:
        db.add(TaskAssignee(task_id=task_id, user_id=user_id))


async def _bulk_task_out(db: AsyncSession, tasks: list[Task]) -> list[TaskOut]:
    if not tasks:
        return []

    task_ids = [t.id for t in tasks]

    assignee_rows = await db.execute(
        select(TaskAssignee, User)
        .join(User, User.id == TaskAssignee.user_id)
        .where(TaskAssignee.task_id.in_(task_ids))
    )
    assignee_map: dict[uuid.UUID, list[AssigneeOut]] = {}
    for a, u in assignee_rows.all():
        assignee_map.setdefault(a.task_id, []).append(
            AssigneeOut(user_id=a.user_id, full_name=u.full_name, email=u.email)
        )

    count_rows = await db.execute(
        select(Task.parent_task_id, func.count(Task.id))
        .where(Task.parent_task_id.in_(task_ids))
        .group_by(Task.parent_task_id)
    )
    count_map = {pid: cnt for pid, cnt in count_rows.all()}

    updated_by_ids = {t.updated_by for t in tasks if t.updated_by}
    updated_by_users: dict[uuid.UUID, User] = {}
    if updated_by_ids:
        ub_rows = await db.execute(
            select(User).where(User.id.in_(updated_by_ids))
        )
        for u in ub_rows.scalars().all():
            updated_by_users[u.id] = u

    return [
        TaskOut(
            id=t.id,
            project_id=t.project_id,
            parent_task_id=t.parent_task_id,
            title=t.title,
            description=t.description,
            status_id=t.status_id,
            priority=t.priority,
            due_date=t.due_date,
            estimated_hours=t.estimated_hours,
            created_by=t.created_by,
            updated_by=(
                UpdatedByOut(
                    user_id=u.id, full_name=u.full_name, email=u.email
                )
                if (u := updated_by_users.get(t.updated_by)) is not None
                else None
            ),
            created_at=t.created_at,
            updated_at=t.updated_at,
            assignees=assignee_map.get(t.id, []),
            subtask_count=count_map.get(t.id, 0),
        )
        for t in tasks
    ]


async def _sync_assignees(
    db: AsyncSession,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    actor_id: uuid.UUID,
    task: Task,
    new_ids: list[uuid.UUID],
) -> None:
    for uid in new_ids:
        await _require_org_membership(db, org_id, uid)

    old_rows = await db.execute(
        select(TaskAssignee).where(TaskAssignee.task_id == task.id)
    )
    old_ids = {row.user_id for row in old_rows.scalars().all()}
    new_set = set(new_ids)

    to_remove = old_ids - new_set
    to_add = new_set - old_ids

    if to_remove:
        await db.execute(
            delete(TaskAssignee).where(
                TaskAssignee.task_id == task.id,
                TaskAssignee.user_id.in_(to_remove),
            )
        )
    for uid in to_add:
        db.add(TaskAssignee(task_id=task.id, user_id=uid))

    if to_remove or to_add:
        await _log_activity(
            db,
            org_id,
            project_id,
            actor_id,
            "task.assignees.updated",
            "task",
            task.id,
            {
                "added": [str(u) for u in sorted(to_add, key=str)],
                "removed": [str(u) for u in sorted(to_remove, key=str)],
            },
        )


async def create_task(
    db: AsyncSession,
    ctx: AuthContext,
    project_id: uuid.UUID,
    title: str,
    description: str | None,
    status_id: uuid.UUID | None,
    priority,
    due_date: date | None,
    estimated_hours: float | None,
    assignee_ids: list[uuid.UUID],
) -> TaskOut:
    project = await _get_project_for_org(db, project_id, ctx.org_id)
    status_id = await _validate_status_for_project(db, project.id, status_id)

    if assignee_ids:
        for uid in assignee_ids:
            await _require_org_membership(db, ctx.org_id, uid)

    task = Task(
        project_id=project.id,
        title=title,
        description=description,
        status_id=status_id,
        priority=priority,
        due_date=due_date,
        estimated_hours=estimated_hours,
        created_by=ctx.user_id,
    )
    db.add(task)
    await db.flush()

    for uid in assignee_ids:
        db.add(TaskAssignee(task_id=task.id, user_id=uid))

    await _log_activity(
        db,
        ctx.org_id,
        project.id,
        ctx.user_id,
        "task.created",
        "task",
        task.id,
        {"title": title},
    )
    await db.commit()
    await db.refresh(task)
    return await _task_out(db, task)


async def list_tasks(
    db: AsyncSession,
    ctx: AuthContext,
    project_id: uuid.UUID,
    status_id: uuid.UUID | None,
    assignee_id: uuid.UUID | None,
    priority,
    search: str | None,
    offset: int,
    limit: int,
) -> TaskListResponse:
    await _get_project_for_org(db, project_id, ctx.org_id)

    filters = [Task.project_id == project_id]

    if status_id is not None:
        filters.append(Task.status_id == status_id)

    if priority is not None:
        filters.append(Task.priority == priority)

    if assignee_id is not None:
        filters.append(
            Task.id.in_(
                select(TaskAssignee.task_id).where(
                    TaskAssignee.user_id == assignee_id
                )
            )
        )

    if search:
        pattern = f"%{search}%"
        filters.append(
            or_(
                Task.title.ilike(pattern),
                Task.description.ilike(pattern),
            )
        )

    count_result = await db.execute(
        select(func.count(Task.id)).where(*filters)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(Task)
        .where(*filters)
        .order_by(Task.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    tasks = list(result.scalars().all())
    items = await _bulk_task_out(db, tasks)

    return TaskListResponse(items=items, total=total, offset=offset, limit=limit)


async def get_task(
    db: AsyncSession, ctx: AuthContext, task_id: uuid.UUID
) -> TaskOut:
    task, _project = await _get_task_for_org(db, task_id, ctx.org_id)
    return await _task_out(db, task)


async def update_task(
    db: AsyncSession,
    ctx: AuthContext,
    task_id: uuid.UUID,
    fields_set: set[str],
    title: str | None,
    description: str | None,
    status_id: uuid.UUID | None,
    priority,
    due_date: date | None,
    estimated_hours: float | None,
) -> TaskOut:
    task, project = await _get_task_for_org(db, task_id, ctx.org_id)
    pm = await is_project_manager(ctx, db, project.id)
    is_assignee = await _is_task_assignee(db, task.id, ctx.user_id)

    if not pm and not is_assignee:
        raise PermissionError("only assignees or project manager can update this task")

    if not pm and fields_set - ASSIGNEE_ALLOWED_FIELDS:
        raise PermissionError("assignees can only update status")

    if pm:
        if status_id is not None:
            validated = await _validate_status_for_project(
                db, project.id, status_id
            )
            task.status_id = validated
        if title is not None:
            task.title = title
        if description is not None:
            task.description = description
        if priority is not None:
            task.priority = priority
        if due_date is not None:
            task.due_date = due_date
        if estimated_hours is not None:
            task.estimated_hours = estimated_hours
    else:
        if status_id is not None:
            validated = await _validate_status_for_project(
                db, project.id, status_id
            )
            task.status_id = validated

    task.updated_by = ctx.user_id

    await _log_activity(
        db,
        ctx.org_id,
        project.id,
        ctx.user_id,
        "task.updated",
        "task",
        task.id,
        {"fields": sorted(fields_set)},
    )
    await db.commit()
    await db.refresh(task)
    return await _task_out(db, task)


async def delete_task(
    db: AsyncSession, ctx: AuthContext, task_id: uuid.UUID
) -> None:
    task, project = await _get_task_for_org(db, task_id, ctx.org_id)

    subtask_count = await _subtask_count(db, task.id)
    if subtask_count > 0:
        raise SubtaskInUseError(subtask_count)

    await _log_activity(
        db,
        ctx.org_id,
        project.id,
        ctx.user_id,
        "task.deleted",
        "task",
        task.id,
        {"title": task.title},
    )
    await db.delete(task)
    await db.commit()


async def create_subtask(
    db: AsyncSession,
    ctx: AuthContext,
    task_id: uuid.UUID,
    title: str,
    description: str | None,
    status_id: uuid.UUID | None,
    priority,
    due_date: date | None,
    estimated_hours: float | None,
    assignee_ids: list[uuid.UUID],
) -> TaskOut:
    parent_task, project = await _get_task_for_org(db, task_id, ctx.org_id)
    status_id = await _validate_status_for_project(db, project.id, status_id)

    if assignee_ids:
        for uid in assignee_ids:
            await _require_org_membership(db, ctx.org_id, uid)

    task = Task(
        project_id=project.id,
        parent_task_id=parent_task.id,
        title=title,
        description=description,
        status_id=status_id,
        priority=priority,
        due_date=due_date,
        estimated_hours=estimated_hours,
        created_by=ctx.user_id,
    )
    db.add(task)
    await db.flush()

    for uid in assignee_ids:
        db.add(TaskAssignee(task_id=task.id, user_id=uid))

    await _log_activity(
        db,
        ctx.org_id,
        project.id,
        ctx.user_id,
        "task.created",
        "task",
        task.id,
        {"title": title, "parent_task_id": str(parent_task.id)},
    )
    await db.commit()
    await db.refresh(task)
    return await _task_out(db, task)


async def list_subtasks(
    db: AsyncSession, ctx: AuthContext, task_id: uuid.UUID
) -> list[TaskOut]:
    task, _project = await _get_task_for_org(db, task_id, ctx.org_id)

    result = await db.execute(
        select(Task)
        .where(Task.parent_task_id == task.id)
        .order_by(Task.created_at)
    )
    tasks = list(result.scalars().all())
    return await _bulk_task_out(db, tasks)


async def update_assignees(
    db: AsyncSession,
    ctx: AuthContext,
    task_id: uuid.UUID,
    new_ids: list[uuid.UUID],
) -> TaskOut:
    task, project = await _get_task_for_org(db, task_id, ctx.org_id)
    await _sync_assignees(db, ctx.org_id, project.id, ctx.user_id, task, new_ids)
    await db.commit()
    await db.refresh(task)
    return await _task_out(db, task)


async def list_task_activity(
    db: AsyncSession,
    ctx: AuthContext,
    task_id: uuid.UUID,
    offset: int,
    limit: int,
) -> TaskActivityListResponse:
    task, _project = await _get_task_for_org(db, task_id, ctx.org_id)

    filters = [
        ActivityLog.entity_type == "task",
        ActivityLog.entity_id == task.id,
    ]

    count_result = await db.execute(
        select(func.count(ActivityLog.id)).where(*filters)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(ActivityLog, User)
        .outerjoin(User, User.id == ActivityLog.actor_id)
        .where(*filters)
        .order_by(ActivityLog.created_at.asc())
        .offset(offset)
        .limit(limit)
    )

    items = [
        TaskActivityOut(
            id=log.id,
            actor_id=log.actor_id,
            actor_email=user.email if user else None,
            actor_full_name=user.full_name if user else None,
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            extra_data=log.extra_data or {},
            created_at=log.created_at,
        )
        for log, user in result.all()
    ]

    return TaskActivityListResponse(
        items=items, total=total, offset=offset, limit=limit
    )


async def list_my_tasks(
    db: AsyncSession,
    ctx: AuthContext,
    status_id: uuid.UUID | None,
    priority,
    search: str | None,
    offset: int,
    limit: int,
) -> TaskListResponse:
    filters = [
        Task.id.in_(
            select(TaskAssignee.task_id).where(
                TaskAssignee.user_id == ctx.user_id
            )
        )
    ]

    if status_id is not None:
        filters.append(Task.status_id == status_id)

    if priority is not None:
        filters.append(Task.priority == priority)

    if search:
        pattern = f"%{search}%"
        filters.append(
            or_(
                Task.title.ilike(pattern),
                Task.description.ilike(pattern),
            )
        )

    count_result = await db.execute(
        select(func.count(Task.id)).where(*filters)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(Task)
        .where(*filters)
        .order_by(Task.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    tasks = list(result.scalars().all())
    items = await _bulk_task_out(db, tasks)

    return TaskListResponse(items=items, total=total, offset=offset, limit=limit)
