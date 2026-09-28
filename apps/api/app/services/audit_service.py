"""
Audit service (spec §27). Append-only by convention: this module
exposes `record()` and nothing that updates or deletes an AuditEvent.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.audit import AuditEvent, AuditEventType


def record(
    db: Session,
    *,
    organization_id: uuid.UUID,
    event_type: AuditEventType,
    object_type: str,
    user_id: uuid.UUID | None = None,
    object_id: uuid.UUID | None = None,
    previous_value: str | None = None,
    new_value: str | None = None,
    ip_address: str | None = None,
    session_context: str | None = None,
    reason: str | None = None,
    source: str = "api",
    commit: bool = True,
) -> AuditEvent:
    event = AuditEvent(
        organization_id=organization_id,
        user_id=user_id,
        event_type=event_type,
        object_type=object_type,
        object_id=object_id,
        previous_value=previous_value,
        new_value=new_value,
        occurred_at=datetime.now(timezone.utc),
        ip_address=ip_address,
        session_context=session_context,
        reason=reason,
        source=source,
    )
    db.add(event)
    if commit:
        db.commit()
        db.refresh(event)
    return event
