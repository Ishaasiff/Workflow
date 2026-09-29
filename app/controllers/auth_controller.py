import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.email import send_password_reset_email
from app.database import get_db
from app.models import (
    OrgMembership,
    OrgRole,
    Organization,
    PasswordResetToken,
    PlanTier,
    ProjectMember,
    ProjectRole,
    TeamMember,
    User,
)
from app.models.auth import LoginResponse, OrganizationOut, TokenPair, UserOut
from app.security import (
    create_token_pair,
    decode_token,
    hash_password,
    verify_password,
)

security = HTTPBearer(auto_error=False)

logger = logging.getLogger(__name__)


@dataclass
class AuthContext:
    user_id: uuid.UUID
    org_id: uuid.UUID | None = None
    org_role: OrgRole | None = None
    is_super_admin: bool = False


ORG_ADMIN_ROLES = (OrgRole.org_admin,)


# ---- Auth business logic ---------------------------------------------------

class OrgSelectionRequired(Exception):
    """Raised when a user belongs to multiple orgs and no org_id was chosen."""

    def __init__(self, organizations: list[OrganizationOut]):
        self.organizations = organizations
        super().__init__("organization selection required")


async def signup(
    db: AsyncSession, org_name: str, admin_email: str, admin_password: str, full_name: str
) -> dict:
    result = await db.execute(select(User).where(User.email == admin_email))
    if result.scalar_one_or_none():
        raise ValueError("a user with this email already exists")

    org = Organization(name=org_name, plan_tier=PlanTier.free)
    db.add(org)
    await db.flush()

    user = User(
        email=admin_email,
        hashed_password=hash_password(admin_password),
        full_name=full_name,
    )
    db.add(user)
    await db.flush()

    membership = OrgMembership(
        org_id=org.id, user_id=user.id, role=OrgRole.org_admin
    )
    db.add(membership)

    await db.commit()
    await db.refresh(org)
    await db.refresh(user)

    token = TokenPair(**create_token_pair(user.id, org.id, OrgRole.org_admin.value))
    return {
        "user": UserOut.model_validate(user),
        "org": OrganizationOut.model_validate(org),
        "token": token,
    }


async def login_user(
    db: AsyncSession,
    email: str,
    password: str,
    org_id: uuid.UUID | None = None,
) -> dict:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        raise ValueError("invalid email or password")

    membership_result = await db.execute(
        select(OrgMembership, Organization)
        .join(Organization, Organization.id == OrgMembership.org_id)
        .where(OrgMembership.user_id == user.id)
        .order_by(OrgMembership.joined_at)
    )
    rows = membership_result.all()
    available_orgs = [OrganizationOut.model_validate(org) for _, org in rows]

    membership: OrgMembership | None
    if org_id is not None:
        org_uuid = org_id if isinstance(org_id, uuid.UUID) else uuid.UUID(str(org_id))
        membership = next((m for m, _ in rows if m.org_id == org_uuid), None)
        if membership is None:
            raise PermissionError("you are not a member of the requested organization")
    elif len(rows) == 1:
        membership = rows[0][0]
    elif len(rows) > 1:
        raise OrgSelectionRequired(available_orgs)
    else:
        membership = None

    selected_org_id = membership.org_id if membership else None
    role = membership.role.value if membership else None

    token = TokenPair(
        **create_token_pair(user.id, selected_org_id, role, user.is_super_admin)
    )
    return {
        "user": UserOut.model_validate(user),
        "token": token,
        "organizations": available_orgs,
    }


async def refresh(
    refresh_token: str,
    db: AsyncSession,
    org_id: uuid.UUID | None = None,
) -> TokenPair:
    ctx = decode_refresh_token(refresh_token)

    target_org_id = ctx.org_id
    role = ctx.org_role.value if ctx.org_role else None

    if org_id is not None:
        # Switching (or confirming) org context: always resolve the role from
        # the database so stale roles are never carried into new tokens.
        new_role = await get_org_role(db, ctx.user_id, org_id)
        if new_role is None:
            raise PermissionError("you are not a member of the requested organization")
        target_org_id = org_id
        role = new_role.value

    return TokenPair(
        **create_token_pair(ctx.user_id, target_org_id, role, ctx.is_super_admin)
    )


async def get_me(db: AsyncSession, ctx: AuthContext) -> UserOut:
    user = await db.get(User, ctx.user_id)
    if user is None:
        raise LookupError("user not found")
    return UserOut.model_validate(user)


