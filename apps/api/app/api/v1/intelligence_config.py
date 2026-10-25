import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentActor, get_current_actor
from app.models.intelligence import IntelligenceSource, IntelligenceTag
from app.schemas.intelligence import (
    SourceCreateRequest,
    SourceResponse,
    SourceUpdateRequest,
    TagCreateRequest,
    TagResponse,
    TenantPreferencesRequest,
)
from app.services import intelligence_admin_service
from app.services.intelligence_service import DomainError

sources_router = APIRouter(prefix="/intelligence/sources", tags=["intelligence-sources"])
tags_router = APIRouter(prefix="/intelligence/tags", tags=["intelligence-tags"])
config_router = APIRouter(prefix="/intelligence/preferences", tags=["intelligence-config"])

# Route shape for every write here: the route resolves WHO (from the
# token), the service decides WHETHER (permission + platform-org rule)
# and writes the audit row — same split as Layer 2.


@sources_router.get("", response_model=list[SourceResponse])
def list_sources(actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)) -> list[IntelligenceSource]:
    # Global reference data (spec §4): readable by any authenticated user.
    return db.query(IntelligenceSource).order_by(IntelligenceSource.name).all()


@sources_router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
def create_source(payload: SourceCreateRequest, actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)) -> IntelligenceSource:
    try:
        return intelligence_admin_service.create_source(db, organization_id=actor.organization_id, actor_id=actor.user_id, **payload.model_dump())
    except DomainError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@sources_router.patch("/{source_id}", response_model=SourceResponse)
def update_source(source_id: uuid.UUID, payload: SourceUpdateRequest, actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)) -> IntelligenceSource:
    source = db.get(IntelligenceSource, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    try:
        return intelligence_admin_service.update_source(
            db, source=source, organization_id=actor.organization_id, actor_id=actor.user_id, changes=payload.model_dump(exclude_unset=True)
        )
    except DomainError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@tags_router.get("", response_model=list[TagResponse])
def list_tags(actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)) -> list[IntelligenceTag]:
    return db.query(IntelligenceTag).filter(IntelligenceTag.active.is_(True)).order_by(IntelligenceTag.tag_type, IntelligenceTag.name).all()


@tags_router.post("", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
def create_tag(payload: TagCreateRequest, actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)) -> IntelligenceTag:
    try:
        return intelligence_admin_service.create_tag(
            db, organization_id=actor.organization_id, actor_id=actor.user_id, tag_type=payload.tag_type, name=payload.name
        )
    except DomainError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@config_router.get("", response_model=TenantPreferencesRequest)
def get_preferences(actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)) -> TenantPreferencesRequest:
    try:
        prefs = intelligence_admin_service.get_preferences(db, organization_id=actor.organization_id, actor_id=actor.user_id)
    except DomainError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return TenantPreferencesRequest(**prefs)


@config_router.put("", response_model=TenantPreferencesRequest)
def set_preferences(payload: TenantPreferencesRequest, actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)) -> TenantPreferencesRequest:
    # There is no organization_id parameter on this route at all: a
    # customer admin can only ever write their OWN organization's row.
    try:
        intelligence_admin_service.set_preferences(
            db, organization_id=actor.organization_id, actor_id=actor.user_id, preferences=payload.model_dump()
        )
    except DomainError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return payload
