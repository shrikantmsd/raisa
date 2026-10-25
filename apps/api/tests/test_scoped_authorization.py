"""
Cross-layer authorization hardening tests. `authorize()` itself
(app/services/authorization_service.py) is UNCHANGED — its scope
ancestor-walk already existed and is exercised here through the Layer
2/3 resources that previously never passed a scope_id into it at all.
"""
import uuid

from app.models.ctd import CTDModule, CTDSection, DocumentCTDPlacement
from app.models.document import Document
from app.models.intelligence import IntelligenceScope, IntelligenceStatus
from app.models.rbac import PermissionAction, PermissionDomain, ScopeType
from app.models.regulatory_structure import Product

from tests.conftest import (
    assign_role,
    login_headers,
    make_authority,
    make_dossier,
    make_distribution,
    make_intelligence_item,
    make_organization,
    make_platform_organization,
    make_regulatory_application,
    make_role_with_permissions,
    make_scope,
    make_user,
)


def _make_product(db, *, organization, scope_id=None, name="Test Product"):
    product = Product(organization_id=organization.id, scope_id=scope_id, name=name)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def _full_role(db, domain, extra_name=""):
    return make_role_with_permissions(
        db, organization=None, name=f"Full {domain.value} {extra_name}", permissions=[(domain, a) for a in PermissionAction]
    )


# --- 1-4: the exact scenarios named in the request ---------------------

