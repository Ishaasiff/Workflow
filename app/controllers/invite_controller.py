import logging
import secrets
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.controllers.auth_controller import AuthContext
from app.models import Invite, OrgMembership, Organization, User
from app.models.auth import TokenPair
from app.models.org_memberships import OrgRole
from app.security import create_token_pair, hash_password
from app.services.email import send_invite_email


def _generate_token() -> str:
    return secrets.token_urlsafe(48)


async def create_invite(
    db: AsyncSession,
    ctx: AuthContext,
    email: str,
    role: OrgRole,
) -> Invite:
    if role == OrgRole.super_admin:
        raise PermissionError("cannot invite as super_admin")

    existing_member = await db.execute(
        select(OrgMembership)
        .join(User, User.id == OrgMembership.user_id)
        .where(OrgMembership.org_id == ctx.org_id, User.email == email)
    )
    if existing_member.scalar_one_or_none():
        raise ValueError("user is already a member of this org")

    existing_invite = await db.execute(
        select(Invite).where(
            Invite.org_id == ctx.org_id,
            Invite.email == email,
            Invite.accepted_at.is_(None),
            Invite.expires_at > datetime.now(timezone.utc),
        )
    )
    if existing_invite.scalar_one_or_none():
        raise ValueError("an active invite already exists for this email")

    token = _generate_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.invite_token_expire_days
    )

    invite = Invite(
        org_id=ctx.org_id,
        email=email,
        role=role,
        token=token,
        invited_by=ctx.user_id,
        expires_at=expires_at,
    )
    db.add(invite)
    await db.flush()

    org = await db.get(Organization, ctx.org_id)
    inviter = await db.get(User, ctx.user_id)

    try:
        await send_invite_email(
            to_email=email,
            org_name=org.name,
            inviter_name=inviter.full_name,
            invite_token=token,
        )
    except Exception:
        logger.exception(
            "failed to send invite email to %s; invite still created", email
)

    await db.commit()
    await db.refresh(invite)
    return invite


async def validate_invite_token(
    db: AsyncSession,
    token: str,
) -> dict:
    result = await db.execute(select(Invite).where(Invite.token == token))
    invite = result.scalar_one_or_none()
    if invite is None:
        raise LookupError("invalid invite token")

    if invite.accepted_at is not None:
        raise LookupError("this invite has already been accepted")

    if invite.expires_at < datetime.now(timezone.utc):
        raise LookupError("this invite has expired")

    org = await db.get(Organization, invite.org_id)
    inviter = await db.get(User, invite.invited_by)

    return {
        "org_name": org.name,
        "inviter_name": inviter.full_name if inviter else "Unknown",
        "email": invite.email,
        "role": invite.role,
        "expires_at": invite.expires_at,
    }


async def accept_invite(
    db: AsyncSession,
    token: str,
    full_name: str,
    password: str,
) -> dict:
    result = await db.execute(select(Invite).where(Invite.token == token))
    invite = result.scalar_one_or_none()
    if invite is None:
        raise LookupError("invalid invite token")

    if invite.accepted_at is not None:
        raise LookupError("this invite has already been accepted")

    if invite.expires_at < datetime.now(timezone.utc):
        raise LookupError("this invite has expired")

    user = User(
        email=invite.email,
        hashed_password=hash_password(password),
        full_name=full_name,
    )
    db.add(user)
    await db.flush()

    membership = OrgMembership(
        org_id=invite.org_id,
        user_id=user.id,
        role=invite.role,
    )
    db.add(membership)

    invite.accepted_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(user)
    await db.refresh(membership)

    token_pair = TokenPair(**create_token_pair(
        user.id, invite.org_id, invite.role.value
    ))
    return {"user": user, "token": token_pair}
