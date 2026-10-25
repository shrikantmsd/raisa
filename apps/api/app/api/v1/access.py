from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentActor, get_current_actor
from app.models.rbac import PermissionAction, PermissionDomain
from app.schemas.rbac import AccessPreviewRequest, AccessPreviewResponse
from app.services.authorization_service import authorize

router = APIRouter(prefix="/access", tags=["access"])


@router.post("/preview", response_model=AccessPreviewResponse)
def preview_access(
    payload: AccessPreviewRequest,
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> AccessPreviewResponse:
    """Spec §44 — "clearly show ALLOWED / DENIED" for a given
    domain+action(+scope), evaluated for the *calling* user. Always
    checks the caller's own access; it does not let one user probe
    another's permissions.
    """
    try:
        domain = PermissionDomain(payload.domain)
        action = PermissionAction(payload.action)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown domain or action")

    decision = authorize(
        db=db,
        user_id=actor.user_id,
        organization_id=actor.organization_id,
        domain=domain,
        action=action,
        scope_id=payload.scope_id,
    )
    return AccessPreviewResponse(
        allowed=decision.allowed,
        reason=decision.reason,
        policy=decision.policy,
        role_id=decision.role_id,
        permission_code=decision.permission_code,
    )
