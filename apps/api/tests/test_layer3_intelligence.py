"""
Layer 3 spec §25 — general functional test coverage.
"""
from app.models.intelligence import IntelligenceScope, IntelligenceStatus
from app.models.rbac import PermissionAction, PermissionDomain

from tests.conftest import (
    assign_role,
    login_headers,
    make_dossier_chain,
    make_intelligence_item,
    make_organization,
    make_platform_organization,
    make_role_with_permissions,
    make_user,
)


def test_create_requires_impact_reason(db, client):
    """Spec §8: impact classification must carry a traceable reason —
    enforced at the schema level (a required field), not optional."""
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = make_role_with_permissions(db, organization=None, name="Creator", permissions=[(PermissionDomain.INTELLIGENCE, PermissionAction.CREATE)])
    user = make_user(db, organization=org, email="creator@acme.example")
    assign_role(db, user=user, organization=org, role=role)
    headers = login_headers(client, organization_slug="acme", email="creator@acme.example")

    response = client.post(
        "/api/v1/intelligence", headers=headers,
        json={"scope": "TENANT", "intelligence_type": "AGENCY_NEWS", "title": "x", "summary": "x", "impact_level": "LOW"},
    )
    assert response.status_code == 422  # impact_reason missing


def test_full_lifecycle_draft_to_published_to_withdrawn_to_review(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = make_role_with_permissions(
        db, organization=None, name="Full",
        permissions=[(PermissionDomain.INTELLIGENCE, a) for a in (PermissionAction.CREATE, PermissionAction.EDIT, PermissionAction.REVIEW, PermissionAction.PUBLISH, PermissionAction.VIEW)],
    )
    user = make_user(db, organization=org, email="user@acme.example")
    assign_role(db, user=user, organization=org, role=role)
    headers = login_headers(client, organization_slug="acme", email="user@acme.example")

    item_id = client.post(
        "/api/v1/intelligence", headers=headers,
        json={"scope": "TENANT", "intelligence_type": "REGULATORY_CHANGE", "title": "x", "summary": "x", "impact_level": "LOW", "impact_reason": "test"},
    ).json()["id"]

    assert client.post(f"/api/v1/intelligence/{item_id}/transition", headers=headers, json={"new_status": "UNDER_REVIEW"}).status_code == 200
    published = client.post(f"/api/v1/intelligence/{item_id}/transition", headers=headers, json={"new_status": "PUBLISHED"})
    assert published.status_code == 200
    withdrawn = client.post(f"/api/v1/intelligence/{item_id}/transition", headers=headers, json={"new_status": "WITHDRAWN"})
    assert withdrawn.status_code == 200
    # WITHDRAWN -> UNDER_REVIEW is the one real way back in (spec §9).
    back_to_review = client.post(f"/api/v1/intelligence/{item_id}/transition", headers=headers, json={"new_status": "UNDER_REVIEW"})
    assert back_to_review.status_code == 200


def test_editor_without_publish_cannot_publish(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = make_role_with_permissions(
        db, organization=None, name="Editor Only",
        permissions=[(PermissionDomain.INTELLIGENCE, a) for a in (PermissionAction.CREATE, PermissionAction.EDIT, PermissionAction.VIEW)],
    )
    user = make_user(db, organization=org, email="editor@acme.example")
    assign_role(db, user=user, organization=org, role=role)
    headers = login_headers(client, organization_slug="acme", email="editor@acme.example")

    item_id = client.post(
        "/api/v1/intelligence", headers=headers,
        json={"scope": "TENANT", "intelligence_type": "REGULATORY_CHANGE", "title": "x", "summary": "x", "impact_level": "LOW", "impact_reason": "test"},
    ).json()["id"]
    client.post(f"/api/v1/intelligence/{item_id}/transition", headers=headers, json={"new_status": "UNDER_REVIEW"})

    response = client.post(f"/api/v1/intelligence/{item_id}/transition", headers=headers, json={"new_status": "PUBLISHED"})
    assert response.status_code == 403


def test_invalid_transition_is_rejected(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = make_role_with_permissions(db, organization=None, name="Full", permissions=[(PermissionDomain.INTELLIGENCE, a) for a in PermissionAction])
    user = make_user(db, organization=org, email="user@acme.example")
    assign_role(db, user=user, organization=org, role=role)
    headers = login_headers(client, organization_slug="acme", email="user@acme.example")

    item_id = client.post(
        "/api/v1/intelligence", headers=headers,
        json={"scope": "TENANT", "intelligence_type": "REGULATORY_CHANGE", "title": "x", "summary": "x", "impact_level": "LOW", "impact_reason": "test"},
    ).json()["id"]

    response = client.post(f"/api/v1/intelligence/{item_id}/transition", headers=headers, json={"new_status": "PUBLISHED"})
    assert response.status_code == 409  # DRAFT -> PUBLISHED skips UNDER_REVIEW


def test_source_registry_is_platform_managed_and_readable_by_all(db, client):
    """Sources are global, CoLAB-managed reference data: the platform org
    can create one; a customer org can't even with the permission; every
    tenant can read the registry."""
    colab = make_platform_organization(db)
    customer = make_organization(db, name="Acme Pharma", slug="acme")
    role = make_role_with_permissions(db, organization=None, name="Source Admin", permissions=[(PermissionDomain.INTELLIGENCE_SOURCE, PermissionAction.CREATE)])

    colab_admin = make_user(db, organization=colab, email="colab.admin@example.com")
    assign_role(db, user=colab_admin, organization=colab, role=role)
    customer_admin = make_user(db, organization=customer, email="admin@acme.example")
    assign_role(db, user=customer_admin, organization=customer, role=role)

    colab_headers = login_headers(client, organization_slug="colab-systems", email="colab.admin@example.com")
    created = client.post("/api/v1/intelligence/sources", headers=colab_headers, json={"name": "Test Source", "source_type": "OTHER"})
    assert created.status_code == 201

    customer_headers = login_headers(client, organization_slug="acme", email="admin@acme.example")
    denied = client.post("/api/v1/intelligence/sources", headers=customer_headers, json={"name": "Injected Source", "source_type": "OTHER"})
    assert denied.status_code == 403

    listing = client.get("/api/v1/intelligence/sources", headers=customer_headers).json()
    names = {s["name"] for s in listing}
    assert "Test Source" in names and "Injected Source" not in names


def test_filtering_by_type_and_impact(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = make_role_with_permissions(db, organization=None, name="Viewer", permissions=[(PermissionDomain.INTELLIGENCE, a) for a in (PermissionAction.VIEW, PermissionAction.CREATE)])
    user = make_user(db, organization=org, email="user@acme.example")
    assign_role(db, user=user, organization=org, role=role)
    make_intelligence_item(db, organization=org, creator=user, intelligence_type="TENDER_ALERT", impact_level="CRITICAL", status=IntelligenceStatus.PUBLISHED, title="Tender A")
    make_intelligence_item(db, organization=org, creator=user, intelligence_type="PHARMA_EVENT", impact_level="LOW", status=IntelligenceStatus.PUBLISHED, title="Event A")

    headers = login_headers(client, organization_slug="acme", email="user@acme.example")
    response = client.get("/api/v1/intelligence?intelligence_type=TENDER_ALERT", headers=headers)
    assert response.status_code == 200
    titles = {i["title"] for i in response.json()}
    assert "Tender A" in titles
    assert "Event A" not in titles


def test_tenant_preferences_roundtrip(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = make_role_with_permissions(
        db, organization=None, name="Config Admin",
        permissions=[(PermissionDomain.INTELLIGENCE_CONFIGURATION, a) for a in (PermissionAction.VIEW, PermissionAction.EDIT)],
    )
    user = make_user(db, organization=org, email="admin@acme.example")
    assign_role(db, user=user, organization=org, role=role)
    headers = login_headers(client, organization_slug="acme", email="admin@acme.example")

    put_response = client.put(
        "/api/v1/intelligence/preferences", headers=headers,
        json={"countries": ["US", "IN"], "authorities": ["FDA"], "therapeutic_areas": ["Oncology"], "intelligence_types": ["TENDER_ALERT"]},
    )
    assert put_response.status_code == 200

    get_response = client.get("/api/v1/intelligence/preferences", headers=headers)
    assert get_response.json()["countries"] == ["US", "IN"]


def test_object_link_rejects_cross_tenant_target(db, client):
    """Spec §14 tenant-safety: a TENANT-scope item cannot link to another
    organization's Dossier."""
    org_a = make_organization(db, name="Tenant A Pharma", slug="tenant-a")
    org_b = make_organization(db, name="Tenant B Pharma", slug="tenant-b")
    role = make_role_with_permissions(
        db, organization=None, name="Full", permissions=[(PermissionDomain.INTELLIGENCE, a) for a in (PermissionAction.CREATE, PermissionAction.EDIT, PermissionAction.VIEW)],
    )
    user_a = make_user(db, organization=org_a, email="ra@tenant-a.example")
    assign_role(db, user=user_a, organization=org_a, role=role)
    user_b = make_user(db, organization=org_b, email="ra@tenant-b.example")
    _, _, dossier_b = make_dossier_chain(db, organization=org_b, owner=user_b)

    item_a = make_intelligence_item(db, organization=org_a, creator=user_a, scope=IntelligenceScope.TENANT)

    headers_a = login_headers(client, organization_slug="tenant-a", email="ra@tenant-a.example")
    response = client.post(
        f"/api/v1/intelligence/{item_a.id}/links", headers=headers_a,
        json={"linked_object_type": "DOSSIER", "linked_object_id": str(dossier_b.id)},
    )
    assert response.status_code == 400


def test_object_link_to_global_ctd_module_is_allowed(db, client):
    """CTD_MODULE has no organization_id — global items may link to it
    without an ownership match."""
    from app.models.ctd import CTDModule

    org = make_organization(db, name="Acme Pharma", slug="acme")
    module = db.query(CTDModule).first()
    if module is None:
        module = CTDModule(code="MODULE_2", title="CTD Summaries", display_order=2)
        db.add(module)
        db.commit()
        db.refresh(module)

    role = make_role_with_permissions(
        db, organization=None, name="Full", permissions=[(PermissionDomain.INTELLIGENCE, a) for a in (PermissionAction.CREATE, PermissionAction.EDIT, PermissionAction.VIEW)],
    )
    user = make_user(db, organization=org, email="user@acme.example")
    assign_role(db, user=user, organization=org, role=role)
    item = make_intelligence_item(db, organization=org, creator=user, scope=IntelligenceScope.TENANT)

    headers = login_headers(client, organization_slug="acme", email="user@acme.example")
    response = client.post(
        f"/api/v1/intelligence/{item.id}/links", headers=headers,
        json={"linked_object_type": "CTD_MODULE", "linked_object_id": str(module.id)},
    )
    assert response.status_code == 201
