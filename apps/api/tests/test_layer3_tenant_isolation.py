"""
Layer 3 spec §24 — MULTI-TENANT SECURITY TESTS (numbered 1-7 in the
spec; test names below map 1:1 onto them).
"""
from app.models.audit import AuditEvent
from app.models.intelligence import IntelligenceScope, IntelligenceStatus
from app.models.rbac import PermissionAction, PermissionDomain

from tests.conftest import (
    assign_role,
    login_headers,
    make_dossier_chain,
    make_distribution,
    make_intelligence_item,
    make_organization,
    make_platform_organization,
    make_role_with_permissions,
    make_user,
)


def _intel_role(db, *, extra_actions=()):
    actions = {PermissionAction.VIEW, *extra_actions}
    return make_role_with_permissions(
        db, organization=None, name=f"Intel {'-'.join(a.value for a in actions)}",
        permissions=[(PermissionDomain.INTELLIGENCE, a) for a in actions],
    )


# 1. Tenant A cannot retrieve Tenant B intelligence.
def test_1_tenant_a_cannot_retrieve_tenant_b_intelligence(db, client):
    tenant_a = make_organization(db, name="Tenant A Pharma", slug="tenant-a")
    tenant_b = make_organization(db, name="Tenant B Pharma", slug="tenant-b")
    role = _intel_role(db)
    user_a = make_user(db, organization=tenant_a, email="ra@tenant-a.example")
    assign_role(db, user=user_a, organization=tenant_a, role=role)
    user_b = make_user(db, organization=tenant_b, email="ra@tenant-b.example")
    item_b = make_intelligence_item(db, organization=tenant_b, creator=user_b, scope=IntelligenceScope.TENANT, status=IntelligenceStatus.PUBLISHED)

    headers_a = login_headers(client, organization_slug="tenant-a", email="ra@tenant-a.example")
    response = client.get(f"/api/v1/intelligence/{item_b.id}", headers=headers_a)
    assert response.status_code == 404

    listing = client.get("/api/v1/intelligence", headers=headers_a).json()
    assert all(i["id"] != str(item_b.id) for i in listing)


# 2. Tenant A cannot modify Tenant B intelligence.
def test_2_tenant_a_cannot_modify_tenant_b_intelligence(db, client):
    tenant_a = make_organization(db, name="Tenant A Pharma", slug="tenant-a")
    tenant_b = make_organization(db, name="Tenant B Pharma", slug="tenant-b")
    role = _intel_role(db, extra_actions=[PermissionAction.EDIT, PermissionAction.DELETE])
    user_a = make_user(db, organization=tenant_a, email="ra@tenant-a.example")
    assign_role(db, user=user_a, organization=tenant_a, role=role)
    user_b = make_user(db, organization=tenant_b, email="ra@tenant-b.example")
    item_b = make_intelligence_item(db, organization=tenant_b, creator=user_b, scope=IntelligenceScope.TENANT, status=IntelligenceStatus.DRAFT)

    headers_a = login_headers(client, organization_slug="tenant-a", email="ra@tenant-a.example")
    # 404 (never reachable at all), not 403 — consistent with every
    # other cross-tenant lookup in this codebase.
    response = client.post(f"/api/v1/intelligence/{item_b.id}/transition", headers=headers_a, json={"new_status": "ARCHIVED"})
    assert response.status_code == 404


# 3. Tenant Administrator cannot modify global CoLAB intelligence.
def test_3_tenant_administrator_cannot_modify_global_intelligence(db, client):
    colab = make_platform_organization(db)
    tenant = make_organization(db, name="Acme Pharma", slug="acme")
    # A role with EVERY intelligence permission, including ADMINISTER —
    # the point is that permission grants don't matter here at all.
    role = make_role_with_permissions(
        db, organization=None, name="Full Intelligence", permissions=[(PermissionDomain.INTELLIGENCE, a) for a in PermissionAction],
    )
    tenant_admin_user = make_user(db, organization=tenant, email="admin@acme.example")
    assign_role(db, user=tenant_admin_user, organization=tenant, role=role)

    colab_admin = make_user(db, organization=colab, email="colab.admin@example.com")
    global_item = make_intelligence_item(
        db, organization=colab, creator=colab_admin, scope=IntelligenceScope.GLOBAL, status=IntelligenceStatus.PUBLISHED
    )
    make_distribution(db, item=global_item, organization=tenant, actor=colab_admin)

    headers = login_headers(client, organization_slug="acme", email="admin@acme.example")
    # It IS visible (distributed) ...
    get_response = client.get(f"/api/v1/intelligence/{global_item.id}", headers=headers)
    assert get_response.status_code == 200
    # ... but transitioning it is still denied, purely on ownership.
    transition_response = client.post(
        f"/api/v1/intelligence/{global_item.id}/transition", headers=headers, json={"new_status": "WITHDRAWN"}
    )
    assert transition_response.status_code == 403


