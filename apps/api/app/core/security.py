"""
Security primitives: password hashing and JWT issuance/verification.

Layer 1 implements password-based auth only. MFA, OAuth/OIDC, and
SAML/SSO are extension points (spec §13) — `create_access_token`'s
`auth_context` field is where a future MFA/SSO assertion would be
recorded without changing the token shape.
"""
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    *,
    user_id: UUID,
    organization_id: UUID,
    session_id: UUID,
    auth_context: str = "password",
    expires_delta: timedelta | None = None,
) -> str:
    """Issue a signed JWT carrying the minimum claims the rest of the
    platform needs to authorize a request. Notably: the tenant
    (organization_id) is embedded in the *signed* token, never taken
    from a client-supplied header or query param (spec §53 — never
    trust client-provided tenant_id).
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "org": str(organization_id),
        "sid": str(session_id),
        "auth_context": auth_context,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, settings.AUTH_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Raises jwt.PyJWTError subclasses on invalid/expired tokens —
    callers (see app.core.deps) turn that into a 401.
    """
    return jwt.decode(token, settings.AUTH_SECRET, algorithms=[settings.JWT_ALGORITHM])
