"""
Login / logout (spec §13-14). Every attempt — success or failure —
writes an AuthenticationEvent; this is what spec §66's demo scenario and
the mandatory security tests check for.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.auth_event import AuthenticationEvent, AuthEventType, UserSession
from app.models.organization import Organization
from app.models.user import User, UserStatus

settings = get_settings()


class LoginError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class LoginResult:
    access_token: str
    token_type: str
    user: User


def _log_auth_event(
    db: Session,
    *,
    event_type: AuthEventType,
    success: bool,
    organization_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    reason: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    db.add(
        AuthenticationEvent(
            user_id=user_id,
            organization_id=organization_id,
            event_type=event_type,
            occurred_at=datetime.now(timezone.utc),
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            reason=reason,
        )
    )
    db.commit()


def login(
    db: Session,
    *,
    organization_slug: str,
    email: str,
    password: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> LoginResult:
    organization = db.query(Organization).filter(Organization.slug == organization_slug).first()
    if organization is None:
        # No organization_id to attach the event to; still a
        # LOGIN_FAILED worth recording for security monitoring.
        _log_auth_event(
            db,
            event_type=AuthEventType.LOGIN_FAILED,
            success=False,
            organization_id=None,
            user_id=None,
            reason="Unknown organization",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        raise LoginError("Invalid credentials")

    user = (
        db.query(User)
        .filter(User.organization_id == organization.id, User.email == email.lower())
        .first()
    )

    if user is None or not verify_password(password, user.password_hash):
        _log_auth_event(
            db,
            event_type=AuthEventType.LOGIN_FAILED,
            success=False,
            organization_id=organization.id,
            user_id=user.id if user else None,
            reason="Invalid credentials",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        raise LoginError("Invalid credentials")

    if user.status != UserStatus.ACTIVE:
        _log_auth_event(
            db,
            event_type=AuthEventType.LOGIN_FAILED,
            success=False,
            organization_id=organization.id,
            user_id=user.id,
            reason=f"Account status is {user.status.value}",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        raise LoginError(f"Account is {user.status.value.lower()}")

    session = UserSession(
        user_id=user.id,
        organization_id=organization.id,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(session)

    user.last_login_at = datetime.now(timezone.utc)

    _log_auth_event(
        db,
        event_type=AuthEventType.LOGIN_SUCCESS,
        success=True,
        organization_id=organization.id,
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.commit()
    db.refresh(session)
    db.refresh(user)

    token = create_access_token(user_id=user.id, organization_id=organization.id, session_id=session.id)
    return LoginResult(access_token=token, token_type="bearer", user=user)


def logout(db: Session, *, session_id: uuid.UUID, user_id: uuid.UUID, organization_id: uuid.UUID) -> None:
    session = db.get(UserSession, session_id)
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
        _log_auth_event(
            db,
            event_type=AuthEventType.LOGOUT,
            success=True,
            organization_id=organization_id,
            user_id=user_id,
        )
        db.commit()