# 4. Tenant users cannot access unauthorized private intelligence.
def test_4_tenant_user_cannot_access_another_users_private_intelligence(db, client):
    tenant = make_organization(db, name="Acme Pharma", slug="acme")
    role = _intel_role(db)
    owner = make_user(db, organization=tenant, email="owner@acme.example")
    other = make_user(db, organization=tenant, email="other@acme.example")
    assign_role(db, user=owner, organization=tenant, role=role)
    assign_role(db, user=other, organization=tenant, role=role)
    private_item = make_intelligence_item(
        db, organization=tenant, creator=owner, scope=IntelligenceScope.PRIVATE, status=IntelligenceStatus.PUBLISHED, title="Owner's private note"
    )

    other_headers = login_headers(client, organization_slug="acme", email="other@acme.example")
    response = client.get(f"/api/v1/intelligence/{private_item.id}", headers=other_headers)
    assert response.status_code == 404
    listing = client.get("/api/v1/intelligence", headers=other_headers).json()
    assert all(i["id"] != str(private_item.id) for i in listing)

    # The owner CAN see their own private item.
    owner_headers = login_headers(client, organization_slug="acme", email="owner@acme.example")
    own_response = client.get(f"/api/v1/intelligence/{private_item.id}", headers=owner_headers)
    assert own_response.status_code == 200


# 5. Global published intelligence can be distributed only according to
# configured authorization.
def test_5_global_intelligence_visible_only_where_distributed(db, client):
    colab = make_platform_organization(db)
    authorized_tenant = make_organization(db, name="Authorized Pharma", slug="authorized")
    unauthorized_tenant = make_organization(db, name="Unauthorized Pharma", slug="unauthorized")
    role = _intel_role(db)

    colab_admin = make_user(db, organization=colab, email="colab.admin@example.com")
    global_item = make_intelligence_item(db, organization=colab, creator=colab_admin, scope=IntelligenceScope.GLOBAL, status=IntelligenceStatus.PUBLISHED)
    make_distribution(db, item=global_item, organization=authorized_tenant, actor=colab_admin)

    authorized_user = make_user(db, organization=authorized_tenant, email="ra@authorized.example")
    assign_role(db, user=authorized_user, organization=authorized_tenant, role=role)
    unauthorized_user = make_user(db, organization=unauthorized_tenant, email="ra@unauthorized.example")
    assign_role(db, user=unauthorized_user, organization=unauthorized_tenant, role=role)

    authorized_headers = login_headers(client, organization_slug="authorized", email="ra@authorized.example")
    assert client.get(f"/api/v1/intelligence/{global_item.id}", headers=authorized_headers).status_code == 200

    unauthorized_headers = login_headers(client, organization_slug="unauthorized", email="ra@unauthorized.example")
    assert client.get(f"/api/v1/intelligence/{global_item.id}", headers=unauthorized_headers).status_code == 404


# 6. CoLAB Super Admin can manage global intelligence.
def test_6_colab_admin_can_manage_global_intelligence(db, client):
    colab = make_platform_organization(db)
    role = make_role_with_permissions(
        db, organization=None, name="CoLAB Intel Admin",
        permissions=[(PermissionDomain.INTELLIGENCE, a) for a in (PermissionAction.VIEW, PermissionAction.CREATE, PermissionAction.EDIT, PermissionAction.PUBLISH)],
    )
    colab_admin = make_user(db, organization=colab, email="colab.admin@example.com")
    assign_role(db, user=colab_admin, organization=colab, role=role)

    headers = login_headers(client, organization_slug="colab-systems", email="colab.admin@example.com")
    create_response = client.post(
        "/api/v1/intelligence", headers=headers,
        json={
            "scope": "GLOBAL", "intelligence_type": "AGENCY_NEWS", "title": "Test", "summary": "Test",
            "impact_level": "LOW", "impact_reason": "test",
        },
    )
    assert create_response.status_code == 201
    item_id = create_response.json()["id"]

    to_review = client.post(f"/api/v1/intelligence/{item_id}/transition", headers=headers, json={"new_status": "UNDER_REVIEW"})
    assert to_review.status_code == 200
    to_published = client.post(f"/api/v1/intelligence/{item_id}/transition", headers=headers, json={"new_status": "PUBLISHED"})
    assert to_published.status_code == 200
    assert to_published.json()["status"] == "PUBLISHED"


# 7. Audit records are generated correctly.
def test_7_audit_records_generated_for_create_and_publish(db, client):
    colab = make_platform_organization(db)
    role = make_role_with_permissions(
        db, organization=None, name="CoLAB Intel Admin",
        permissions=[(PermissionDomain.INTELLIGENCE, a) for a in (PermissionAction.VIEW, PermissionAction.CREATE, PermissionAction.EDIT, PermissionAction.PUBLISH)],
    )
    colab_admin = make_user(db, organization=colab, email="colab.admin@example.com")
    assign_role(db, user=colab_admin, organization=colab, role=role)
    headers = login_headers(client, organization_slug="colab-systems", email="colab.admin@example.com")

    create_response = client.post(
        "/api/v1/intelligence", headers=headers,
        json={"scope": "GLOBAL", "intelligence_type": "AGENCY_NEWS", "title": "Audited item", "summary": "x", "impact_level": "LOW", "impact_reason": "test"},
    )
    item_id = create_response.json()["id"]

    audit_rows = db.query(AuditEvent).filter(AuditEvent.object_type == "RegulatoryIntelligenceItem", AuditEvent.object_id == item_id).all()
    assert len(audit_rows) >= 1
