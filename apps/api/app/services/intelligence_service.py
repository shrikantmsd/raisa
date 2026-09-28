"""
Layer 3 domain service.

The one new idea beyond Layer 2's pattern: `visible_intelligence_query`.
Every other domain in this codebase answers "which rows can this user
see" with a single `WHERE organization_id = actor.organization_id`.
Intelligence can't, because GLOBAL items are legitimately owned by a
DIFFERENT organization_id (CoLAB's platform org) than the customer
reading them. Layer 1's `authorize()` is unchanged and still only
answers "does this user hold permission P in their own org" — the
extra "...or is it a published+distributed GLOBAL item" clause lives
entirely here, in the query layer, exactly where Layer 1/2's ordinary
tenant filters already live. Mutations stay strictly single-tenant via
`_require_own_org` — reading someone else's distributed content is not
the same as being allowed to change it.
"""
import json
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import and_, or_
from sqlalchemy.orm import Query, Session

from app.models.audit import AuditEventType
from app.models.ctd import CTDModule, CTDSection
from app.models.intelligence import (
    ALLOWED_INTELLIGENCE_TRANSITIONS,
    IntelligenceDistribution,
    IntelligenceItemTag,
    IntelligenceObjectLink,
    IntelligenceScope,
    IntelligenceStatus,
    RegulatoryIntelligenceItem,
)
from app.models.organization import Organization, OrganizationType
from app.models.platform import Configuration, ConfigurationScope
from app.models.rbac import PermissionAction, PermissionDomain
from app.models.regulatory_activity import RegulatoryEventType
from app.models.regulatory_structure import Product, RegulatoryApplication, RegulatoryAuthority, RegulatoryPortfolio
from app.models.dossier import Dossier
from app.models.regulatory_activity import RegulatoryActivity
from app.services import audit_service, regulatory_event_service
from app.services.authorization_service import authorize

# Object types a TENANT/PRIVATE intelligence item may link to, and the
# model+column used to verify the linked row actually belongs to the
# SAME organization as the intelligence item (spec §14 — links must not
# leak across tenants). GLOBAL reference types (CTD_MODULE, CTD_SECTION)
# are intentionally absent: they have no organization_id to check
# because they're not tenant-owned in the first place.
_TENANT_OWNED_LINK_TYPES: dict[str, type] = {
    "PRODUCT": Product,
    "REGULATORY_PORTFOLIO": RegulatoryPortfolio,
    "APPLICATION": RegulatoryApplication,
    "DOSSIER": Dossier,
    "REGULATORY_ACTIVITY": RegulatoryActivity,
}
_GLOBAL_LINK_TYPES: dict[str, type] = {
    "CTD_MODULE": CTDModule,
    "CTD_SECTION": CTDSection,
}


class DomainError(Exception):
    def __init__(self, message: str, *, status_code: int = 403):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _require(db: Session, *, user_id: uuid.UUID, organization_id: uuid.UUID, action: PermissionAction, domain: PermissionDomain = PermissionDomain.INTELLIGENCE) -> None:
    decision = authorize(db=db, user_id=user_id, organization_id=organization_id, domain=domain, action=action)
    if not decision.allowed:
        raise DomainError(decision.reason, status_code=403)


def _require_own_org(item: RegulatoryIntelligenceItem, organization_id: uuid.UUID) -> None:
    """Mutation guard (spec §5-6): reading a distributed GLOBAL item is
    fine; changing it is not, no matter what INTELLIGENCE permission the
    caller holds in their own org. This one check is also what makes
    "Tenant Administrator cannot modify global CoLAB intelligence" and
    "Tenant A cannot modify Tenant B intelligence" the same rule."""
    if item.organization_id != organization_id:
        raise DomainError("Cannot modify intelligence owned by another organization", status_code=403)


def get_platform_organization(db: Session) -> Organization:
    """No magic tenant-zero id (per your confirmation) — looked up by
    `organization_type`. Raises if seed data hasn't created it yet."""
    org = db.query(Organization).filter(Organization.organization_type == OrganizationType.PLATFORM).first()
    if org is None:
        raise DomainError("No platform organization configured", status_code=500)
    return org


