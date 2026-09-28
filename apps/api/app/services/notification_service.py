"""
Notification foundation integration (spec §16 — "prepare the
notification model and service for future web/mobile delivery," not a
full push infrastructure). This is the first thing in the codebase to
actually write a `Notification` row; Layer 1 only defined the table.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.platform import Notification
from app.models.rbac import UserRoleAssignment, Role
from app.models.user import User, UserStatus


def notify_user(db: Session, *, organization_id: uuid.UUID, user_id: uuid.UUID, notification_type: str, title: str, message: str, action_url: str | None = None) -> Notification:
    notification = Notification(
        organization_id=organization_id, user_id=user_id, type=notification_type,
        title=title, message=message, created_at=datetime.now(timezone.utc), action_url=action_url,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


def notify_organization_admins(db: Session, *, organization_id: uuid.UUID, notification_type: str, title: str, message: str) -> list[Notification]:
    """Deliberately narrow default audience (Tenant Administrators) —
    Layer 3 foundation doesn't yet have a per-user subscription/interest
    model to target more precisely (that's the Configuration-based
    intelligence preferences, read but not fanned-out-to individual
    users in this layer)."""
    admin_user_ids = (
        db.query(UserRoleAssignment.user_id)
        .join(Role, Role.id == UserRoleAssignment.role_id)
        .filter(UserRoleAssignment.organization_id == organization_id, Role.code == "TENANT_ADMINISTRATOR")
        .distinct()
        .all()
    )
    created = []
    for (user_id,) in admin_user_ids:
        user = db.get(User, user_id)
        if user and user.status == UserStatus.ACTIVE:
            created.append(
                notify_user(db, organization_id=organization_id, user_id=user_id, notification_type=notification_type, title=title, message=message)
            )
    return created
