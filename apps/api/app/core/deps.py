"""
Request-scoped dependencies.

`get_current_actor` is the ONLY place tenant identity is derived from a
request. It comes out of the signed JWT, never from a header, query
param, or request body — this is what makes "never trust client-
provided tenant_id" (spec §53) actually true rather than aspirational.
"""
import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.rbac import PermissionAction, PermissionDomain
from app.models.user import User, UserStatus

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


@dataclass(frozen=True)
class CurrentActor:
    """Everything downstream code needs about "who is making this
    request" — deliberately a plain object, not the ORM User row, so
    it's obvious this is the trusted, token-derived identity."""

    user_id: uuid.UUID
    organization_id: uuid.UUID
    session_id: uuid.UUID


def get_current_actor(token: str | None = Depends(oauth2_scheme)) -> CurrentActor:
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    return CurrentActor(
        user_id=uuid.UUID(payload["sub"]),
        organization_id=uuid.UUID(payload["org"]),
        session_id=uuid.UUID(payload["sid"]),
    )


def get_current_user(
    actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)
) -> User:
    """Loads the User row scoped to the token's own organization_id —
    a user row from another tenant can never be returned here even if
    somehow the same primary key existed (it can't; UUIDs), belt-and-
    braces against tenant-crossing bugs."""
    user = (
        db.query(User)
        .filter(User.id == actor.user_id, User.organization_id == actor.organization_id)
        .first()
    )
    if user is None or user.status not in (UserStatus.ACTIVE, UserStatus.INVITED):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is not active")
    return user


def require_permission(domain: PermissionDomain, action: PermissionAction):
    """Dependency factory: `Depends(require_permission(DOCUMENT, APPROVE))`.
    Delegates the actual decision to the one central authorization
    service (spec §23) rather than re-implementing role lookups per
    route.
    """

    def _check(
        actor: CurrentActor = Depends(get_current_actor),
        db: Session = Depends(get_db),
    ) -> CurrentActor:
        from app.services.authorization_service import authorize  # local import avoids a cycle

        decision = authorize(
            db=db,
            user_id=actor.user_id,
            organization_id=actor.organization_id,
            domain=domain,
            action=action,
            scope_id=None,
            resource_state=None,
        )
        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"reason": decision.reason, "policy": decision.policy},
            )
        return actor

    return _check