def visible_intelligence_query(db: Session, *, actor_organization_id: uuid.UUID) -> Query:
    """The read-side visibility rule (spec §5, §24 test 5):
    - anything owned by the caller's own org (their TENANT/PRIVATE items,
      or every item if the caller's org IS the platform org), OR
    - a GLOBAL item that is PUBLISHED and has an explicit
      IntelligenceDistribution grant to the caller's org.

    PRIVATE-item creator-only narrowing happens one layer up (routes),
    where the caller's user_id and ADMINISTER status are known — this
    function answers "which organization can see this row", not "which
    user".
    """
    distributed_ids = (
        db.query(IntelligenceDistribution.intelligence_item_id)
        .filter(IntelligenceDistribution.organization_id == actor_organization_id)
        .scalar_subquery()
    )
    return db.query(RegulatoryIntelligenceItem).filter(
        or_(
            RegulatoryIntelligenceItem.organization_id == actor_organization_id,
            and_(
                RegulatoryIntelligenceItem.scope == IntelligenceScope.GLOBAL,
                RegulatoryIntelligenceItem.status == IntelligenceStatus.PUBLISHED,
                RegulatoryIntelligenceItem.id.in_(distributed_ids),
            ),
        )
    )


def _organization_is_platform(db: Session, organization_id: uuid.UUID) -> bool:
    org = db.get(Organization, organization_id)
    return org is not None and org.organization_type == OrganizationType.PLATFORM


def require_platform_organization(db: Session, organization_id: uuid.UUID, *, what: str) -> None:
    """GLOBAL content, the source registry, and the shared tag vocabulary
    are CoLAB-managed (spec §5-6). Permission grants alone can't enforce
    that — a customer org can define a custom role holding any permission
    — so writes to anything that is visible across tenants additionally
    require the caller's organization to BE the platform org."""
    if not _organization_is_platform(db, organization_id):
        raise DomainError(f"Only the platform organization can {what}", status_code=403)


