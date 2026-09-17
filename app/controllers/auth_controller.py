import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    OrgMembership,
    OrgRole,
    Organization,
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


@dataclass
class AuthContext:
    user_id: uuid.UUID
    org_id: uuid.UUID | None = None
    org_role: OrgRole | None = None
    is_super_admin: bool = False


ORG_ADMIN_ROLES = (OrgRole.org_admin,)


# ---- Auth business logic ---------------------------------------------------

async def signup(
    db: AsyncSession, org_name: str, admin_email: str, admin_password: str, full_name: str
) -> dict:
    result = await db.execute(select(User).where(User.email == admin_email))
    if result.scalar_one_or_none():
        raise ValueError("a user with this email already exists")

    org = Organization(name=org_name)
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


async def login_user(db: AsyncSession, email: str, password: str) -> dict:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        raise ValueError("invalid email or password")

    membership_result = await db.execute(
        select(OrgMembership).where(OrgMembership.user_id == user.id)
    )
    membership = membership_result.scalars().first()

    org_id = membership.org_id if membership else None
    role = membership.role.value if membership else None

    token = TokenPair(**create_token_pair(user.id, org_id, role, user.is_super_admin))
    return {"user": UserOut.model_validate(user), "token": token}


def refresh(refresh_token: str) -> TokenPair:
    ctx = decode_refresh_token(refresh_token)
    role = ctx.org_role.value if ctx.org_role else None
    return TokenPair(**create_token_pair(ctx.user_id, ctx.org_id, role, ctx.is_super_admin))


async def get_me(db: AsyncSession, ctx: AuthContext) -> UserOut:
    user = await db.get(User, ctx.user_id)
    if user is None:
        raise LookupError("user not found")
    return UserOut.model_validate(user)


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