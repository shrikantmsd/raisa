"""
Regulatory Event recording (Layer 2 spec §16). Deliberately thin and
always called alongside `audit_service.record` — a RegulatoryEvent is
the human-readable timeline entry ("Dossier moved to Under Review"); the
AuditEvent is the compliance record (who/what/previous/new). Neither
replaces the other; see docs/LAYER_2_DOSSIER_CTD.md.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.regulatory_activity import RegulatoryEvent, RegulatoryEventType


def record(
    db: Session,
    *,
    organization_id: uuid.UUID,
    event_type: RegulatoryEventType,
    dossier_id: uuid.UUID | None = None,
    regulatory_activity_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    intelligence_item_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    description: str | None = None,
    commit: bool = True,
) -> RegulatoryEvent:
    event = RegulatoryEvent(
        organization_id=organization_id,
        event_type=event_type,
        dossier_id=dossier_id,
        regulatory_activity_id=regulatory_activity_id,
        document_id=document_id,
        intelligence_item_id=intelligence_item_id,
        actor_user_id=actor_user_id,
        occurred_at=datetime.now(timezone.utc),
        description=description,
    )
    db.add(event)
    if commit:
        db.commit()
        db.refresh(event)
    return event
