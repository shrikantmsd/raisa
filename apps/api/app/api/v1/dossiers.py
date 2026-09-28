import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentActor, get_current_actor, require_permission
from app.models.ctd import CTDModule, CTDSection
from app.models.dossier import Dossier, DossierStatus
from app.models.rbac import PermissionAction, PermissionDomain
from app.schemas.regulatory import (
    CTDModuleResponse,
    CTDSectionResponse,
    DocumentPlacementRequest,
    DocumentPlacementResponse,
    DossierCreateRequest,
    DossierResponse,
    DossierTransitionRequest,
)
from app.services import dossier_service
from app.services.dossier_service import DomainError

router = APIRouter(prefix="/dossiers", tags=["dossiers"])
ctd_router = APIRouter(prefix="/ctd", tags=["ctd"])


def _get_tenant_dossier(db: Session, dossier_id: uuid.UUID, organization_id: uuid.UUID) -> Dossier:
    # The one place a Dossier is looked up by id in this router — every
    # route below calls this rather than querying Dossier directly, so
    # the tenant filter can never accidentally be left off one route.
    dossier = db.query(Dossier).filter(Dossier.id == dossier_id, Dossier.organization_id == organization_id).first()
    if dossier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dossier not found")
    return dossier


@router.get("", response_model=list[DossierResponse])
def list_dossiers(
    actor: CurrentActor = Depends(require_permission(PermissionDomain.DOSSIER, PermissionAction.VIEW)),
    db: Session = Depends(get_db),
    product_id: uuid.UUID | None = None,
) -> list[Dossier]:
    query = db.query(Dossier).filter(Dossier.organization_id == actor.organization_id)
    if product_id is not None:
        query = query.filter(Dossier.product_id == product_id)
    return query.order_by(Dossier.created_at.desc()).all()


@router.get("/{dossier_id}", response_model=DossierResponse)
def get_dossier(
    dossier_id: uuid.UUID,
    actor: CurrentActor = Depends(require_permission(PermissionDomain.DOSSIER, PermissionAction.VIEW)),
    db: Session = Depends(get_db),
) -> Dossier:
    return _get_tenant_dossier(db, dossier_id, actor.organization_id)


@router.post("", response_model=DossierResponse, status_code=status.HTTP_201_CREATED)
def create_dossier(
    payload: DossierCreateRequest, actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)
) -> Dossier:
    try:
        return dossier_service.create_dossier(
            db, organization_id=actor.organization_id, actor_id=actor.user_id, **payload.model_dump()
        )
    except DomainError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post("/{dossier_id}/transition", response_model=DossierResponse)
def transition_dossier(
    dossier_id: uuid.UUID,
    payload: DossierTransitionRequest,
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> Dossier:
    # Tenant check happens here (via _get_tenant_dossier) BEFORE the
    # transition is even attempted — a Tenant A caller gets 404 for a
    # Tenant B dossier id, never a 403/409 that would confirm it exists.
    dossier = _get_tenant_dossier(db, dossier_id, actor.organization_id)
    try:
        new_status = DossierStatus(payload.new_status)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown dossier status")
    try:
        return dossier_service.transition_dossier_status(
            db,
            dossier=dossier,
            actor_id=actor.user_id,
            organization_id=actor.organization_id,
            new_status=new_status,
            reason=payload.reason,
        )
    except DomainError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post("/{dossier_id}/documents", response_model=DocumentPlacementResponse, status_code=status.HTTP_201_CREATED)
def place_document(
    dossier_id: uuid.UUID,
    payload: DocumentPlacementRequest,
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> DocumentPlacementResponse:
    _get_tenant_dossier(db, dossier_id, actor.organization_id)  # 404s before touching anything else
    try:
        return dossier_service.associate_document_to_ctd(
            db,
            organization_id=actor.organization_id,
            actor_id=actor.user_id,
            dossier_id=dossier_id,
            **payload.model_dump(),
        )
    except DomainError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


# --- CTD structure reference data (spec §11: registry, not hard-coded headings) ---


@ctd_router.get("/modules", response_model=list[CTDModuleResponse])
def list_ctd_modules(actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)) -> list[CTDModule]:
    # Global reference data — same reasoning as /authorities above.
    return db.query(CTDModule).order_by(CTDModule.display_order).all()


@ctd_router.get("/sections", response_model=list[CTDSectionResponse])
def list_ctd_sections(
    module_id: uuid.UUID | None = None,
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> list[CTDSection]:
    query = db.query(CTDSection).filter(CTDSection.active.is_(True))
    if module_id is not None:
        query = query.filter(CTDSection.module_id == module_id)
    return query.order_by(CTDSection.display_order).all()