def test_scoped_user_can_access_resource_within_scope(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = _full_role(db, PermissionDomain.PRODUCT)
    india = make_scope(db, organization=org, label="Product ABC / India", scope_type=ScopeType.MARKET)
    user = make_user(db, organization=org, email="specialist@acme.example")
    assign_role(db, user=user, organization=org, role=role, scope=india)
    product = _make_product(db, organization=org, scope_id=india.id, name="Product ABC")

    headers = login_headers(client, organization_slug="acme", email="specialist@acme.example")
    response = client.get(f"/api/v1/products/{product.id}", headers=headers)
    assert response.status_code == 200


def test_scoped_user_denied_unrelated_product(db, client):
    """'Product ABC / India scope -> denied Product XYZ'."""
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = _full_role(db, PermissionDomain.PRODUCT)
    india = make_scope(db, organization=org, label="Product ABC / India", scope_type=ScopeType.MARKET)
    xyz_scope = make_scope(db, organization=org, label="Product XYZ", scope_type=ScopeType.PRODUCT)
    user = make_user(db, organization=org, email="specialist@acme.example")
    assign_role(db, user=user, organization=org, role=role, scope=india)
    product_xyz = _make_product(db, organization=org, scope_id=xyz_scope.id, name="Product XYZ")

    headers = login_headers(client, organization_slug="acme", email="specialist@acme.example")
    assert client.get(f"/api/v1/products/{product_xyz.id}", headers=headers).status_code == 404
    assert all(p["id"] != str(product_xyz.id) for p in client.get("/api/v1/products", headers=headers).json())


def test_scoped_user_denied_sibling_scope_same_product_different_country(db, client):
    """'Product ABC / India scope -> denied Product ABC / another
    unauthorized country where country scope applies' — two MARKET
    scopes sharing the same PRODUCT parent must not authorize each
    other."""
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = _full_role(db, PermissionDomain.PRODUCT)
    product_scope = make_scope(db, organization=org, label="Product ABC", scope_type=ScopeType.PRODUCT)
    india = make_scope(db, organization=org, label="Product ABC / India", scope_type=ScopeType.MARKET, parent=product_scope)
    japan = make_scope(db, organization=org, label="Product ABC / Japan", scope_type=ScopeType.MARKET, parent=product_scope)
    user = make_user(db, organization=org, email="specialist@acme.example")
    assign_role(db, user=user, organization=org, role=role, scope=india)
    product_japan = _make_product(db, organization=org, scope_id=japan.id, name="ABC Japan filing")

    headers = login_headers(client, organization_slug="acme", email="specialist@acme.example")
    assert client.get(f"/api/v1/products/{product_japan.id}", headers=headers).status_code == 404


def test_broader_scope_grant_authorizes_descendant_scope(db, client):
    """A role held at 'Product ABC' (parent) reaches both
    'Product ABC / India' and 'Product ABC / Japan' (children)."""
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = _full_role(db, PermissionDomain.PRODUCT)
    product_scope = make_scope(db, organization=org, label="Product ABC", scope_type=ScopeType.PRODUCT)
    india = make_scope(db, organization=org, label="Product ABC / India", scope_type=ScopeType.MARKET, parent=product_scope)
    japan = make_scope(db, organization=org, label="Product ABC / Japan", scope_type=ScopeType.MARKET, parent=product_scope)
    user = make_user(db, organization=org, email="manager@acme.example")
    assign_role(db, user=user, organization=org, role=role, scope=product_scope)
    product_india = _make_product(db, organization=org, scope_id=india.id, name="ABC India")
    product_japan = _make_product(db, organization=org, scope_id=japan.id, name="ABC Japan")

    headers = login_headers(client, organization_slug="acme", email="manager@acme.example")
    assert client.get(f"/api/v1/products/{product_india.id}", headers=headers).status_code == 200
    assert client.get(f"/api/v1/products/{product_japan.id}", headers=headers).status_code == 200


def test_organization_wide_role_retains_existing_behavior(db, client):
    """'Organization-wide role -> retains existing organization-wide
    behavior' — the regression this whole pass must not break."""
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = _full_role(db, PermissionDomain.PRODUCT)
    scope_a = make_scope(db, organization=org, label="Product A", scope_type=ScopeType.PRODUCT)
    scope_b = make_scope(db, organization=org, label="Product B", scope_type=ScopeType.PRODUCT)
    user = make_user(db, organization=org, email="admin@acme.example")
    assign_role(db, user=user, organization=org, role=role)  # no scope = org-wide, unchanged
    product_a = _make_product(db, organization=org, scope_id=scope_a.id, name="A")
    product_b = _make_product(db, organization=org, scope_id=scope_b.id, name="B")
    product_unscoped = _make_product(db, organization=org, scope_id=None, name="Unscoped")

    headers = login_headers(client, organization_slug="acme", email="admin@acme.example")
    for p in (product_a, product_b, product_unscoped):
        assert client.get(f"/api/v1/products/{p.id}", headers=headers).status_code == 200
    ids = {p["id"] for p in client.get("/api/v1/products", headers=headers).json()}
    assert {str(product_a.id), str(product_b.id), str(product_unscoped.id)} <= ids


def test_scoped_only_user_denied_unscoped_organization_wide_resource(db):
    """Documents the deliberate design choice: an org-wide resource
    (scope_id=None) is not implicitly "inside" a narrow scope just
    because nothing more specific was asked for — a scoped assignment
    authorizes only what is IN its scope."""
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = _full_role(db, PermissionDomain.PRODUCT)
    scope = make_scope(db, organization=org, label="Product ABC / India", scope_type=ScopeType.MARKET)
    user = make_user(db, organization=org, email="specialist@acme.example")
    assign_role(db, user=user, organization=org, role=role, scope=scope)
    unscoped_product = _make_product(db, organization=org, scope_id=None)

    from app.services.authorization_service import authorize

    decision = authorize(db=db, user_id=user.id, organization_id=org.id, domain=PermissionDomain.PRODUCT, action=PermissionAction.VIEW, scope_id=unscoped_product.scope_id)
    assert decision.allowed is False


# --- creation: scope must belong to the caller's own org ----------------

def test_cannot_create_resource_with_another_orgs_scope(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    other_org = make_organization(db, name="Other Pharma", slug="other")
    role = _full_role(db, PermissionDomain.PRODUCT)
    user = make_user(db, organization=org, email="user@acme.example")
    assign_role(db, user=user, organization=org, role=role)
    foreign_scope = make_scope(db, organization=other_org, label="Someone else's scope")

    headers = login_headers(client, organization_slug="acme", email="user@acme.example")
    response = client.post("/api/v1/products", headers=headers, json={"name": "Injected", "scope_id": str(foreign_scope.id)})
    assert response.status_code == 400


def test_create_with_own_scope_binds_the_resource(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = _full_role(db, PermissionDomain.PRODUCT)
    scope = make_scope(db, organization=org, label="Product ABC / India", scope_type=ScopeType.MARKET)
    user = make_user(db, organization=org, email="specialist@acme.example")
    assign_role(db, user=user, organization=org, role=role, scope=scope)

    headers = login_headers(client, organization_slug="acme", email="specialist@acme.example")
    response = client.post("/api/v1/products", headers=headers, json={"name": "New Product", "scope_id": str(scope.id)})
    assert response.status_code == 201
    assert response.json()["scope_id"] == str(scope.id)


def test_scoped_user_cannot_create_outside_their_own_scope(db, client):
    """A user scoped to India cannot claim scope=Japan on creation just
    because they hold the CREATE action somewhere."""
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = _full_role(db, PermissionDomain.PRODUCT)
    product_scope = make_scope(db, organization=org, label="Product ABC", scope_type=ScopeType.PRODUCT)
    india = make_scope(db, organization=org, label="Product ABC / India", scope_type=ScopeType.MARKET, parent=product_scope)
    japan = make_scope(db, organization=org, label="Product ABC / Japan", scope_type=ScopeType.MARKET, parent=product_scope)
    user = make_user(db, organization=org, email="specialist@acme.example")
    assign_role(db, user=user, organization=org, role=role, scope=india)

    headers = login_headers(client, organization_slug="acme", email="specialist@acme.example")
    assert client.post("/api/v1/products", headers=headers, json={"name": "x", "scope_id": str(japan.id)}).status_code == 403
    assert client.post("/api/v1/products", headers=headers, json={"name": "x", "scope_id": str(india.id)}).status_code == 201


# --- Dossier, Application, Activity (the other named resource types) ---

def test_dossier_scope_enforcement_including_transition(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    dossier_role = make_role_with_permissions(
        db, organization=None, name="Scoped Dossier Editor",
        permissions=[(PermissionDomain.DOSSIER, a) for a in (PermissionAction.VIEW, PermissionAction.EDIT)],
    )
    india = make_scope(db, organization=org, label="Product ABC / India", scope_type=ScopeType.MARKET)
    japan = make_scope(db, organization=org, label="Product ABC / Japan", scope_type=ScopeType.MARKET)
    user = make_user(db, organization=org, email="specialist@acme.example")
    assign_role(db, user=user, organization=org, role=dossier_role, scope=india)

    authority = make_authority(db)
    product = _make_product(db, organization=org, scope_id=india.id)
    application = make_regulatory_application(db, organization=org, product=product, authority=authority)
    in_scope_dossier = make_dossier(db, organization=org, product=product, application=application, authority=authority, owner=user)
    in_scope_dossier.scope_id = india.id
    out_of_scope_dossier = make_dossier(db, organization=org, product=product, application=application, authority=authority, owner=user)
    out_of_scope_dossier.scope_id = japan.id
    db.commit()

    headers = login_headers(client, organization_slug="acme", email="specialist@acme.example")
    assert client.get(f"/api/v1/dossiers/{in_scope_dossier.id}", headers=headers).status_code == 200
    assert client.get(f"/api/v1/dossiers/{out_of_scope_dossier.id}", headers=headers).status_code == 404
    assert client.post(f"/api/v1/dossiers/{in_scope_dossier.id}/transition", headers=headers, json={"new_status": "UNDER_REVIEW"}).status_code == 200
    assert client.post(f"/api/v1/dossiers/{out_of_scope_dossier.id}/transition", headers=headers, json={"new_status": "UNDER_REVIEW"}).status_code == 404


def test_application_scope_enforcement(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = _full_role(db, PermissionDomain.APPLICATION)
    india = make_scope(db, organization=org, label="Product ABC / India", scope_type=ScopeType.MARKET)
    other_scope = make_scope(db, organization=org, label="Product XYZ", scope_type=ScopeType.PRODUCT)
    user = make_user(db, organization=org, email="specialist@acme.example")
    assign_role(db, user=user, organization=org, role=role, scope=india)
    authority = make_authority(db)
    product = _make_product(db, organization=org, scope_id=india.id)
    in_scope_app = make_regulatory_application(db, organization=org, product=product, authority=authority)
    in_scope_app.scope_id = india.id
    other_product = _make_product(db, organization=org, scope_id=other_scope.id, name="XYZ")
    out_of_scope_app = make_regulatory_application(db, organization=org, product=other_product, authority=authority)
    out_of_scope_app.scope_id = other_scope.id
    db.commit()

    headers = login_headers(client, organization_slug="acme", email="specialist@acme.example")
    assert client.get(f"/api/v1/applications/{in_scope_app.id}", headers=headers).status_code == 200
    assert client.get(f"/api/v1/applications/{out_of_scope_app.id}", headers=headers).status_code == 404


def test_activity_scope_enforcement(db, client):
    from app.services import dossier_service

    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = _full_role(db, PermissionDomain.ACTIVITY)
    india = make_scope(db, organization=org, label="Product ABC / India", scope_type=ScopeType.MARKET)
    other_scope = make_scope(db, organization=org, label="Product XYZ", scope_type=ScopeType.PRODUCT)
    user = make_user(db, organization=org, email="specialist@acme.example")
    assign_role(db, user=user, organization=org, role=role, scope=india)
    authority = make_authority(db)
    product = _make_product(db, organization=org, scope_id=india.id)

    in_scope = dossier_service.create_regulatory_activity(
        db, organization_id=org.id, actor_id=user.id, product_id=product.id, authority_id=authority.id,
        activity_type="INITIAL_SUBMISSION", scope_id=india.id,
    )
    # Created directly (not through the service) on purpose: a specialist
    # scoped to India legitimately CANNOT create an activity in a scope
    # they don't hold -- that permission boundary is covered by
    # test_scoped_user_cannot_create_outside_their_own_scope. This test
    # is about LIST filtering once such an activity already exists (e.g.
    # created by an org-wide admin).
    from app.models.regulatory_activity import RegulatoryActivity, RegulatoryActivityType, RegulatoryActivityStatus
    out_of_scope = RegulatoryActivity(
        organization_id=org.id, scope_id=other_scope.id, product_id=product.id, authority_id=authority.id,
        activity_type=RegulatoryActivityType.INITIAL_SUBMISSION, status=RegulatoryActivityStatus.PLANNED,
    )
    db.add(out_of_scope); db.commit(); db.refresh(out_of_scope)

    headers = login_headers(client, organization_slug="acme", email="specialist@acme.example")
    ids = {a["id"] for a in client.get("/api/v1/activities", headers=headers).json()}
    assert str(in_scope.id) in ids
    assert str(out_of_scope.id) not in ids


def test_document_ctd_placement_uses_the_dossiers_scope(db, client):
    """CTD Module/Section are global reference data with no scope of
    their own (spec Layer 3 hardening note) — placement is gated by the
    DOSSIER's scope, not a scope on the CTD structure."""
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = make_role_with_permissions(
        db, organization=None, name="Scoped Editor", permissions=[(PermissionDomain.DOSSIER, a) for a in (PermissionAction.VIEW, PermissionAction.EDIT)],
    )
    india = make_scope(db, organization=org, label="Product ABC / India", scope_type=ScopeType.MARKET)
    japan = make_scope(db, organization=org, label="Product ABC / Japan", scope_type=ScopeType.MARKET)
    user = make_user(db, organization=org, email="specialist@acme.example")
    assign_role(db, user=user, organization=org, role=role, scope=india)

    authority = make_authority(db)
    product = _make_product(db, organization=org, scope_id=india.id)
    application = make_regulatory_application(db, organization=org, product=product, authority=authority)
    in_scope_dossier = make_dossier(db, organization=org, product=product, application=application, authority=authority, owner=user)
    in_scope_dossier.scope_id = india.id
    out_of_scope_dossier = make_dossier(db, organization=org, product=product, application=application, authority=authority, owner=user)
    out_of_scope_dossier.scope_id = japan.id
    db.commit()

    module = db.query(CTDModule).first() or CTDModule(code="MODULE_2", title="CTD Summaries", display_order=2)
    if module.id is None:
        db.add(module); db.commit(); db.refresh(module)
    section = CTDSection(module_id=module.id, section_code="2.3", title="QOS", display_order=1)
    db.add(section); db.commit(); db.refresh(section)
    document = Document(organization_id=org.id, file_name="f.pdf", mime_type="application/pdf", owner_id=user.id)
    db.add(document); db.commit(); db.refresh(document)

    headers = login_headers(client, organization_slug="acme", email="specialist@acme.example")
    ok = client.post(f"/api/v1/dossiers/{in_scope_dossier.id}/documents", headers=headers, json={"document_id": str(document.id), "ctd_section_id": str(section.id)})
    assert ok.status_code == 201
    denied = client.post(f"/api/v1/dossiers/{out_of_scope_dossier.id}/documents", headers=headers, json={"document_id": str(document.id), "ctd_section_id": str(section.id)})
    assert denied.status_code == 404  # out-of-scope dossier reads as not-found, same as get_dossier


# --- Intelligence: scope enforcement AND the global-distribution exemption ---

def test_intelligence_scope_enforcement(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = make_role_with_permissions(db, organization=None, name="Scoped Intel", permissions=[(PermissionDomain.INTELLIGENCE, a) for a in (PermissionAction.VIEW, PermissionAction.CREATE)])
    india = make_scope(db, organization=org, label="Product ABC / India", scope_type=ScopeType.MARKET)
    japan = make_scope(db, organization=org, label="Product ABC / Japan", scope_type=ScopeType.MARKET)
    user = make_user(db, organization=org, email="specialist@acme.example")
    assign_role(db, user=user, organization=org, role=role, scope=india)

    headers = login_headers(client, organization_slug="acme", email="specialist@acme.example")
    in_scope = client.post("/api/v1/intelligence", headers=headers, json={
        "scope": "TENANT", "intelligence_type": "REGULATORY_CHANGE", "title": "in scope", "summary": "x",
        "impact_level": "LOW", "impact_reason": "x", "scope_id": str(india.id),
    })
    assert in_scope.status_code == 201

    out_of_scope_item = make_intelligence_item(db, organization=org, creator=user, scope=IntelligenceScope.TENANT, status=IntelligenceStatus.PUBLISHED)
    out_of_scope_item.scope_id = japan.id
    db.commit()
    assert client.get(f"/api/v1/intelligence/{out_of_scope_item.id}", headers=headers).status_code == 404
    ids = {i["id"] for i in client.get("/api/v1/intelligence", headers=headers).json()}
    assert str(out_of_scope_item.id) not in ids
    assert in_scope.json()["id"] in ids


def test_distributed_global_intelligence_still_visible_to_scoped_only_customer_user(db, client):
    """CRITICAL regression: a customer whose ONLY assignment is scoped
    must still see a distributed GLOBAL item, because a CoLAB-internal
    scope_id (if any) is not comparable to the customer's own scope
    tree — visibility of foreign-org rows must remain governed purely by
    the distribution+published rule, never narrowed by scope."""
    colab = make_platform_organization(db)
    customer = make_organization(db, name="Acme Pharma", slug="acme")
    india = make_scope(db, organization=customer, label="Product ABC / India", scope_type=ScopeType.MARKET)
    role = make_role_with_permissions(db, organization=None, name="Scoped Intel Viewer", permissions=[(PermissionDomain.INTELLIGENCE, PermissionAction.VIEW)])
    user = make_user(db, organization=customer, email="specialist@acme.example")
    assign_role(db, user=user, organization=customer, role=role, scope=india)

    colab_admin = make_user(db, organization=colab, email="colab.admin@example.com")
    # Give the GLOBAL item a scope_id in COLAB's own (unrelated) scope
    # tree, specifically to prove it doesn't collide with the customer's.
    colab_scope = make_scope(db, organization=colab, label="Internal CoLAB grouping")
    global_item = make_intelligence_item(db, organization=colab, creator=colab_admin, scope=IntelligenceScope.GLOBAL, status=IntelligenceStatus.PUBLISHED)
    global_item.scope_id = colab_scope.id
    db.commit()
    make_distribution(db, item=global_item, organization=customer, actor=colab_admin)

    headers = login_headers(client, organization_slug="acme", email="specialist@acme.example")
    assert client.get(f"/api/v1/intelligence/{global_item.id}", headers=headers).status_code == 200
    ids = {i["id"] for i in client.get("/api/v1/intelligence", headers=headers).json()}
    assert str(global_item.id) in ids