async def request_password_reset(db: AsyncSession, email: str) -> None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        return

    token = secrets.token_urlsafe(48)
    reset = PasswordResetToken(
        user_id=user.id,
        token=token,
        expires_at=datetime.now(timezone.utc)
        + timedelta(minutes=settings.reset_token_expire_minutes),
    )
    db.add(reset)
    await db.flush()

    try:
        await send_password_reset_email(to_email=email, reset_token=token)
    except Exception:
        logger.exception("failed to send password reset email to %s", email)

    await db.commit()


async def validate_reset_token(db: AsyncSession, token: str) -> dict:
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token == token)
    )
    reset = result.scalar_one_or_none()
    if reset is None:
        raise LookupError("invalid reset token")

    if reset.used_at is not None:
        raise LookupError("this reset link has already been used")

    if reset.expires_at < datetime.now(timezone.utc):
        raise LookupError("this reset link has expired")

    user = await db.get(User, reset.user_id)
    if user is None:
        raise LookupError("user not found")

    return {"email": user.email}


async def reset_password(db: AsyncSession, token: str, new_password: str) -> None:
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token == token)
    )
    reset = result.scalar_one_or_none()
    if reset is None:
        raise LookupError("invalid reset token")

    if reset.used_at is not None:
        raise LookupError("this reset link has already been used")

    if reset.expires_at < datetime.now(timezone.utc):
        raise LookupError("this reset link has expired")

    user = await db.get(User, reset.user_id)
    if user is None:
        raise LookupError("user not found")

    user.hashed_password = hash_password(new_password)
    reset.used_at = datetime.now(timezone.utc)
    await db.commit()


# ---- Token / auth dependencies ---------------------------------------------

def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
) -> AuthContext:
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(creds.credentials)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthContext(
        user_id=uuid.UUID(user_id),
        org_id=uuid.UUID(payload["org_id"]) if payload.get("org_id") else None,
        org_role=OrgRole(payload["role"]) if payload.get("role") else None,
        is_super_admin=bool(payload.get("is_super_admin", False)),
    )


def require_org_member(ctx: AuthContext = Depends(get_current_user)) -> AuthContext:
    if ctx.org_id is None or ctx.org_role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="not a member of any organization",
        )
    return ctx


def require_org_admin(ctx: AuthContext = Depends(require_org_member)) -> AuthContext:
    if ctx.org_role not in ORG_ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="requires org admin permission",
        )
    return ctx


def require_super_admin(ctx: AuthContext = Depends(get_current_user)) -> AuthContext:
    if not ctx.is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="requires super admin permission",
        )
    return ctx


async def get_project_role(
    db: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> ProjectRole | None:
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.user_id == user_id,
            ProjectMember.project_id == project_id,
        )
    )
    member = result.scalar_one_or_none()
    return member.role if member else None


async def get_org_role(
    db: AsyncSession, user_id: uuid.UUID, org_id: uuid.UUID
) -> OrgRole | None:
    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.user_id == user_id,
            OrgMembership.org_id == org_id,
        )
    )
    membership = result.scalar_one_or_none()
    return membership.role if membership else None


async def is_project_manager(
    ctx: AuthContext, db: AsyncSession, project_id: uuid.UUID
) -> bool:
    if ctx.org_role in ORG_ADMIN_ROLES:
        return True
    return await get_project_role(db, ctx.user_id, project_id) == ProjectRole.project_manager


async def is_team_member(
    db: AsyncSession, user_id: uuid.UUID, team_id: uuid.UUID
) -> bool:
    result = await db.execute(
        select(TeamMember.id).where(
            TeamMember.user_id == user_id,
            TeamMember.team_id == team_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def assert_project_access(
    ctx: AuthContext,
    db: AsyncSession,
    project_id: uuid.UUID,
    allowed_roles: set[ProjectRole] | None = None,
) -> None:
    if ctx.org_role in ORG_ADMIN_ROLES:
        return

    role = await get_project_role(db, ctx.user_id, project_id)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="not a member of this project",
        )
    if allowed_roles is not None and role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"requires project role: {', '.join(r.value for r in allowed_roles)}",
        )


async def assert_team_access(ctx: AuthContext, db: AsyncSession, team_id: uuid.UUID) -> None:
    if ctx.org_role in ORG_ADMIN_ROLES:
        return
    if not await is_team_member(db, ctx.user_id, team_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="not a member of this team",
        )


def decode_refresh_token(token: str) -> AuthContext:
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not a refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return AuthContext(
        user_id=uuid.UUID(payload["sub"]),
        org_id=uuid.UUID(payload["org_id"]) if payload.get("org_id") else None,
        org_role=OrgRole(payload["role"]) if payload.get("role") else None,
        is_super_admin=bool(payload.get("is_super_admin", False)),
    )