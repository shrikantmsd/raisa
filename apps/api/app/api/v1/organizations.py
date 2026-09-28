from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentActor, get_current_actor
from app.models.organization import Organization
from app.schemas.organization import OrganizationResponse

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("/me", response_model=OrganizationResponse)
def get_my_organization(
    actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)
) -> Organization:
    # Tenant resolved from the token (actor.organization_id), never from
    # a path/query parameter — spec §53.
    org = db.get(Organization, actor.organization_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org
