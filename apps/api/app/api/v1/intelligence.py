import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentActor, get_current_actor
from app.models.intelligence import IntelligenceItemTag, IntelligenceScope, RegulatoryIntelligenceItem
from app.models.rbac import PermissionAction, PermissionDomain
from app.schemas.intelligence import (
    DistributionRequest,
    IntelligenceItemCreateRequest,
    IntelligenceItemResponse,
    IntelligenceItemUpdateRequest,
    IntelligenceTransitionRequest,
    ObjectLinkRequest,
    SuggestedOrganization,
)
from app.services import intelligence_service
from app.services.authorization_service import authorize
from app.services.intelligence_service import DomainError

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


def _can_administer(db: Session, actor: CurrentActor) -> bool:
    return authorize(
        db=db, user_id=actor.user_id, organization_id=actor.organization_id,
        domain=PermissionDomain.INTELLIGENCE, action=PermissionAction.ADMINISTER,
    ).allowed


def _get_visible_item(db: Session, item_id: uuid.UUID, actor: CurrentActor) -> RegulatoryIntelligenceItem:
    item = (
        intelligence_service.visible_intelligence_query(db, actor_organization_id=actor.organization_id)
        .filter(RegulatoryIntelligenceItem.id == item_id)
        .first()
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intelligence item not found")
    # PRIVATE narrowing (spec §5): visible to the creator or an admin,
    # even though it passed the org-level visibility_query above.
    if (
        item.scope == IntelligenceScope.PRIVATE
        and item.organization_id == actor.organization_id
        and item.created_by != actor.user_id
        and not _can_administer(db, actor)
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intelligence item not found")
    return item


@router.get("", response_model=list[IntelligenceItemResponse])
def list_intelligence(
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
    intelligence_type: str | None = None,
    authority_id: uuid.UUID | None = None,
    country_region: str | None = None,
    impact_level: str | None = None,
    status_filter: str | None = None,
    therapeutic_area: str | None = None,
    tag_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[RegulatoryIntelligenceItem]:
    query = intelligence_service.visible_intelligence_query(db, actor_organization_id=actor.organization_id)

    can_administer = _can_administer(db, actor)
    if not can_administer:
        # Hide other people's PRIVATE items from the list entirely
        # (spec §24 test 4) — an item that IS visible per the org-level
        # rule but is someone else's PRIVATE note doesn't belong in a
        # general list view.
        query = query.filter(
            (RegulatoryIntelligenceItem.scope != IntelligenceScope.PRIVATE)
            | (RegulatoryIntelligenceItem.created_by == actor.user_id)
        )

    if intelligence_type:
        query = query.filter(RegulatoryIntelligenceItem.intelligence_type == intelligence_type)
    if authority_id:
        query = query.filter(RegulatoryIntelligenceItem.authority_id == authority_id)
    if country_region:
        query = query.filter(RegulatoryIntelligenceItem.country_region == country_region)
    if impact_level:
        query = query.filter(RegulatoryIntelligenceItem.impact_level == impact_level)
    if status_filter:
        query = query.filter(RegulatoryIntelligenceItem.status == status_filter)
    if therapeutic_area:
        query = query.filter(RegulatoryIntelligenceItem.therapeutic_area == therapeutic_area)
    if tag_id:
        query = query.join(IntelligenceItemTag, IntelligenceItemTag.intelligence_item_id == RegulatoryIntelligenceItem.id).filter(
            IntelligenceItemTag.tag_id == tag_id
        )

    return query.order_by(RegulatoryIntelligenceItem.publication_date.desc().nullslast()).limit(limit).all()


@router.get("/{item_id}", response_model=IntelligenceItemResponse)
def get_intelligence(item_id: uuid.UUID, actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)) -> RegulatoryIntelligenceItem:
    return _get_visible_item(db, item_id, actor)


@router.post("", response_model=IntelligenceItemResponse, status_code=status.HTTP_201_CREATED)
def create_intelligence(payload: IntelligenceItemCreateRequest, actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)) -> RegulatoryIntelligenceItem:
    try:
        return intelligence_service.create_intelligence_item(db, organization_id=actor.organization_id, actor_id=actor.user_id, **payload.model_dump())
    except DomainError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.patch("/{item_id}", response_model=IntelligenceItemResponse)
def update_intelligence(item_id: uuid.UUID, payload: IntelligenceItemUpdateRequest, actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)) -> RegulatoryIntelligenceItem:
    item = _get_visible_item(db, item_id, actor)
    try:
        return intelligence_service.update_intelligence_item(
            db, item=item, actor_id=actor.user_id, organization_id=actor.organization_id, changes=payload.model_dump(exclude_unset=True),
        )
    except DomainError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/{item_id}/distribution-suggestions", response_model=list[SuggestedOrganization])
def distribution_suggestions(item_id: uuid.UUID, actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)):
    item = _get_visible_item(db, item_id, actor)
    try:
        return intelligence_service.suggest_distribution_targets(db, item=item, actor_id=actor.user_id, organization_id=actor.organization_id)
    except DomainError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post("/{item_id}/transition", response_model=IntelligenceItemResponse)
def transition_intelligence(item_id: uuid.UUID, payload: IntelligenceTransitionRequest, actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)) -> RegulatoryIntelligenceItem:
    item = _get_visible_item(db, item_id, actor)
    try:
        return intelligence_service.transition_intelligence_status(
            db, item=item, actor_id=actor.user_id, organization_id=actor.organization_id, new_status=payload.new_status, reason=payload.reason,
        )
    except DomainError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post("/{item_id}/distribute", status_code=status.HTTP_201_CREATED)
def distribute_intelligence(item_id: uuid.UUID, payload: DistributionRequest, actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)) -> dict:
    item = _get_visible_item(db, item_id, actor)
    try:
        intelligence_service.distribute_intelligence_item(
            db, item=item, target_organization_id=payload.target_organization_id, actor_id=actor.user_id, organization_id=actor.organization_id,
        )
    except DomainError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return {"status": "distributed"}


@router.post("/{item_id}/tags/{tag_id}", status_code=status.HTTP_201_CREATED)
def tag_intelligence(item_id: uuid.UUID, tag_id: uuid.UUID, actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)) -> dict:
    item = _get_visible_item(db, item_id, actor)
    try:
        intelligence_service.tag_intelligence_item(db, item=item, tag_id=tag_id, actor_id=actor.user_id, organization_id=actor.organization_id)
    except DomainError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return {"status": "tagged"}


@router.post("/{item_id}/links", status_code=status.HTTP_201_CREATED)
def link_intelligence(item_id: uuid.UUID, payload: ObjectLinkRequest, actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)) -> dict:
    item = _get_visible_item(db, item_id, actor)
    try:
        intelligence_service.link_intelligence_object(
            db, item=item, linked_object_type=payload.linked_object_type, linked_object_id=payload.linked_object_id,
            actor_id=actor.user_id, organization_id=actor.organization_id,
        )
    except DomainError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return {"status": "linked"}
