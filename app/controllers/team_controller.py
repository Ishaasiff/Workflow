import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers.auth_controller import AuthContext
from app.models import (
    ActivityLog,
    OrgMembership,
    Project,
    ProjectMember,
    Team,
    TeamMember,
    User,
)
from app.models.team_schemas import (
    TeamDetailOut,
    TeamMemberOut,
    TeamOut,
    TeamProjectOut,
)


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


async def _get_team(db: AsyncSession, team_id: uuid.UUID) -> Team:
    team = await db.get(Team, team_id)
    if team is None:
        raise LookupError("team not found")
    return team


async def _get_team_for_org(
    db: AsyncSession, team_id: uuid.UUID, org_id: uuid.UUID
) -> Team:
    team = await _get_team(db, team_id)
    if team.org_id != org_id:
        raise PermissionError("not a member of this org")
    return team


async def _require_team_member_row(
    db: AsyncSession, team_id: uuid.UUID, user_id: uuid.UUID
) -> TeamMember:
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise LookupError("user is not a member of this team")
    return member


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


async def _member_out(db: AsyncSession, member: TeamMember) -> TeamMemberOut:
    user = await db.get(User, member.user_id)
    return TeamMemberOut(
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        joined_at=member.joined_at,
    )


async def create_team(
    db: AsyncSession,
    ctx: AuthContext,
    name: str,
    member_ids: list[uuid.UUID],
) -> TeamOut:
    seen: set[uuid.UUID] = set()
    for user_id in member_ids:
        if user_id in seen:
            raise ValueError("duplicate member in request")
        seen.add(user_id)
        await _require_org_membership(db, ctx.org_id, user_id)

    team = Team(org_id=ctx.org_id, name=name)
    db.add(team)
    await db.flush()

    for order, user_id in enumerate(member_ids):
        db.add(TeamMember(team_id=team.id, user_id=user_id))

    await _log_activity(
        db,
        ctx.org_id,
        ctx.user_id,
        "team.created",
        "team",
        team.id,
        {"name": name, "member_ids": [str(m) for m in member_ids]},
    )
    await db.commit()
    await db.refresh(team)
    member_count = len(member_ids)
    return TeamOut(
        id=team.id,
        org_id=team.org_id,
        name=team.name,
        member_count=member_count,
        created_at=team.created_at,
    )


async def list_teams(db: AsyncSession, ctx: AuthContext) -> list[TeamOut]:
    result = await db.execute(
        select(Team, func.count(TeamMember.id))
        .outerjoin(TeamMember, TeamMember.team_id == Team.id)
        .where(Team.org_id == ctx.org_id)
        .group_by(Team.id)
        .order_by(Team.created_at.desc())
    )
    return [
        TeamOut(
            id=team.id,
            org_id=team.org_id,
            name=team.name,
            member_count=count,
            created_at=team.created_at,
        )
        for team, count in result.all()
    ]


async def get_team(
    db: AsyncSession, ctx: AuthContext, team_id: uuid.UUID
) -> TeamDetailOut:
    team = await _get_team_for_org(db, team_id, ctx.org_id)

    member_rows = await db.execute(
        select(TeamMember, User)
        .join(User, User.id == TeamMember.user_id)
        .where(TeamMember.team_id == team_id)
        .order_by(TeamMember.joined_at)
    )
    members = [
        TeamMemberOut(
            user_id=member.user_id,
            full_name=user.full_name,
            email=user.email,
            joined_at=member.joined_at,
        )
        for member, user in member_rows.all()
    ]

    team_user_ids = [m.user_id for m in members]
    if team_user_ids:
        project_rows = await db.execute(
            select(Project)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(
                Project.org_id == ctx.org_id,
                ProjectMember.user_id.in_(team_user_ids),
            )
            .distinct()
            .order_by(Project.created_at.desc())
        )
        projects = [
            TeamProjectOut(id=p.id, name=p.name, status=p.status)
            for p in project_rows.scalars().all()
        ]
    else:
        projects = []

    return TeamDetailOut(
        id=team.id,
        org_id=team.org_id,
        name=team.name,
        created_at=team.created_at,
        members=members,
        projects=projects,
    )


async def update_team(
    db: AsyncSession,
    ctx: AuthContext,
    team_id: uuid.UUID,
    name: str,
) -> TeamOut:
    team = await _get_team_for_org(db, team_id, ctx.org_id)
    old_name = team.name
    if name != team.name:
        team.name = name
        await _log_activity(
            db,
            ctx.org_id,
            ctx.user_id,
            "team.updated",
            "team",
            team.id,
            {"old_name": old_name, "new_name": name},
        )

    count_result = await db.execute(
        select(func.count(TeamMember.id)).where(TeamMember.team_id == team_id)
    )
    member_count = count_result.scalar_one()
    await db.commit()
    await db.refresh(team)
    return TeamOut(
        id=team.id,
        org_id=team.org_id,
        name=team.name,
        member_count=member_count,
        created_at=team.created_at,
    )


async def delete_team(
    db: AsyncSession, ctx: AuthContext, team_id: uuid.UUID
) -> None:
    team = await _get_team_for_org(db, team_id, ctx.org_id)
    await _log_activity(
        db,
        ctx.org_id,
        ctx.user_id,
        "team.deleted",
        "team",
        team.id,
        {"name": team.name},
    )
    await db.delete(team)
    await db.commit()


async def add_member(
    db: AsyncSession,
    ctx: AuthContext,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
) -> TeamMemberOut:
    await _get_team_for_org(db, team_id, ctx.org_id)
    await _require_org_membership(db, ctx.org_id, user_id)

    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
        )
    )
    if result.scalar_one_or_none() is not None:
        raise ValueError("user is already a member of this team")

    member = TeamMember(team_id=team_id, user_id=user_id)
    db.add(member)
    await db.flush()
    await _log_activity(
        db,
        ctx.org_id,
        ctx.user_id,
        "team.member.added",
        "team_member",
        member.id,
        {"team_id": str(team_id), "user_id": str(user_id)},
    )
    await db.commit()
    return await _member_out(db, member)


async def remove_member(
    db: AsyncSession,
    ctx: AuthContext,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    await _get_team_for_org(db, team_id, ctx.org_id)
    member = await _require_team_member_row(db, team_id, user_id)
    await _log_activity(
        db,
        ctx.org_id,
        ctx.user_id,
        "team.member.removed",
        "team_member",
        member.id,
        {"team_id": str(team_id), "user_id": str(user_id)},
    )
    await db.delete(member)
    await db.commit()