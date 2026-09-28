from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentActor, require_permission
from app.models.rbac import PermissionAction, PermissionDomain, Role
from app.schemas.rbac import RoleResponse

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("", response_model=list[RoleResponse])
def list_roles(
    actor: CurrentActor = Depends(require_permission(PermissionDomain.ROLE, PermissionAction.VIEW)),
    db: Session = Depends(get_db),
) -> list[Role]:
    # Visible roles = platform/template roles (organization_id IS NULL)
    # plus this org's own custom roles.
    return (
        db.query(Role)
        .filter((Role.organization_id == actor.organization_id) | (Role.organization_id.is_(None)))
        .order_by(Role.category, Role.name)
        .all()
    )
