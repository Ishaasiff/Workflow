import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OrgMembership, Organization, User, OrgRole
from app.models.admin import OrganizationAdminOut, UserAdminOut
from app.models.auth import LoginResponse, TokenPair, UserOut
from app.security import create_token_pair, verify_password


async def login_super_admin(db: AsyncSession, email: str, password: str) -> LoginResponse:
    user_result = await db.execute(select(User).where(User.email == email))
    user = user_result.scalar_one_or_none()
    if user is None or not verify_password(password, user.hashed_password):
        raise ValueError("invalid email or password")
    if not user.is_super_admin:
        raise PermissionError("only super admins can log in here")

    token = create_token_pair(user.id, None, None, is_super_admin=True)
    return LoginResponse(
        user=UserOut.model_validate(user),
        token=TokenPair(**token),
    )

async def create_organization(db: AsyncSession, name: str) -> OrganizationAdminOut:
    org = Organization(name=name)
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return OrganizationAdminOut(
        id=org.id,
        name=org.name,
        plan_tier=org.plan_tier,
        member_count=0,
        created_at=org.created_at,
    )


async def list_organizations(db: AsyncSession) -> list[OrganizationAdminOut]:
    org_result = await db.execute(select(Organization).order_by(Organization.created_at))
    orgs = org_result.scalars().all()
    result = []
    for org in orgs:
        count_result = await db.execute(
            select(func.count(OrgMembership.id)).where(OrgMembership.org_id == org.id)
        )
        member_count = count_result.scalar_one()
        result.append(
            OrganizationAdminOut(
                id=org.id,
                name=org.name,
                plan_tier=org.plan_tier,
                member_count=member_count,
                created_at=org.created_at,
            )
        )
    return result


async def list_users(db: AsyncSession) -> list[UserAdminOut]:
    user_result = await db.execute(select(User).order_by(User.created_at))
    users = user_result.scalars().all()
    result = []
    for user in users:
        membership_result = await db.execute(
            select(OrgMembership).where(OrgMembership.user_id == user.id)
        )
        memberships = membership_result.scalars().all()
        orgs = []
        for m in memberships:
            org = await db.get(Organization, m.org_id)
            if org:
                orgs.append({"id": str(org.id), "role": m.role.value})
        result.append(
            UserAdminOut(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                is_active=user.is_active,
                created_at=user.created_at,
                orgs=orgs,
            )
        )
    return result


async def suspend_user(db: AsyncSession, user_id: uuid.UUID) -> dict:
    user = await db.get(User, user_id)
    if user is None:
        raise LookupError("user not found")
    user.is_active = not user.is_active
    await db.commit()
    return {"user_id": str(user.id), "is_active": user.is_active}


async def update_membership_role(
    db: AsyncSession, membership_id: uuid.UUID, org_id: uuid.UUID, role: OrgRole
) -> dict:
    membership = await db.get(OrgMembership, membership_id)
    if membership is None:
        raise LookupError("membership not found")
    if membership.org_id != org_id:
        raise ValueError("membership does not belong to this org")
    membership.role = role
    await db.commit()
    await db.refresh(membership)
    return {"membership_id": str(membership.id), "role": membership.role.value}