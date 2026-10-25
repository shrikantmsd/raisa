import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentActor, get_current_actor
from app.models.rbac import PermissionAction, PermissionDomain
from app.models.regulatory_structure import Product
from app.schemas.regulatory import ProductCreateRequest, ProductResponse
from app.services import dossier_service
from app.services.dossier_service import DomainError

router = APIRouter(prefix="/products", tags=["products"])

# Route shape for every read here: fetch the org-owned candidate(s), THEN
# apply dossier_service.filter_by_scope -- a single centralized-authorize()
# call per row, not a second scope-matching implementation. A user whose
# only role assignment is scoped (e.g. "Product ABC / India") sees only
# products bound to that scope or a descendant of it; an org-wide
# assignment sees everything, unchanged from before this hardening pass.


@router.get("", response_model=list[ProductResponse])
def list_products(actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)) -> list[Product]:
    candidates = db.query(Product).filter(Product.organization_id == actor.organization_id).order_by(Product.name).all()
    return dossier_service.filter_by_scope(db, candidates, user_id=actor.user_id, organization_id=actor.organization_id, domain=PermissionDomain.PRODUCT)


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: uuid.UUID, actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)) -> Product:
    product = db.query(Product).filter(Product.id == product_id, Product.organization_id == actor.organization_id).first()
    if product is None or not dossier_service.filter_by_scope(db, [product], user_id=actor.user_id, organization_id=actor.organization_id, domain=PermissionDomain.PRODUCT):
        # Same 404 whether the row doesn't exist, belongs to another
        # tenant, or is outside the caller's scope -- none of those cases
        # should be distinguishable from the outside.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreateRequest,
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> Product:
    # Identity only here -- dossier_service.create_product makes the real
    # CREATE-permission call (now scope-aware: payload.scope_id, if any,
    # is validated and checked there). Every write route in this Layer 2
    # module follows this shape on purpose: the route resolves WHO, the
    # service decides WHETHER, through the one authorize() engine (spec Sec20).
    try:
        return dossier_service.create_product(
            db, organization_id=actor.organization_id, actor_id=actor.user_id, **payload.model_dump()
        )
    except DomainError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
