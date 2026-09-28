"""
The one centralized authorization service (spec §23).

Every other layer — API routes (via core.deps.require_permission),
service-layer code, and eventually background jobs / the future AI
assistant — calls `authorize()` rather than querying roles/permissions
itself. That is the whole point of centralizing it: one place to audit,
one place to fix a bug in, one place a future RAG/agent integration has
to respect instead of bypassing.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.rbac import (
    PermissionAction,
    PermissionDomain,
    Permission,
    Role,
    RolePermission,
    UserRoleAssignment,
    Scope,
    SoDPolicy,
    ResourceState,
)
from app.models.user import User, UserStatus

# Actions that mutate a resource. VIEW/EXPORT are read-type and are not
# blocked by resource state (spec §21 example: EDIT on an APPROVED
# record must not be silently allowed; viewing an APPROVED record is
# fine and, in fact, the normal case).
_MUTATING_ACTIONS = {
    PermissionAction.CREATE,
    PermissionAction.EDIT,
    PermissionAction.DELETE,
    PermissionAction.REVIEW,
    PermissionAction.APPROVE,
    PermissionAction.PUBLISH,
}

# A resource in one of these states rejects further mutation by
# default; only an explicit future workflow transition (not Layer 1)
# moves it out of this list.
_TERMINAL_STATES = {ResourceState.APPROVED, ResourceState.EFFECTIVE, ResourceState.SUPERSEDED, ResourceState.ARCHIVED}


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    policy: str | None = None
    scope_id: uuid.UUID | None = None
    role_id: uuid.UUID | None = None
    permission_code: str | None = None


def _scope_ancestor_ids(db: Session, scope_id: uuid.UUID | None) -> set[uuid.UUID]:
    """Walk `parent_id` up from `scope_id` to the root, so a role granted
    at "Product ABC" also authorizes actions scoped to "Product ABC /
    India" underneath it (spec §19 hierarchy)."""
    if scope_id is None:
        return set()
    ids: set[uuid.UUID] = set()
    current = db.get(Scope, scope_id)
    while current is not None:
        ids.add(current.id)
        current = db.get(Scope, current.parent_id) if current.parent_id else None
    return ids


def authorize(
    *,
    db: Session,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    domain: PermissionDomain,
    action: PermissionAction,
    scope_id: uuid.UUID | None = None,
    resource_state: ResourceState | None = None,
    resource_owner_id: uuid.UUID | None = None,
) -> AuthorizationDecision:
    """
    authorize(user, action, resource, scope, resource_state) -> ALLOW | DENY

    Deny-by-default: any unmatched branch below falls through to the
    final `return AuthorizationDecision(allowed=False, ...)`.
    """
    now = datetime.now(timezone.utc)

    user = db.get(User, user_id)
    if user is None or user.organization_id != organization_id:
        # Tenant boundary check lives here too, not just in get_current_user —
        # authorize() must be safe to call directly from future background
        # jobs that don't go through the HTTP dependency chain at all.
        return AuthorizationDecision(allowed=False, reason="User not found in organization", policy="TENANT_ISOLATION")

    if user.status not in (UserStatus.ACTIVE,):
        return AuthorizationDecision(allowed=False, reason=f"User status is {user.status.value}", policy="USER_STATUS")

    # External consultant / time-bounded access (spec §22).
    if user.valid_from and now < user.valid_from:
        return AuthorizationDecision(allowed=False, reason="Access not yet valid", policy="TIME_BOUNDED_ACCESS")
    if user.valid_until and now > user.valid_until:
        return AuthorizationDecision(allowed=False, reason="Access has expired", policy="TIME_BOUNDED_ACCESS")

    permission = (
        db.query(Permission).filter(Permission.domain == domain, Permission.action == action).first()
    )
    if permission is None:
        return AuthorizationDecision(allowed=False, reason="Unknown permission", policy="UNKNOWN_PERMISSION")

    allowed_scope_ids = _scope_ancestor_ids(db, scope_id)

    assignments = (
        db.query(UserRoleAssignment)
        .filter(UserRoleAssignment.user_id == user_id, UserRoleAssignment.organization_id == organization_id)
        .all()
    )

    matching_role_id: uuid.UUID | None = None
    matching_scope_id: uuid.UUID | None = None

    for assignment in assignments:
        if assignment.valid_from and now < assignment.valid_from:
            continue
        if assignment.valid_until and now > assignment.valid_until:
            continue

        # NULL scope on the assignment = whole organization. Otherwise
        # the assignment's scope must be the requested scope or one of
        # its ancestors.
        if assignment.scope_id is not None and assignment.scope_id not in allowed_scope_ids:
            continue

        has_permission = (
            db.query(RolePermission)
            .filter(RolePermission.role_id == assignment.role_id, RolePermission.permission_id == permission.id)
            .first()
        )
        if has_permission:
            matching_role_id = assignment.role_id
            matching_scope_id = assignment.scope_id
            break

    if matching_role_id is None:
        return AuthorizationDecision(
            allowed=False,
            reason=f"No role grants {permission.code}",
            policy="RBAC",
            permission_code=permission.code,
        )

    # Resource-state policy (spec §21): a mutating action against a
    # terminal-state resource is denied even though the role/permission
    # check above passed.
    if resource_state is not None and action in _MUTATING_ACTIONS and resource_state in _TERMINAL_STATES:
        return AuthorizationDecision(
            allowed=False,
            reason=f"Resource is {resource_state.value}; {action.value} is not permitted in this state",
            policy="RESOURCE_STATE",
            permission_code=permission.code,
        )

    # Segregation of duties (spec §20): Layer 1 checks the direct
    # "the resource owner cannot also perform this action" case. A full
    # workflow-history-aware SoD engine (arbitrary action_a/action_b
    # pairs across a resource's audit trail) is later-layer work.
    if resource_owner_id is not None and resource_owner_id == user_id:
        conflicting_policy = (
            db.query(SoDPolicy)
            .filter(
                SoDPolicy.active.is_(True),
                SoDPolicy.action_b == action,
                (SoDPolicy.organization_id == organization_id) | (SoDPolicy.organization_id.is_(None)),
            )
            .first()
        )
        if conflicting_policy is not None:
            return AuthorizationDecision(
                allowed=False,
                reason=f"Segregation of duties: {conflicting_policy.name}",
                policy="SOD",
                permission_code=permission.code,
            )

    return AuthorizationDecision(
        allowed=True,
        reason="Granted",
        policy=None,
        scope_id=matching_scope_id,
        role_id=matching_role_id,
        permission_code=permission.code,
    )
