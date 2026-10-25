"""
Layer 3 — the behaviors that close gaps found on self-review: who may
create GLOBAL content, how published items may (not) be edited, audit
coverage for sources/tags/preferences, notification + event side
effects, configured-interest suggestions, and input validation.
"""
import json

from app.models.audit import AuditEvent, AuditEventType
from app.models.intelligence import ImpactLevel, IntelligenceScope, IntelligenceStatus
from app.models.platform import Notification
from app.models.rbac import PermissionAction, PermissionDomain
from app.models.regulatory_activity import RegulatoryEvent, RegulatoryEventType

from tests.conftest import (
    assign_role,
    login_headers,
    make_authority,
    make_intelligence_item,
    make_organization,
    make_platform_organization,
    make_role_with_permissions,
    make_user,
)

FULL = [(PermissionDomain.INTELLIGENCE, a) for a in PermissionAction]
NEW_ITEM = {"scope": "TENANT", "intelligence_type": "REGULATORY_CHANGE", "title": "t", "summary": "s", "impact_level": "LOW", "impact_reason": "r"}


def _user_with(db, org, email, permissions, role_name):
    role = make_role_with_permissions(db, organization=None, name=role_name, permissions=permissions)
    user = make_user(db, organization=org, email=email)
    assign_role(db, user=user, organization=org, role=role)
    return user


# --- the injection hole -------------------------------------------------

def test_customer_tenant_cannot_create_global_intelligence(db, client):
    """Even holding every INTELLIGENCE permission, a customer org can't
    mint GLOBAL content (which it could otherwise own and distribute to
    other tenants)."""
    customer = make_organization(db, name="Acme Pharma", slug="acme")
    _user_with(db, customer, "admin@acme.example", FULL, "Full Intel")
    headers = login_headers(client, organization_slug="acme", email="admin@acme.example")

    response = client.post("/api/v1/intelligence", headers=headers, json={**NEW_ITEM, "scope": "GLOBAL"})
    assert response.status_code == 403
    # ...but the same tenant's own TENANT-scope item is fine.
    assert client.post("/api/v1/intelligence", headers=headers, json=NEW_ITEM).status_code == 201


def test_customer_cannot_distribute_even_a_forged_global_row(db, client):
    """Defense in depth: if a GLOBAL row were somehow owned by a customer
    org, distribute still refuses."""
    customer = make_organization(db, name="Acme Pharma", slug="acme")
    other = make_organization(db, name="Other Pharma", slug="other")
    user = _user_with(db, customer, "admin@acme.example", FULL, "Full Intel")
    forged = make_intelligence_item(db, organization=customer, creator=user, scope=IntelligenceScope.GLOBAL, status=IntelligenceStatus.PUBLISHED)

    headers = login_headers(client, organization_slug="acme", email="admin@acme.example")
    response = client.post(f"/api/v1/intelligence/{forged.id}/distribute", headers=headers, json={"target_organization_id": str(other.id)})
    assert response.status_code == 403


def test_customer_cannot_create_shared_tags(db, client):
    customer = make_organization(db, name="Acme Pharma", slug="acme")
    _user_with(db, customer, "admin@acme.example", FULL, "Full Intel")
    headers = login_headers(client, organization_slug="acme", email="admin@acme.example")
    assert client.post("/api/v1/intelligence/tags", headers=headers, json={"tag_type": "REGULATORY_TOPIC", "name": "Injected"}).status_code == 403


# --- update rules -------------------------------------------------------

