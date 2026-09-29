import logging
import uuid
from datetime import datetime

from sqlalchemy import delete, func, select

logger = logging.getLogger(__name__)
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ActivityLog,
    OrgMembership,
    OrgRole,
    Organization,
    Project,
    ProjectMember,
    User,
    Team,
    TeamMember,
)
from app.models.admin import MemberOut
from app.models.organization_schemas import ActivityLogListResponse, ActivityLogOut


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


async def _require_membership(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID
) -> OrgMembership:
    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == user_id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise LookupError("user is not a member of this org")
    return membership


async def _member_out(db: AsyncSession, membership: OrgMembership) -> MemberOut:
    user = await db.get(User, membership.user_id)
    return MemberOut(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        role=membership.role,
        joined_at=membership.joined_at,
    )


async def _get_org(db: AsyncSession, org_id: uuid.UUID) -> Organization:
    org = await db.get(Organization, org_id)
    if org is None:
        raise LookupError("organization not found")
    return org


async def get_org(db: AsyncSession, org_id: uuid.UUID) -> Organization:
    return await _get_org(db, org_id)


async def update_org(
    db: AsyncSession,
    org_id: uuid.UUID,
    actor_id: uuid.UUID,
    name: str | None,
    logo_url: str | None,
) -> Organization:
    org = await _get_org(db, org_id)
    changes: dict[str, dict] = {}
    if name is not None and name != org.name:
        changes["name"] = {"old": org.name, "new": name}
        org.name = name
    if logo_url is not None and logo_url != org.logo_url:
        changes["logo_url"] = {"old": org.logo_url, "new": logo_url or None}
        org.logo_url = logo_url or None

    if changes:
        await _log_activity(
            db,
            org_id=org_id,
            actor_id=actor_id,
            action="organization.updated",
            entity_type="organization",
            entity_id=org_id,
            extra_data={"changes": changes},
        )
        await db.commit()
    await db.refresh(org)
    return org


async def list_members(
    db: AsyncSession, org_id: uuid.UUID, offset: int, limit: int
) -> list[MemberOut]:
    await _get_org(db, org_id)
    result = await db.execute(
        select(OrgMembership, User)
        .outerjoin(User, User.id == OrgMembership.user_id)
        .where(OrgMembership.org_id == org_id)
        .order_by(OrgMembership.joined_at)
        .offset(offset)
        .limit(limit)
    )
    rows = result.all()
    logger.debug(
        "list_members(org_id=%s) returned %d rows",
        org_id,
        len(rows),
    )
    return [
        MemberOut(
            user_id=membership.user_id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            role=membership.role,
            joined_at=membership.joined_at,
        )
        for membership, user in rows
    ]


async def count_members(db: AsyncSession, org_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count(OrgMembership.id)).where(OrgMembership.org_id == org_id)
    )
    return result.scalar_one()


async def update_member_role(
    db: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    role: OrgRole,
    caller_id: uuid.UUID,
) -> MemberOut:
    if role == OrgRole.super_admin:
        raise PermissionError("super_admin can only be granted by a super admin")

    membership = await _require_membership(db, org_id, user_id)
    if membership.role == OrgRole.super_admin:
        raise PermissionError("cannot change a super admin")

    if (
        user_id == caller_id
        and membership.role == OrgRole.org_admin
        and role != OrgRole.org_admin
    ):
        admin_count = await db.execute(
            select(func.count(OrgMembership.id)).where(
                OrgMembership.org_id == org_id,
                OrgMembership.role == OrgRole.org_admin,
            )
        )
        if admin_count.scalar_one() <= 1:
            raise ValueError("cannot demote the last remaining org admin")

    membership.role = role
    await _log_activity(
        db,
        org_id=org_id,
        actor_id=caller_id,
        action="organization.member.role.updated",
        entity_type="org_membership",
        entity_id=membership.id,
        extra_data={"user_id": str(user_id), "role": role.value},
    )
    await db.commit()
    await db.refresh(membership)
    return await _member_out(db, membership)


async def remove_member(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, caller_id: uuid.UUID
) -> None:
    if user_id == caller_id:
        raise ValueError("cannot remove yourself")

    membership = await _require_membership(db, org_id, user_id)
    if membership.role in (OrgRole.super_admin, OrgRole.org_admin):
        raise PermissionError("cannot remove an admin")

    await db.execute(
        delete(ProjectMember).where(
            ProjectMember.user_id == user_id,
            ProjectMember.project_id.in_(
                select(Project.id).where(Project.org_id == org_id)
            ),
        )
    )
    await db.execute(
        delete(TeamMember).where(
            TeamMember.user_id == user_id,
            TeamMember.team_id.in_(
                select(Team.id).where(Team.org_id == org_id)
            ),
        )
    )
    await db.delete(membership)
    await _log_activity(
        db,
        org_id=org_id,
        actor_id=caller_id,
        action="organization.member.removed",
        entity_type="org_membership",
        entity_id=membership.id,
        extra_data={"user_id": str(user_id)},
    )
    await db.commit()


async def list_activity_log(
    db: AsyncSession,
    org_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    action: str | None,
    from_dt: datetime | None,
    to_dt: datetime | None,
    offset: int,
    limit: int,
) -> ActivityLogListResponse:
    await _get_org(db, org_id)

    filters = [ActivityLog.org_id == org_id]
    if actor_id is not None:
        filters.append(ActivityLog.actor_id == actor_id)
    if action is not None:
        filters.append(ActivityLog.action == action)
    if from_dt is not None:
        filters.append(ActivityLog.created_at >= from_dt)
    if to_dt is not None:
        filters.append(ActivityLog.created_at <= to_dt)

    count_result = await db.execute(
        select(func.count(ActivityLog.id)).where(*filters)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(ActivityLog)
        .where(*filters)
        .order_by(ActivityLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = result.scalars().all()

    return ActivityLogListResponse(
        items=[
            ActivityLogOut(
                id=log.id,
                actor_id=log.actor_id,
                action=log.action,
                entity_type=log.entity_type,
                entity_id=log.entity_id,
                metadata=log.extra_data,
                created_at=log.created_at,
            )
            for log in rows
        ],
        total=total,
        offset=offset,
        limit=limit,
    )