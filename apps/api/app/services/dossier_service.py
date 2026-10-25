"""
Layer 2 domain service. Every mutation here goes through Layer 1's
`authorize()` for the permission check and `audit_service.record` for
the compliance trail, plus `regulatory_event_service.record` for the
business timeline — nothing in this module checks a role or writes an
audit row on its own (spec Layer 2 §20: "Do not create ad-hoc
permission checks throughout the code").
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.audit import AuditEventType
from app.models.ctd import DocumentCTDPlacement
from app.models.dossier import ALLOWED_DOSSIER_TRANSITIONS, Dossier, DossierStatus
from app.models.rbac import PermissionAction, PermissionDomain, Scope
from app.models.regulatory_activity import RegulatoryActivity, RegulatoryEventType
from app.models.regulatory_structure import Product, RegulatoryApplication
from app.services import audit_service, regulatory_event_service
from app.services.authorization_service import authorize


class DomainError(Exception):
    """Raised for authorization denials and invalid state transitions —
    routes translate this to 403/409 (see api/v1/dossiers.py)."""

    def __init__(self, message: str, *, status_code: int = 403):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _require(
    db: Session, *, user_id: uuid.UUID, organization_id: uuid.UUID, domain: PermissionDomain, action: PermissionAction,
    scope_id: uuid.UUID | None = None,
) -> None:
    decision = authorize(db=db, user_id=user_id, organization_id=organization_id, domain=domain, action=action, scope_id=scope_id)
    if not decision.allowed:
        raise DomainError(f"{decision.reason}", status_code=403)


def resolve_scope(db: Session, *, requested_scope_id: uuid.UUID | None, organization_id: uuid.UUID) -> uuid.UUID | None:
    """Validates a caller-supplied scope_id belongs to their own
    organization before it's stored on a row or handed to authorize() —
    a scope from another tenant must never be usable as a binding.
    None (the default — no scope given) means organization-wide, exactly
    as it already does for a Layer 1 UserRoleAssignment."""
    if requested_scope_id is None:
        return None
    scope = db.get(Scope, requested_scope_id)
    if scope is None or scope.organization_id != organization_id:
        raise DomainError("scope_id does not belong to this organization", status_code=400)
    return requested_scope_id


def filter_by_scope(
    db: Session, items: list, *, user_id: uuid.UUID, organization_id: uuid.UUID, domain: PermissionDomain,
    action: PermissionAction = PermissionAction.VIEW,
) -> list:
    """Per-row visibility filter reusing the SAME authorize() call as
    every single-resource check — no parallel scope-matching logic. A
    row with scope_id=None needs only the ordinary permission; a row
    bound to a scope is visible only to an assignment whose own scope is
    that scope or an ancestor of it (or an org-wide assignment) — see
    authorize()'s existing `_scope_ancestor_ids` walk, unchanged here.
    O(n) authorize() calls; acceptable at this layer's scale — see
    docs/LAYER_4 hardening notes for the possible SQL-side optimization.
    """
    return [
        item for item in items
        if authorize(db=db, user_id=user_id, organization_id=organization_id, domain=domain, action=action, scope_id=item.scope_id).allowed
    ]


def create_product(db: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID, **fields) -> Product:
    scope_id = resolve_scope(db, requested_scope_id=fields.pop("scope_id", None), organization_id=organization_id)
    _require(db, user_id=actor_id, organization_id=organization_id, domain=PermissionDomain.PRODUCT, action=PermissionAction.CREATE, scope_id=scope_id)
    product = Product(organization_id=organization_id, scope_id=scope_id, created_by=actor_id, updated_by=actor_id, **fields)
    db.add(product)
    db.commit()
    db.refresh(product)
    audit_service.record(
        db, organization_id=organization_id, event_type=AuditEventType.USER_CREATED, object_type="Product",
        object_id=product.id, user_id=actor_id, new_value=f"name={product.name}",
    )
    return product


def create_regulatory_application(
    db: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID, **fields
) -> RegulatoryApplication:
    scope_id = resolve_scope(db, requested_scope_id=fields.pop("scope_id", None), organization_id=organization_id)
    _require(db, user_id=actor_id, organization_id=organization_id, domain=PermissionDomain.APPLICATION, action=PermissionAction.CREATE, scope_id=scope_id)
    application = RegulatoryApplication(organization_id=organization_id, scope_id=scope_id, created_by=actor_id, updated_by=actor_id, **fields)
    db.add(application)
    db.commit()
    db.refresh(application)
    audit_service.record(
        db, organization_id=organization_id, event_type=AuditEventType.USER_CREATED, object_type="RegulatoryApplication",
        object_id=application.id, user_id=actor_id,
    )
    return application


def create_dossier(db: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID, **fields) -> Dossier:
    scope_id = resolve_scope(db, requested_scope_id=fields.pop("scope_id", None), organization_id=organization_id)
    _require(db, user_id=actor_id, organization_id=organization_id, domain=PermissionDomain.DOSSIER, action=PermissionAction.CREATE, scope_id=scope_id)
    dossier = Dossier(
        organization_id=organization_id,
        scope_id=scope_id,
        status=DossierStatus.DRAFT,
        owner_id=actor_id,
        created_by=actor_id,
        updated_by=actor_id,
        **fields,
    )
    db.add(dossier)
    db.commit()
    db.refresh(dossier)
    audit_service.record(
        db, organization_id=organization_id, event_type=AuditEventType.USER_CREATED, object_type="Dossier",
        object_id=dossier.id, user_id=actor_id, new_value=f"status={dossier.status.value}",
    )
    regulatory_event_service.record(
        db, organization_id=organization_id, event_type=RegulatoryEventType.DOSSIER_CREATED,
        dossier_id=dossier.id, actor_user_id=actor_id,
    )
    return dossier


# Which PermissionAction gates each (from, to) transition (spec Layer 2
# §4: "a user who can EDIT should not automatically be able to APPROVE
# or LOCK it"). Deliberately explicit rather than derived, so the
# mapping is auditable by reading it, not by tracing authorize() calls.
_TRANSITION_PERMISSION: dict[tuple[DossierStatus, DossierStatus], PermissionAction] = {
    (DossierStatus.DRAFT, DossierStatus.UNDER_REVIEW): PermissionAction.EDIT,
    (DossierStatus.UNDER_REVIEW, DossierStatus.DRAFT): PermissionAction.REVIEW,
    (DossierStatus.UNDER_REVIEW, DossierStatus.ACTIVE): PermissionAction.APPROVE,
    (DossierStatus.ACTIVE, DossierStatus.UNDER_REVIEW): PermissionAction.REVIEW,
    (DossierStatus.ACTIVE, DossierStatus.LOCKED): PermissionAction.PUBLISH,
    (DossierStatus.LOCKED, DossierStatus.ACTIVE): PermissionAction.PUBLISH,
    (DossierStatus.DRAFT, DossierStatus.ARCHIVED): PermissionAction.DELETE,
    (DossierStatus.UNDER_REVIEW, DossierStatus.ARCHIVED): PermissionAction.DELETE,
    (DossierStatus.ACTIVE, DossierStatus.ARCHIVED): PermissionAction.DELETE,
    (DossierStatus.LOCKED, DossierStatus.ARCHIVED): PermissionAction.DELETE,
}


def transition_dossier_status(
    db: Session,
    *,
    dossier: Dossier,
    actor_id: uuid.UUID,
    organization_id: uuid.UUID,
    new_status: DossierStatus,
    reason: str | None = None,
) -> Dossier:
    current_status = dossier.status

    if new_status not in ALLOWED_DOSSIER_TRANSITIONS.get(current_status, set()):
        raise DomainError(
            f"Cannot move a dossier from {current_status.value} to {new_status.value}", status_code=409
        )

    required_action = _TRANSITION_PERMISSION[(current_status, new_status)]
    _require(db, user_id=actor_id, organization_id=organization_id, domain=PermissionDomain.DOSSIER, action=required_action, scope_id=dossier.scope_id)

    previous_status = dossier.status
    dossier.status = new_status
    dossier.updated_by = actor_id
    db.commit()
    db.refresh(dossier)

    audit_service.record(
        db,
        organization_id=organization_id,
        event_type=AuditEventType.USER_STATUS_CHANGED,
        object_type="Dossier",
        object_id=dossier.id,
        user_id=actor_id,
        previous_value=previous_status.value,
        new_value=new_status.value,
        reason=reason,
    )
    regulatory_event_service.record(
        db,
        organization_id=organization_id,
        event_type=RegulatoryEventType.DOSSIER_STATUS_CHANGED,
        dossier_id=dossier.id,
        actor_user_id=actor_id,
        description=f"{previous_status.value} -> {new_status.value}" + (f" ({reason})" if reason else ""),
    )
    return dossier


def associate_document_to_ctd(
    db: Session,
    *,
    dossier: Dossier,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    document_id: uuid.UUID,
    ctd_section_id: uuid.UUID,
    regulatory_activity_id: uuid.UUID | None = None,
) -> DocumentCTDPlacement:
    # Placement inherits the DOSSIER's scope check — CTD Module/Section
    # rows have no organization/scope of their own (they're global
    # reference data, spec Layer 3 hardening note), so "can this user
    # touch CTD structure here" is really "can this user edit THIS
    # dossier".
    _require(db, user_id=actor_id, organization_id=organization_id, domain=PermissionDomain.DOSSIER, action=PermissionAction.EDIT, scope_id=dossier.scope_id)
    dossier_id = dossier.id
    placement = DocumentCTDPlacement(
        organization_id=organization_id,
        document_id=document_id,
        dossier_id=dossier_id,
        ctd_section_id=ctd_section_id,
        regulatory_activity_id=regulatory_activity_id,
        placed_at=datetime.now(timezone.utc),
        placed_by=actor_id,
    )
    db.add(placement)
    db.commit()
    db.refresh(placement)

    audit_service.record(
        db, organization_id=organization_id, event_type=AuditEventType.DOCUMENT_UPLOADED, object_type="DocumentCTDPlacement",
        object_id=placement.id, user_id=actor_id,
    )
    regulatory_event_service.record(
        db, organization_id=organization_id, event_type=RegulatoryEventType.DOCUMENT_ADDED,
        dossier_id=dossier_id, document_id=document_id, actor_user_id=actor_id,
    )
    return placement


def create_regulatory_activity(db: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID, **fields) -> RegulatoryActivity:
    scope_id = resolve_scope(db, requested_scope_id=fields.pop("scope_id", None), organization_id=organization_id)
    _require(db, user_id=actor_id, organization_id=organization_id, domain=PermissionDomain.ACTIVITY, action=PermissionAction.CREATE, scope_id=scope_id)
    activity = RegulatoryActivity(organization_id=organization_id, scope_id=scope_id, created_by=actor_id, updated_by=actor_id, **fields)
    db.add(activity)
    db.commit()
    db.refresh(activity)

    audit_service.record(
        db, organization_id=organization_id, event_type=AuditEventType.USER_CREATED, object_type="RegulatoryActivity",
        object_id=activity.id, user_id=actor_id,
    )
    regulatory_event_service.record(
        db, organization_id=organization_id, event_type=RegulatoryEventType.ACTIVITY_CREATED,
        regulatory_activity_id=activity.id, dossier_id=fields.get("dossier_id"), actor_user_id=actor_id,
    )
    return activity