def test_update_draft_ok_but_published_is_immutable(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    _user_with(db, org, "user@acme.example", FULL, "Full Intel")
    headers = login_headers(client, organization_slug="acme", email="user@acme.example")
    item_id = client.post("/api/v1/intelligence", headers=headers, json=NEW_ITEM).json()["id"]

    edited = client.patch(f"/api/v1/intelligence/{item_id}", headers=headers, json={"title": "Better title"})
    assert edited.status_code == 200 and edited.json()["title"] == "Better title"

    client.post(f"/api/v1/intelligence/{item_id}/transition", headers=headers, json={"new_status": "UNDER_REVIEW"})
    client.post(f"/api/v1/intelligence/{item_id}/transition", headers=headers, json={"new_status": "PUBLISHED"})
    locked = client.patch(f"/api/v1/intelligence/{item_id}", headers=headers, json={"title": "Silent rewrite"})
    assert locked.status_code == 409


def test_scope_cannot_be_changed_by_update(db, client):
    """Otherwise a TENANT item could be edited into GLOBAL after the
    create-time platform check."""
    org = make_organization(db, name="Acme Pharma", slug="acme")
    _user_with(db, org, "user@acme.example", FULL, "Full Intel")
    headers = login_headers(client, organization_slug="acme", email="user@acme.example")
    item_id = client.post("/api/v1/intelligence", headers=headers, json=NEW_ITEM).json()["id"]

    attempt = client.patch(f"/api/v1/intelligence/{item_id}", headers=headers, json={"scope": "GLOBAL"})
    assert attempt.status_code == 422  # rejected loudly, not silently ignored
    assert client.get(f"/api/v1/intelligence/{item_id}", headers=headers).json()["scope"] == "TENANT"


def test_changing_impact_requires_reason_and_is_audited_as_classification_change(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    _user_with(db, org, "user@acme.example", FULL, "Full Intel")
    headers = login_headers(client, organization_slug="acme", email="user@acme.example")
    item_id = client.post("/api/v1/intelligence", headers=headers, json=NEW_ITEM).json()["id"]

    no_reason = client.patch(f"/api/v1/intelligence/{item_id}", headers=headers, json={"impact_level": "CRITICAL"})
    assert no_reason.status_code == 400

    with_reason = client.patch(
        f"/api/v1/intelligence/{item_id}", headers=headers, json={"impact_level": "CRITICAL", "impact_reason": "Agency deadline moved up"}
    )
    assert with_reason.status_code == 200

    row = (
        db.query(AuditEvent)
        .filter(AuditEvent.object_id == item_id, AuditEvent.event_type == AuditEventType.INTELLIGENCE_CLASSIFICATION_CHANGED)
        .one()
    )
    assert json.loads(row.previous_value)["impact_level"] == "LOW"
    assert json.loads(row.new_value)["impact_level"] == "CRITICAL"


def test_cross_tenant_update_is_404(db, client):
    a = make_organization(db, name="A", slug="tenant-a")
    b = make_organization(db, name="B", slug="tenant-b")
    _user_with(db, a, "u@a.example", FULL, "Full Intel A")
    user_b = make_user(db, organization=b, email="u@b.example")
    item_b = make_intelligence_item(db, organization=b, creator=user_b)
    headers = login_headers(client, organization_slug="tenant-a", email="u@a.example")
    assert client.patch(f"/api/v1/intelligence/{item_b.id}", headers=headers, json={"title": "hijack"}).status_code == 404


# --- audit coverage (spec §20) ----------------------------------------

def test_source_and_preference_changes_are_audited(db, client):
    colab = make_platform_organization(db)
    customer = make_organization(db, name="Acme Pharma", slug="acme")
    _user_with(db, colab, "colab.admin@example.com", [(PermissionDomain.INTELLIGENCE_SOURCE, a) for a in (PermissionAction.CREATE, PermissionAction.EDIT)], "Source Admin")
    _user_with(db, customer, "admin@acme.example", [(PermissionDomain.INTELLIGENCE_CONFIGURATION, a) for a in (PermissionAction.VIEW, PermissionAction.EDIT)], "Config Admin")

    colab_headers = login_headers(client, organization_slug="colab-systems", email="colab.admin@example.com")
    source_id = client.post("/api/v1/intelligence/sources", headers=colab_headers, json={"name": "Wire", "source_type": "NEWS_AGGREGATOR"}).json()["id"]
    client.patch(f"/api/v1/intelligence/sources/{source_id}", headers=colab_headers, json={"active": False})
    source_events = db.query(AuditEvent).filter(AuditEvent.object_id == source_id, AuditEvent.event_type == AuditEventType.INTELLIGENCE_SOURCE_CHANGED).all()
    assert len(source_events) == 2  # create + update

    customer_headers = login_headers(client, organization_slug="acme", email="admin@acme.example")
    client.put("/api/v1/intelligence/preferences", headers=customer_headers, json={"countries": ["US"]})
    client.put("/api/v1/intelligence/preferences", headers=customer_headers, json={"countries": ["US", "IN"]})
    pref_events = db.query(AuditEvent).filter(AuditEvent.event_type == AuditEventType.CONFIGURATION_CHANGED, AuditEvent.organization_id == customer.id).all()
    assert len(pref_events) == 2
    assert pref_events[-1].previous_value is not None  # second change records what it replaced


def test_source_update_of_unknown_source_is_404(db, client):
    colab = make_platform_organization(db)
    _user_with(db, colab, "colab.admin@example.com", [(PermissionDomain.INTELLIGENCE_SOURCE, PermissionAction.EDIT)], "Source Editor")
    headers = login_headers(client, organization_slug="colab-systems", email="colab.admin@example.com")
    assert client.patch("/api/v1/intelligence/sources/00000000-0000-0000-0000-000000000000", headers=headers, json={"active": False}).status_code == 404


# --- side effects: regulatory events + notifications ------------------

def test_publishing_records_a_regulatory_event(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    _user_with(db, org, "user@acme.example", FULL, "Full Intel")
    headers = login_headers(client, organization_slug="acme", email="user@acme.example")
    item_id = client.post("/api/v1/intelligence", headers=headers, json=NEW_ITEM).json()["id"]
    client.post(f"/api/v1/intelligence/{item_id}/transition", headers=headers, json={"new_status": "UNDER_REVIEW"})
    client.post(f"/api/v1/intelligence/{item_id}/transition", headers=headers, json={"new_status": "PUBLISHED"})

    events = db.query(RegulatoryEvent).filter(RegulatoryEvent.intelligence_item_id == item_id).all()
    assert RegulatoryEventType.INTELLIGENCE_PUBLISHED in {e.event_type for e in events}


def _publish_global(db, colab, colab_user, *, impact):
    return make_intelligence_item(
        db, organization=colab, creator=colab_user, scope=IntelligenceScope.GLOBAL, status=IntelligenceStatus.PUBLISHED, impact_level=impact,
    )


def test_high_impact_distribution_notifies_tenant_admins_but_low_impact_does_not(db, client):
    from app.models.rbac import Role, RoleCategory

    colab = make_platform_organization(db)
    customer = make_organization(db, name="Acme Pharma", slug="acme")
    colab_user = _user_with(db, colab, "colab.admin@example.com", FULL, "CoLAB Intel")

    tenant_admin_role = Role(organization_id=None, code="TENANT_ADMINISTRATOR", name="Tenant Administrator", category=RoleCategory.PLATFORM)
    db.add(tenant_admin_role)
    db.commit()
    admin_user = make_user(db, organization=customer, email="admin@acme.example")
    assign_role(db, user=admin_user, organization=customer, role=tenant_admin_role)

    headers = login_headers(client, organization_slug="colab-systems", email="colab.admin@example.com")
    high = _publish_global(db, colab, colab_user, impact=ImpactLevel.HIGH)
    low = _publish_global(db, colab, colab_user, impact=ImpactLevel.LOW)

    assert client.post(f"/api/v1/intelligence/{low.id}/distribute", headers=headers, json={"target_organization_id": str(customer.id)}).status_code == 201
    assert db.query(Notification).filter(Notification.user_id == admin_user.id).count() == 0

    assert client.post(f"/api/v1/intelligence/{high.id}/distribute", headers=headers, json={"target_organization_id": str(customer.id)}).status_code == 201
    notes = db.query(Notification).filter(Notification.user_id == admin_user.id).all()
    assert len(notes) == 1 and notes[0].organization_id == customer.id


# --- configured-interest suggestions ---------------------------------

def test_distribution_suggestions_follow_configured_interests(db, client):
    colab = make_platform_organization(db)
    colab_user = _user_with(db, colab, "colab.admin@example.com", FULL, "CoLAB Intel")
    fda = make_authority(db, short_name="FDA", region="US")

    match = make_organization(db, name="Match Pharma", slug="match")
    miss = make_organization(db, name="Miss Pharma", slug="miss")
    silent = make_organization(db, name="No Prefs Pharma", slug="silent")
    for org, prefs in ((match, {"authorities": ["FDA"], "countries": ["US"]}), (miss, {"authorities": ["EMA"]})):
        user = _user_with(db, org, f"admin@{org.slug}.example", [(PermissionDomain.INTELLIGENCE_CONFIGURATION, a) for a in (PermissionAction.VIEW, PermissionAction.EDIT)], f"Cfg {org.slug}")
        h = login_headers(client, organization_slug=org.slug, email=f"admin@{org.slug}.example")
        assert client.put("/api/v1/intelligence/preferences", headers=h, json=prefs).status_code == 200

    item = _publish_global(db, colab, colab_user, impact=ImpactLevel.HIGH)
    item.authority_id, item.country_region = fda.id, "US"
    db.commit()

    headers = login_headers(client, organization_slug="colab-systems", email="colab.admin@example.com")
    slugs = {o["slug"] for o in client.get(f"/api/v1/intelligence/{item.id}/distribution-suggestions", headers=headers).json()}
    assert slugs == {"match"}  # `miss` wants EMA; `silent` opted into nothing

    client.post(f"/api/v1/intelligence/{item.id}/distribute", headers=headers, json={"target_organization_id": str(match.id)})
    again = {o["slug"] for o in client.get(f"/api/v1/intelligence/{item.id}/distribution-suggestions", headers=headers).json()}
    assert "match" not in again  # already distributed


def test_customer_cannot_ask_for_distribution_suggestions(db, client):
    colab = make_platform_organization(db)
    customer = make_organization(db, name="Acme Pharma", slug="acme")
    colab_user = make_user(db, organization=colab, email="colab.admin@example.com")
    _user_with(db, customer, "admin@acme.example", FULL, "Full Intel")
    from tests.conftest import make_distribution

    item = _publish_global(db, colab, colab_user, impact=ImpactLevel.HIGH)
    make_distribution(db, item=item, organization=customer)  # customer can SEE it...
    headers = login_headers(client, organization_slug="acme", email="admin@acme.example")
    assert client.get(f"/api/v1/intelligence/{item.id}", headers=headers).status_code == 200
    # ...but can't enumerate other tenants' interests.
    assert client.get(f"/api/v1/intelligence/{item.id}/distribution-suggestions", headers=headers).status_code == 403


# --- input validation -------------------------------------------------

def test_invalid_enum_values_are_422_not_500(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    _user_with(db, org, "user@acme.example", FULL + [(PermissionDomain.PRODUCT, PermissionAction.CREATE)], "Full Intel")
    headers = login_headers(client, organization_slug="acme", email="user@acme.example")

    assert client.post("/api/v1/intelligence", headers=headers, json={**NEW_ITEM, "impact_level": "SEVERE"}).status_code == 422
    assert client.post("/api/v1/intelligence", headers=headers, json={**NEW_ITEM, "intelligence_type": "GOSSIP"}).status_code == 422
    assert client.post("/api/v1/intelligence", headers=headers, json={**NEW_ITEM, "scope": "EVERYONE"}).status_code == 422
    # and the Layer 2 request that used to 500 on a bad enum string:
    assert client.post("/api/v1/products", headers=headers, json={"name": "P", "development_status": "NOT_A_STATUS"}).status_code == 422