def create_intelligence_item(db: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID, **fields) -> RegulatoryIntelligenceItem:
    _require(db, user_id=actor_id, organization_id=organization_id, action=PermissionAction.CREATE)
    scope = fields.get("scope")
    if scope == IntelligenceScope.GLOBAL:
        # Without this, a customer tenant admin could POST scope=GLOBAL,
        # own the result (so pass every ownership check), and distribute
        # their own content into other tenants' feeds.
        require_platform_organization(db, organization_id, what="create GLOBAL intelligence")
    item = RegulatoryIntelligenceItem(
        organization_id=organization_id,
        status=IntelligenceStatus.DRAFT,
        created_by=actor_id,
        updated_by=actor_id,
        impact_assessed_by=actor_id,
        **fields,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    audit_service.record(
        db, organization_id=organization_id, event_type=AuditEventType.INTELLIGENCE_CREATED, object_type="RegulatoryIntelligenceItem",
        object_id=item.id, user_id=actor_id, new_value=f"title={item.title}, scope={item.scope.value}",
    )
    return item


_TRANSITION_PERMISSION: dict[tuple[IntelligenceStatus, IntelligenceStatus], PermissionAction] = {
    (IntelligenceStatus.DRAFT, IntelligenceStatus.UNDER_REVIEW): PermissionAction.EDIT,
    (IntelligenceStatus.UNDER_REVIEW, IntelligenceStatus.DRAFT): PermissionAction.REVIEW,
    (IntelligenceStatus.UNDER_REVIEW, IntelligenceStatus.PUBLISHED): PermissionAction.PUBLISH,
    (IntelligenceStatus.PUBLISHED, IntelligenceStatus.WITHDRAWN): PermissionAction.PUBLISH,
    (IntelligenceStatus.WITHDRAWN, IntelligenceStatus.UNDER_REVIEW): PermissionAction.REVIEW,
    (IntelligenceStatus.DRAFT, IntelligenceStatus.ARCHIVED): PermissionAction.DELETE,
    (IntelligenceStatus.UNDER_REVIEW, IntelligenceStatus.ARCHIVED): PermissionAction.DELETE,
    (IntelligenceStatus.PUBLISHED, IntelligenceStatus.ARCHIVED): PermissionAction.DELETE,
    (IntelligenceStatus.WITHDRAWN, IntelligenceStatus.ARCHIVED): PermissionAction.DELETE,
}


def transition_intelligence_status(
    db: Session, *, item: RegulatoryIntelligenceItem, actor_id: uuid.UUID, organization_id: uuid.UUID,
    new_status: IntelligenceStatus, reason: str | None = None,
) -> RegulatoryIntelligenceItem:
    _require_own_org(item, organization_id)
    current = item.status
    if new_status not in ALLOWED_INTELLIGENCE_TRANSITIONS.get(current, set()):
        raise DomainError(f"Cannot move intelligence from {current.value} to {new_status.value}", status_code=409)

    _require(db, user_id=actor_id, organization_id=organization_id, action=_TRANSITION_PERMISSION[(current, new_status)])

    item.status = new_status
    item.updated_by = actor_id
    db.commit()
    db.refresh(item)

    event_type = (
        RegulatoryEventType.INTELLIGENCE_PUBLISHED
        if new_status == IntelligenceStatus.PUBLISHED
        else RegulatoryEventType.INTELLIGENCE_STATUS_CHANGED
    )
    audit_service.record(
        db, organization_id=organization_id, event_type=AuditEventType.INTELLIGENCE_STATUS_CHANGED, object_type="RegulatoryIntelligenceItem",
        object_id=item.id, user_id=actor_id, previous_value=current.value, new_value=new_status.value, reason=reason,
    )
    regulatory_event_service.record(
        db, organization_id=organization_id, event_type=event_type, intelligence_item_id=item.id, actor_user_id=actor_id,
        description=f"{current.value} -> {new_status.value}" + (f" ({reason})" if reason else ""),
    )
    return item


def distribute_intelligence_item(
    db: Session, *, item: RegulatoryIntelligenceItem, target_organization_id: uuid.UUID, actor_id: uuid.UUID, organization_id: uuid.UUID,
) -> IntelligenceDistribution:
    """Grants a customer org access to read a GLOBAL+PUBLISHED item
    (spec §5-6, §24 test 5). Only the OWNING org (CoLAB) can distribute
    its own items — `_require_own_org` here is what stops a customer
    tenant from "distributing" someone else's content to a third org."""
    _require_own_org(item, organization_id)
    if item.scope != IntelligenceScope.GLOBAL:
        raise DomainError("Only GLOBAL intelligence can be distributed", status_code=409)
    # Defense in depth alongside the create-time check: even if a
    # GLOBAL-scope row somehow existed under a customer org, it must
    # never be distributable to other tenants.
    require_platform_organization(db, organization_id, what="distribute intelligence")
    if item.status != IntelligenceStatus.PUBLISHED:
        raise DomainError("Only PUBLISHED intelligence can be distributed", status_code=409)
    _require(db, user_id=actor_id, organization_id=organization_id, action=PermissionAction.PUBLISH)

    existing = (
        db.query(IntelligenceDistribution)
        .filter(IntelligenceDistribution.intelligence_item_id == item.id, IntelligenceDistribution.organization_id == target_organization_id)
        .first()
    )
    if existing:
        return existing

    grant = IntelligenceDistribution(
        intelligence_item_id=item.id, organization_id=target_organization_id,
        distributed_at=datetime.now(timezone.utc), distributed_by=actor_id,
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)

    audit_service.record(
        db, organization_id=organization_id, event_type=AuditEventType.INTELLIGENCE_DISTRIBUTED, object_type="IntelligenceDistribution",
        object_id=grant.id, user_id=actor_id, new_value=f"to_organization={target_organization_id}",
    )
    regulatory_event_service.record(
        db, organization_id=organization_id, event_type=RegulatoryEventType.INTELLIGENCE_DISTRIBUTED,
        intelligence_item_id=item.id, actor_user_id=actor_id, description=f"distributed to organization {target_organization_id}",
    )

    if item.impact_level.value in ("CRITICAL", "HIGH"):
        from app.services import notification_service

        notification_service.notify_organization_admins(
            db, organization_id=target_organization_id,
            notification_type="intelligence_distributed",
            title=f"New {item.impact_level.value.title()}-impact intelligence: {item.title}",
            message=item.summary,
        )
    return grant


def tag_intelligence_item(db: Session, *, item: RegulatoryIntelligenceItem, tag_id: uuid.UUID, actor_id: uuid.UUID, organization_id: uuid.UUID) -> IntelligenceItemTag:
    _require_own_org(item, organization_id)
    _require(db, user_id=actor_id, organization_id=organization_id, action=PermissionAction.EDIT)
    existing = (
        db.query(IntelligenceItemTag)
        .filter(IntelligenceItemTag.intelligence_item_id == item.id, IntelligenceItemTag.tag_id == tag_id)
        .first()
    )
    if existing:
        return existing
    link = IntelligenceItemTag(intelligence_item_id=item.id, tag_id=tag_id)
    db.add(link)
    db.commit()
    return link


def link_intelligence_object(
    db: Session, *, item: RegulatoryIntelligenceItem, linked_object_type: str, linked_object_id: uuid.UUID,
    actor_id: uuid.UUID, organization_id: uuid.UUID,
) -> IntelligenceObjectLink:
    """Spec §14. Tenant-owned target types must belong to the SAME org as
    the intelligence item — this is what stops a GLOBAL CoLAB item (or a
    different tenant's item) from linking directly into another
    customer's private Product/Dossier/Activity."""
    _require_own_org(item, organization_id)
    _require(db, user_id=actor_id, organization_id=organization_id, action=PermissionAction.EDIT)

    if linked_object_type in _TENANT_OWNED_LINK_TYPES:
        model = _TENANT_OWNED_LINK_TYPES[linked_object_type]
        target = db.get(model, linked_object_id)
        if target is None or target.organization_id != item.organization_id:
            raise DomainError("Linked object must belong to the same organization as the intelligence item", status_code=400)
    elif linked_object_type not in _GLOBAL_LINK_TYPES:
        raise DomainError(f"Unknown linked_object_type: {linked_object_type}", status_code=400)

    link = IntelligenceObjectLink(
        intelligence_item_id=item.id, linked_object_type=linked_object_type, linked_object_id=linked_object_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


# Fields an author may change while an item is still DRAFT/UNDER_REVIEW.
# `scope` and `organization_id` are deliberately absent: an item's scope
# is fixed at creation, otherwise a TENANT item could be edited into a
# GLOBAL one after the fact and sidestep the create-time platform check.
_EDITABLE_FIELDS = {
    "title", "summary", "full_content_reference", "source_id", "source_url", "authority_id", "country_region",
    "publication_date", "effective_date", "expiry_review_date", "impact_level", "impact_reason",
    "impact_assessment_source", "therapeutic_area", "regulatory_area", "intelligence_type",
}
_EDITABLE_STATES = {IntelligenceStatus.DRAFT, IntelligenceStatus.UNDER_REVIEW}


def _plain(value):
    return value.value if hasattr(value, "value") else (value.isoformat() if isinstance(value, date) else str(value) if value is not None else None)


def update_intelligence_item(
    db: Session, *, item: RegulatoryIntelligenceItem, actor_id: uuid.UUID, organization_id: uuid.UUID, changes: dict,
) -> RegulatoryIntelligenceItem:
    """Spec §18 "Update intelligence". Published/withdrawn/archived items
    are not edited in place — a correction goes withdraw -> review ->
    republish, so the published record stays traceable (spec §23)."""
    _require_own_org(item, organization_id)
    unknown = set(changes) - _EDITABLE_FIELDS
    if unknown:
        raise DomainError(f"Fields cannot be changed: {', '.join(sorted(unknown))}", status_code=400)
    if item.status not in _EDITABLE_STATES:
        raise DomainError(f"Intelligence in {item.status.value} cannot be edited; withdraw and re-review it instead", status_code=409)
    _require(db, user_id=actor_id, organization_id=organization_id, action=PermissionAction.EDIT)

    impact_changing = "impact_level" in changes and changes["impact_level"] != item.impact_level
    if impact_changing and not (changes.get("impact_reason") or "").strip():
        # spec §8: an impact assessment must carry its reason/source.
        raise DomainError("Changing impact_level requires a new impact_reason", status_code=400)

    previous: dict = {}
    updated: dict = {}
    for field, new_value in changes.items():
        old_value = getattr(item, field)
        if old_value != new_value:
            previous[field] = _plain(old_value)
            updated[field] = _plain(new_value)
            setattr(item, field, new_value)
    if not updated:
        return item

    item.updated_by = actor_id
    if impact_changing or "impact_reason" in updated:
        item.impact_assessed_by = actor_id
    db.commit()
    db.refresh(item)

    audit_service.record(
        db, organization_id=organization_id,
        event_type=AuditEventType.INTELLIGENCE_CLASSIFICATION_CHANGED if impact_changing else AuditEventType.INTELLIGENCE_UPDATED,
        object_type="RegulatoryIntelligenceItem", object_id=item.id, user_id=actor_id,
        previous_value=json.dumps(previous), new_value=json.dumps(updated),
    )
    return item


def _load_preferences(db: Session, organization_id: uuid.UUID) -> dict:
    row = (
        db.query(Configuration)
        .filter(
            Configuration.scope == ConfigurationScope.ORGANIZATION,
            Configuration.organization_id == organization_id,
            Configuration.key == "intelligence_preferences",
        )
        .first()
    )
    return json.loads(row.value) if row else {}


def _matches_preferences(item: RegulatoryIntelligenceItem, authority_short_name: str | None, prefs: dict) -> bool:
    """Opt-in: an org with no saved interests matches nothing. For each
    dimension the org DID specify, the item must match — except that an
    item with no value on a dimension (e.g. a generic guideline with no
    therapeutic area) is treated as not constrained by it."""
    countries = prefs.get("countries") or []
    authorities = prefs.get("authorities") or []
    areas = prefs.get("therapeutic_areas") or []
    types = prefs.get("intelligence_types") or []
    if not (countries or authorities or areas or types):
        return False
    if countries and item.country_region and item.country_region not in countries:
        return False
    if authorities and authority_short_name and authority_short_name not in authorities:
        return False
    if areas and item.therapeutic_area and item.therapeutic_area not in areas:
        return False
    if types and item.intelligence_type.value not in types:
        return False
    return True


def suggest_distribution_targets(
    db: Session, *, item: RegulatoryIntelligenceItem, actor_id: uuid.UUID, organization_id: uuid.UUID,
) -> list[Organization]:
    """The "configured-interest" half of the distribution rule. The
    explicit IntelligenceDistribution grant stays the only thing that
    ever gates visibility; customers' saved interests just tell CoLAB
    *who to offer an item to*. It returns suggestions — nothing is
    distributed automatically (automation belongs with the Layer 6
    ingestion pipeline)."""
    _require_own_org(item, organization_id)
    if item.scope != IntelligenceScope.GLOBAL:
        raise DomainError("Only GLOBAL intelligence is distributed", status_code=409)
    require_platform_organization(db, organization_id, what="distribute intelligence")
    _require(db, user_id=actor_id, organization_id=organization_id, action=PermissionAction.PUBLISH)

    authority_short_name = None
    if item.authority_id:
        authority = db.get(RegulatoryAuthority, item.authority_id)
        authority_short_name = authority.short_name if authority else None

    already = {
        row[0]
        for row in db.query(IntelligenceDistribution.organization_id).filter(IntelligenceDistribution.intelligence_item_id == item.id)
    }
    suggestions = []
    for org in db.query(Organization).filter(Organization.organization_type == OrganizationType.CUSTOMER).all():
        if org.id in already:
            continue
        if _matches_preferences(item, authority_short_name, _load_preferences(db, org.id)):
            suggestions.append(org)
    return suggestions
