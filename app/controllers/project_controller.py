import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers.auth_controller import AuthContext, is_project_manager
from app.models import (
    ActivityLog,
    OrgMembership,
    OrgRole,
    Project,
    ProjectMember,
    ProjectStatus,
    Task,
    TaskStatus,
    User,
)
from app.models.project_members import ProjectRole
from app.models.project_schemas import (
    ProgressOut,
    ProjectMemberOut,
    StatusCount,
    StatusDeleteResponse,
)

DEFAULT_STATUSES = ["To Do", "In Progress", "Done"]


class StatusInUseError(Exception):
    def __init__(self, count: int):
        self.count = count
        super().__init__(f"status is in use by {count} tasks")


async def _log_activity(
    db: AsyncSession,
    org_id: uuid.UUID,
    actor_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    extra_data: dict | None = None,
) -> None:
    db.add(
        ActivityLog(
            org_id=org_id,
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


async def _require_project_member_row(
    db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID
) -> ProjectMember:
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise LookupError("user is not a member of this project")
    return member


async def _member_out(db: AsyncSession, member: ProjectMember) -> ProjectMemberOut:
    user = await db.get(User, member.user_id)
    return ProjectMemberOut(
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=member.role,
        added_at=member.added_at,
    )


async def create_project(
    db: AsyncSession,
    org_id: uuid.UUID,
    creator_id: uuid.UUID,
    name: str,
    description: str | None,
) -> Project:
    project = Project(org_id=org_id, name=name, description=description, created_by=creator_id)
    db.add(project)
    await db.flush()

    for order, status_name in enumerate(DEFAULT_STATUSES):
        db.add(TaskStatus(project_id=project.id, name=status_name, order=order))

    await _log_activity(
        db, org_id, creator_id, "project.created", "project", project.id
    )
    await db.commit()
    await db.refresh(project)
    return project


async def list_projects(db: AsyncSession, ctx: AuthContext) -> list[Project]:
    if ctx.org_role in (OrgRole.org_admin,):
        result = await db.execute(
            select(Project)
            .where(Project.org_id == ctx.org_id)
            .order_by(Project.created_at.desc())
        )
    else:
        result = await db.execute(
            select(Project)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(Project.org_id == ctx.org_id, ProjectMember.user_id == ctx.user_id)
            .distinct()
            .order_by(Project.created_at.desc())
        )
    return result.scalars().all()


async def get_project(
    db: AsyncSession, project_id: uuid.UUID, org_id: uuid.UUID
) -> Project:
    return await _get_project_for_org(db, project_id, org_id)


async def update_project(
    db: AsyncSession,
    project_id: uuid.UUID,
    org_id: uuid.UUID,
    actor_id: uuid.UUID,
    name: str | None,
    description: str | None,
    status: ProjectStatus | None,
) -> Project:
    project = await _get_project_for_org(db, project_id, org_id)
    changes: dict[str, dict] = {}
    if name is not None and name != project.name:
        changes["name"] = {"old": project.name, "new": name}
        project.name = name
    if description is not None and description != project.description:
        changes["description"] = {"old": project.description, "new": description}
        project.description = description
    if status is not None and status != project.status:
        changes["status"] = {"old": project.status.value, "new": status.value}
        project.status = status

    if changes:
        await _log_activity(
            db,
            org_id,
            actor_id,
            "project.updated",
            "project",
            project.id,
            {"changes": changes},
        )
        await db.commit()
    await db.refresh(project)
    return project


async def delete_project(
    db: AsyncSession, project_id: uuid.UUID, org_id: uuid.UUID, actor_id: uuid.UUID
) -> None:
    project = await _get_project_for_org(db, project_id, org_id)
    await _log_activity(
        db,
        org_id,
        actor_id,
        "project.deleted",
        "project",
        project.id,
        {"name": project.name},
    )
    await db.delete(project)
    await db.commit()


async def assert_project_manager(
    db: AsyncSession, ctx: AuthContext, project_id: uuid.UUID
) -> None:
    project = await _get_project_for_org(db, project_id, ctx.org_id)
    if not await is_project_manager(ctx, db, project.id):
        raise PermissionError("requires project manager or org admin permission")


async def list_members(
    db: AsyncSession, project_id: uuid.UUID, org_id: uuid.UUID
) -> list[ProjectMemberOut]:
    await _get_project_for_org(db, project_id, org_id)
    result = await db.execute(
        select(ProjectMember, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.added_at)
    )
    return [
        ProjectMemberOut(
            user_id=member.user_id,
            full_name=user.full_name,
            email=user.email,
            role=member.role,
            added_at=member.added_at,
        )
        for member, user in result.all()
    ]


async def add_member(
    db: AsyncSession,
    project_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    role: ProjectRole,
    actor_id: uuid.UUID,
) -> ProjectMemberOut:
    await _get_project_for_org(db, project_id, org_id)

    membership = await db.execute(
        select(OrgMembership).where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == user_id,
        )
    )
    if membership.scalar_one_or_none() is None:
        raise ValueError("user is not a member of this org")

    existing = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError("user is already a member of this project")

    member = ProjectMember(project_id=project_id, user_id=user_id, role=role)
    db.add(member)
    await db.flush()
    await _log_activity(
        db,
        org_id,
        actor_id,
        "project.member.added",
        "project_member",
        member.id,
        {"user_id": str(user_id), "role": role.value},
    )
    await db.commit()
    return await _member_out(db, member)


async def update_member_role(
    db: AsyncSession,
    project_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    role: ProjectRole,
    actor_id: uuid.UUID,
) -> ProjectMemberOut:
    await _get_project_for_org(db, project_id, org_id)
    member = await _require_project_member_row(db, project_id, user_id)
    member.role = role
    await _log_activity(
        db,
        org_id,
        actor_id,
        "project.member.role.updated",
        "project_member",
        member.id,
        {"user_id": str(user_id), "role": role.value},
    )
    await db.commit()
    return await _member_out(db, member)


async def remove_member(
    db: AsyncSession,
    project_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    await _get_project_for_org(db, project_id, org_id)
    member = await _require_project_member_row(db, project_id, user_id)
    await _log_activity(
        db,
        org_id,
        actor_id,
        "project.member.removed",
        "project_member",
        member.id,
        {"user_id": str(user_id)},
    )
    await db.delete(member)
    await db.commit()


async def get_progress(
    db: AsyncSession, project_id: uuid.UUID, org_id: uuid.UUID
) -> ProgressOut:
    await _get_project_for_org(db, project_id, org_id)

    total_result = await db.execute(
        select(func.count(Task.id)).where(Task.project_id == project_id)
    )
    total = total_result.scalar_one()

    status_result = await db.execute(
        select(TaskStatus)
        .where(TaskStatus.project_id == project_id)
        .order_by(TaskStatus.order)
    )
    statuses = status_result.scalars().all()

    by_status = []
    for status in statuses:
        count_result = await db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == project_id, Task.status_id == status.id
            )
        )
        by_status.append(
            StatusCount(
                status_id=status.id, name=status.name, count=count_result.scalar_one()
            )
        )

    completed_id = statuses[-1].id if statuses else None
    completed = 0
    if completed_id is not None:
        completed_result = await db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == project_id, Task.status_id == completed_id
            )
        )
        completed = completed_result.scalar_one()

    overdue_filters = [Task.project_id == project_id, Task.due_date.isnot(None), Task.due_date < date.today()]
    if completed_id is not None:
        overdue_filters.append(Task.status_id != completed_id)
    overdue_result = await db.execute(
        select(func.count(Task.id)).where(*overdue_filters)
    )
    overdue = overdue_result.scalar_one()

    open_tasks = total - completed
    percent_done = round(completed / total * 100, 2) if total else 0.0

    return ProgressOut(
        total_tasks=total,
        completed_tasks=completed,
        open_tasks=open_tasks,
        percent_done=percent_done,
        overdue_tasks=overdue,
        by_status=by_status,
    )


