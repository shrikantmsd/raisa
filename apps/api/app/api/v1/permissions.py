from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentActor, get_current_actor
from app.models.rbac import Permission
from app.schemas.rbac import PermissionResponse

router = APIRouter(prefix="/permissions", tags=["permissions"])


@router.get("", response_model=list[PermissionResponse])
def list_permissions(
    actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)
) -> list[Permission]:
    # Reference data (spec §18) — every authenticated user can see the
    # catalog of permissions that exist; that's not the same as holding
    # them. Any authenticated user in any organization, so no further
    # tenant filter applies here (Permission is a global reference table).
    return db.query(Permission).order_by(Permission.domain, Permission.action).all()
