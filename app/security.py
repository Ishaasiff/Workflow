import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings

JWT_SECRET_KEY = settings.secret_key
JWT_ALGORITHM = settings.algorithm
ACCESS_TOKEN_TTL = timedelta(minutes=settings.access_token_expire_minutes)
REFRESH_TOKEN_TTL = timedelta(days=settings.refresh_token_expire_days)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(
    user_id: uuid.UUID,
    org_id: uuid.UUID | None = None,
    role: str | None = None,
    is_super_admin: bool = False,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "jti": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + ACCESS_TOKEN_TTL,
        "is_super_admin": is_super_admin,
    }
    if org_id is not None:
        payload["org_id"] = str(org_id)
    if role is not None:
        payload["role"] = role
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(
    user_id: uuid.UUID,
    org_id: uuid.UUID | None = None,
    role: str | None = None,
    is_super_admin: bool = False,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + REFRESH_TOKEN_TTL,
        "is_super_admin": is_super_admin,
    }
    if org_id is not None:
        payload["org_id"] = str(org_id)
    if role is not None:
        payload["role"] = role
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_token_pair(
    user_id: uuid.UUID,
    org_id: uuid.UUID | None = None,
    role: str | None = None,
    is_super_admin: bool = False,
) -> dict:
    return {
        "access_token": create_access_token(user_id, org_id, role, is_super_admin),
        "refresh_token": create_refresh_token(user_id, org_id, role, is_super_admin),
    }

def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])