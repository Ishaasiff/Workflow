import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.controllers.auth_controller import AuthContext
from app.models import OrgMembership, OrgRole, User
from app.models.admin import MemberOut
from app.security import hash_password


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


async def list_members(db: AsyncSession, org_id: uuid.UUID) -> list[MemberOut]:
    result = await db.execute(
        select(OrgMembership, User)
        .outerjoin(User, User.id == OrgMembership.user_id)
        .where(OrgMembership.org_id == org_id)
        .order_by(OrgMembership.joined_at)
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


async def add_member(
    db: AsyncSession,
    org_id: uuid.UUID,
    email: str,
    role: OrgRole,
    full_name: str | None,
    password: str | None,
) -> MemberOut:
    if role == OrgRole.super_admin:
        raise PermissionError("super_admin can only be granted by a super admin")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        if not full_name or not password:
            raise ValueError("full_name and password are required for a new user")
        user = User(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
        )
        db.add(user)
        await db.flush()

    existing_result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == user.id,
        )
    )
    if existing_result.scalar_one_or_none():
        raise ValueError("user is already a member of this org")

    membership = OrgMembership(org_id=org_id, user_id=user.id, role=role)
    db.add(membership)
    await db.commit()
    await db.refresh(membership)
    await db.refresh(user)

    return MemberOut(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        role=membership.role,
        joined_at=membership.joined_at,
    )


async def update_member_role(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, role: OrgRole
) -> MemberOut:
    if role == OrgRole.super_admin:
        raise PermissionError("super_admin can only be granted by a super admin")

    membership = await _require_membership(db, org_id, user_id)
    if membership.role == OrgRole.super_admin:
        raise PermissionError("cannot change a super admin")

    membership.role = role
    await db.commit()
    await db.refresh(membership)

    return await _member_out(db, membership)


async def suspend_member(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID
) -> MemberOut:
    membership = await _require_membership(db, org_id, user_id)
    if membership.role in (OrgRole.super_admin, OrgRole.org_admin):
        raise PermissionError("cannot suspend an admin")

    user = await db.get(User, user_id)
    user.is_active = not user.is_active
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

    await db.delete(membership)
    await db.commit()