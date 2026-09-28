"""
Layer 2 spec §27.R / §32.18 — MANDATORY:
"At least one automated test MUST prove that a user from Tenant A
cannot access a Dossier belonging to Tenant B."
"""
import uuid

from app.models.rbac import PermissionAction, PermissionDomain

from tests.conftest import (
    assign_role,
    login_headers,
    make_dossier_chain,
    make_organization,
    make_role_with_permissions,
    make_user,
)


def _viewer_role(db):
    return make_role_with_permissions(
        db,
        organization=None,
        name="Dossier Viewer",
        permissions=[
            (PermissionDomain.DOSSIER, PermissionAction.VIEW),
            (PermissionDomain.PRODUCT, PermissionAction.VIEW),
            (PermissionDomain.APPLICATION, PermissionAction.VIEW),
        ],
    )


def test_tenant_a_cannot_fetch_tenant_b_dossier(db, client):
    """THE mandatory test."""
    tenant_a = make_organization(db, name="Tenant A Pharma", slug="tenant-a")
    tenant_b = make_organization(db, name="Tenant B Pharma", slug="tenant-b")
    role = _viewer_role(db)

    user_a = make_user(db, organization=tenant_a, email="ra@tenant-a.example")
    assign_role(db, user=user_a, organization=tenant_a, role=role)

    user_b = make_user(db, organization=tenant_b, email="ra@tenant-b.example")
    assign_role(db, user=user_b, organization=tenant_b, role=role)
    _, _, dossier_b = make_dossier_chain(db, organization=tenant_b, owner=user_b)

    headers_a = login_headers(client, organization_slug="tenant-a", email="ra@tenant-a.example")

    # Direct fetch by id — never the record, never a 403 that would leak
    # that the id exists somewhere.
    response = client.get(f"/api/v1/dossiers/{dossier_b.id}", headers=headers_a)
    assert response.status_code == 404

    # And it never shows up in Tenant A's own list either.
    _, _, dossier_a = make_dossier_chain(db, organization=tenant_a, owner=user_a)
    list_response = client.get("/api/v1/dossiers", headers=headers_a)
    assert list_response.status_code == 200
    returned_ids = {d["id"] for d in list_response.json()}
    assert str(dossier_a.id) in returned_ids
    assert str(dossier_b.id) not in returned_ids


def test_tenant_a_cannot_transition_tenant_bs_dossier(db, client):
    """Isolation must hold for writes, not just reads."""
    tenant_a = make_organization(db, name="Tenant A Pharma", slug="tenant-a")
    tenant_b = make_organization(db, name="Tenant B Pharma", slug="tenant-b")
    role = make_role_with_permissions(
        db, organization=None, name="Dossier Admin",
        permissions=[(PermissionDomain.DOSSIER, a) for a in (PermissionAction.VIEW, PermissionAction.EDIT, PermissionAction.APPROVE)],
    )

    user_a = make_user(db, organization=tenant_a, email="admin@tenant-a.example")
    assign_role(db, user=user_a, organization=tenant_a, role=role)
    user_b = make_user(db, organization=tenant_b, email="admin@tenant-b.example")
    _, _, dossier_b = make_dossier_chain(db, organization=tenant_b, owner=user_b)

    headers_a = login_headers(client, organization_slug="tenant-a", email="admin@tenant-a.example")

    response = client.post(
        f"/api/v1/dossiers/{dossier_b.id}/transition", headers=headers_a, json={"new_status": "UNDER_REVIEW"}
    )
    assert response.status_code == 404


def test_tenant_a_cannot_see_tenant_b_products_or_applications(db, client):
    tenant_a = make_organization(db, name="Tenant A Pharma", slug="tenant-a")
    tenant_b = make_organization(db, name="Tenant B Pharma", slug="tenant-b")
    role = _viewer_role(db)

    user_a = make_user(db, organization=tenant_a, email="ra@tenant-a.example")
    assign_role(db, user=user_a, organization=tenant_a, role=role)
    user_b = make_user(db, organization=tenant_b, email="ra@tenant-b.example")
    product_b, application_b, _ = make_dossier_chain(db, organization=tenant_b, owner=user_b)

    headers_a = login_headers(client, organization_slug="tenant-a", email="ra@tenant-a.example")

    products = client.get("/api/v1/products", headers=headers_a).json()
    assert all(p["id"] != str(product_b.id) for p in products)

    app_response = client.get(f"/api/v1/applications/{application_b.id}", headers=headers_a)
    assert app_response.status_code == 404