async def list_statuses(
    db: AsyncSession, project_id: uuid.UUID, org_id: uuid.UUID
) -> list[TaskStatus]:
    await _get_project_for_org(db, project_id, org_id)
    result = await db.execute(
        select(TaskStatus)
        .where(TaskStatus.project_id == project_id)
        .order_by(TaskStatus.order)
    )
    return result.scalars().all()


async def create_status(
    db: AsyncSession,
    project_id: uuid.UUID,
    org_id: uuid.UUID,
    actor_id: uuid.UUID,
    name: str,
    color: str | None,
    order: int | None,
) -> TaskStatus:
    await _get_project_for_org(db, project_id, org_id)
    if order is None:
        max_result = await db.execute(
            select(func.max(TaskStatus.order)).where(TaskStatus.project_id == project_id)
        )
        order = (max_result.scalar_one() or -1) + 1

    status = TaskStatus(project_id=project_id, name=name, color=color, order=order)
    db.add(status)
    await db.flush()
    await _log_activity(
        db, org_id, actor_id, "project.status.created", "task_status", status.id,
        {"name": name, "order": order},
    )
    await db.commit()
    await db.refresh(status)
    return status


async def update_status(
    db: AsyncSession,
    project_id: uuid.UUID,
    org_id: uuid.UUID,
    status_id: uuid.UUID,
    actor_id: uuid.UUID,
    name: str | None,
    color: str | None,
    order: int | None,
) -> TaskStatus:
    await _get_project_for_org(db, project_id, org_id)
    status = await db.get(TaskStatus, status_id)
    if status is None or status.project_id != project_id:
        raise LookupError("status not found")

    if name is not None and name != status.name:
        status.name = name
    if color is not None and color != status.color:
        status.color = color or None
    if order is not None and order != status.order:
        status.order = order

    await _log_activity(
        db, org_id, actor_id, "project.status.updated", "task_status", status.id,
        {"name": status.name, "order": status.order, "color": status.color},
    )
    await db.commit()
    await db.refresh(status)
    return status


async def delete_status(
    db: AsyncSession,
    project_id: uuid.UUID,
    org_id: uuid.UUID,
    status_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> StatusDeleteResponse:
    await _get_project_for_org(db, project_id, org_id)
    status = await db.get(TaskStatus, status_id)
    if status is None or status.project_id != project_id:
        raise LookupError("status not found")

    count_result = await db.execute(
        select(func.count(Task.id)).where(Task.status_id == status_id)
    )
    affected = count_result.scalar_one()
    if affected > 0:
        raise StatusInUseError(affected)

    await _log_activity(
        db, org_id, actor_id, "project.status.deleted", "task_status", status.id,
        {"name": status.name},
    )
    await db.delete(status)
    await db.commit()
    return StatusDeleteResponse(deleted=True, affected_tasks=0)