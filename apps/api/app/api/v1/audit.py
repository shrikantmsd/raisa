from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentActor, require_permission
from app.models.audit import AuditEvent
from app.models.rbac import PermissionAction, PermissionDomain
from app.schemas.audit import AuditEventResponse

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditEventResponse])
def list_audit_events(
    actor: CurrentActor = Depends(require_permission(PermissionDomain.AUDIT, PermissionAction.VIEW)),
    db: Session = Depends(get_db),
    limit: int = 100,
) -> list[AuditEvent]:
    # Tenant-scoped by construction (spec §28): a Tenant Admin's
    # AUDIT_VIEW grant only ever authorizes this query, which is itself
    # hard-filtered to actor.organization_id. There is no code path in
    # Layer 1 that returns another tenant's audit rows through this
    # endpoint, regardless of role.
    return (
        db.query(AuditEvent)
        .filter(AuditEvent.organization_id == actor.organization_id)
        .order_by(AuditEvent.occurred_at.desc())
        .limit(limit)
        .all()
    )
