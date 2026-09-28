import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.audit import AuditEventType
from app.models.rbac import UserRoleAssignment
from app.models.user import User, UserStatus
from app.core.security import hash_password
from app.services import audit_service


def create_user(
    db: Session,
    *,
    organization_id: uuid.UUID,
    email: str,
    name: str,
    password: str,
    status: UserStatus = UserStatus.ACTIVE,
    created_by: uuid.UUID | None = None,
    department: str | None = None,
    job_title: str | None = None,
) -> User:
    user = User(
        organization_id=organization_id,
        email=email.lower(),
        password_hash=hash_password(password),
        name=name,
        status=status,
        department=department,
        job_title=job_title,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    audit_service.record(
        db,
        organization_id=organization_id,
        event_type=AuditEventType.USER_CREATED,
        object_type="User",
        object_id=user.id,
        user_id=created_by,
        new_value=f"email={user.email}, status={user.status.value}",
    )
    return user


def assign_role(
    db: Session,
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    role_id: uuid.UUID,
    scope_id: uuid.UUID | None = None,
    granted_by: uuid.UUID | None = None,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
) -> UserRoleAssignment:
    assignment = UserRoleAssignment(
        user_id=user_id,
        organization_id=organization_id,
        role_id=role_id,
        scope_id=scope_id,
        granted_at=datetime.now(timezone.utc),
        granted_by=granted_by,
        valid_from=valid_from,
        valid_until=valid_until,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    audit_service.record(
        db,
        organization_id=organization_id,
        event_type=AuditEventType.ROLE_ASSIGNED,
        object_type="User",
        object_id=user_id,
        user_id=granted_by,
        new_value=f"role_id={role_id}, scope_id={scope_id}",
    )
    return assignment
