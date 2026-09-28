import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentActor, get_current_actor, require_permission
from app.models.rbac import PermissionAction, PermissionDomain
from app.models.regulatory_structure import RegulatoryApplication, RegulatoryAuthority
from app.schemas.regulatory import (
    AuthorityResponse,
    RegulatoryApplicationCreateRequest,
    RegulatoryApplicationResponse,
)
from app.services import dossier_service
from app.services.dossier_service import DomainError

authorities_router = APIRouter(prefix="/authorities", tags=["authorities"])
applications_router = APIRouter(prefix="/applications", tags=["applications"])


@authorities_router.get("", response_model=list[AuthorityResponse])
def list_authorities(actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)) -> list[RegulatoryAuthority]:
    # Global reference data (spec §2) — any authenticated user in any
    # tenant can see the authority catalog, same treatment as Layer 1's
    # Permission catalog. No tenant filter applies; there is nothing
    # tenant-specific to filter.
    return db.query(RegulatoryAuthority).order_by(RegulatoryAuthority.short_name).all()


@applications_router.get("", response_model=list[RegulatoryApplicationResponse])
def list_applications(
    actor: CurrentActor = Depends(require_permission(PermissionDomain.APPLICATION, PermissionAction.VIEW)),
    db: Session = Depends(get_db),
    product_id: uuid.UUID | None = None,
) -> list[RegulatoryApplication]:
    query = db.query(RegulatoryApplication).filter(RegulatoryApplication.organization_id == actor.organization_id)
    if product_id is not None:
        query = query.filter(RegulatoryApplication.product_id == product_id)
    return query.order_by(RegulatoryApplication.created_at.desc()).all()


@applications_router.get("/{application_id}", response_model=RegulatoryApplicationResponse)
def get_application(
    application_id: uuid.UUID,
    actor: CurrentActor = Depends(require_permission(PermissionDomain.APPLICATION, PermissionAction.VIEW)),
    db: Session = Depends(get_db),
) -> RegulatoryApplication:
    application = (
        db.query(RegulatoryApplication)
        .filter(RegulatoryApplication.id == application_id, RegulatoryApplication.organization_id == actor.organization_id)
        .first()
    )
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return application


@applications_router.post("", response_model=RegulatoryApplicationResponse, status_code=status.HTTP_201_CREATED)
def create_application(
    payload: RegulatoryApplicationCreateRequest,
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> RegulatoryApplication:
    try:
        return dossier_service.create_regulatory_application(
            db, organization_id=actor.organization_id, actor_id=actor.user_id, **payload.model_dump()
        )
    except DomainError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
