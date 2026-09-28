import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentActor, get_current_actor, require_permission
from app.models.rbac import PermissionAction, PermissionDomain
from app.models.regulatory_activity import RegulatoryActivity, RegulatoryEvent
from app.schemas.regulatory import (
    RegulatoryActivityCreateRequest,
    RegulatoryActivityResponse,
    RegulatoryEventResponse,
)
from app.services import dossier_service
from app.services.dossier_service import DomainError

router = APIRouter(prefix="/activities", tags=["activities"])


@router.get("", response_model=list[RegulatoryActivityResponse])
def list_activities(
    actor: CurrentActor = Depends(require_permission(PermissionDomain.ACTIVITY, PermissionAction.VIEW)),
    db: Session = Depends(get_db),
    dossier_id: uuid.UUID | None = None,
) -> list[RegulatoryActivity]:
    query = db.query(RegulatoryActivity).filter(RegulatoryActivity.organization_id == actor.organization_id)
    if dossier_id is not None:
        query = query.filter(RegulatoryActivity.dossier_id == dossier_id)
    return query.order_by(RegulatoryActivity.created_at.desc()).all()


@router.post("", response_model=RegulatoryActivityResponse, status_code=status.HTTP_201_CREATED)
def create_activity(
    payload: RegulatoryActivityCreateRequest,
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> RegulatoryActivity:
    try:
        return dossier_service.create_regulatory_activity(
            db, organization_id=actor.organization_id, actor_id=actor.user_id, **payload.model_dump()
        )
    except DomainError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/events", response_model=list[RegulatoryEventResponse])
def list_events(
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
    dossier_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[RegulatoryEvent]:
    # Tenant-scoped the same way Layer 1's /audit is (spec §26/§28
    # principle applied here too) — read access to the *business*
    # timeline is lighter than AUDIT_VIEW on purpose (any authenticated
    # tenant member, not just an auditor role), but never cross-tenant.
    query = db.query(RegulatoryEvent).filter(RegulatoryEvent.organization_id == actor.organization_id)
    if dossier_id is not None:
        query = query.filter(RegulatoryEvent.dossier_id == dossier_id)
    return query.order_by(RegulatoryEvent.occurred_at.desc()).limit(limit).all()
