"""
Spec §55 — MANDATORY SECURITY TEST:
"Create two tenants. Create users in both. Prove that Tenant A cannot
retrieve Tenant B records."
"""
from app.models.rbac import PermissionAction, PermissionDomain

from tests.conftest import (
    assign_role,
    login_headers,
    make_organization,
    make_role_with_permissions,
    make_user,
)


def test_tenant_a_cannot_list_tenant_b_users(db, client):
    tenant_a = make_organization(db, name="Tenant A Pharma", slug="tenant-a")
    tenant_b = make_organization(db, name="Tenant B Pharma", slug="tenant-b")

    view_users_role = make_role_with_permissions(
        db, organization=None, name="User Viewer", permissions=[(PermissionDomain.USER, PermissionAction.VIEW)]
    )

    user_a = make_user(db, organization=tenant_a, email="admin@tenant-a.example")
    assign_role(db, user=user_a, organization=tenant_a, role=view_users_role)

    user_b1 = make_user(db, organization=tenant_b, email="admin@tenant-b.example")
    make_user(db, organization=tenant_b, email="second-user@tenant-b.example")
    assign_role(db, user=user_b1, organization=tenant_b, role=view_users_role)

    headers_a = login_headers(client, organization_slug="tenant-a", email="admin@tenant-a.example")

    response = client.get("/api/v1/users", headers=headers_a)
    assert response.status_code == 200
    returned_emails = {u["email"] for u in response.json()}

    # Tenant A's own user is visible ...
    assert "admin@tenant-a.example" in returned_emails
    # ... and NOTHING from Tenant B ever appears, no matter how many
    # users Tenant B has.
    assert "admin@tenant-b.example" not in returned_emails
    assert "second-user@tenant-b.example" not in returned_emails
    assert len(returned_emails) == 1


def test_tenant_a_cannot_fetch_tenant_b_user_by_id(db, client):
    tenant_a = make_organization(db, name="Tenant A Pharma", slug="tenant-a")
    tenant_b = make_organization(db, name="Tenant B Pharma", slug="tenant-b")

    view_users_role = make_role_with_permissions(
        db, organization=None, name="User Viewer", permissions=[(PermissionDomain.USER, PermissionAction.VIEW)]
    )

    user_a = make_user(db, organization=tenant_a, email="admin@tenant-a.example")
    assign_role(db, user=user_a, organization=tenant_a, role=view_users_role)
    user_b = make_user(db, organization=tenant_b, email="admin@tenant-b.example")

    headers_a = login_headers(client, organization_slug="tenant-a", email="admin@tenant-a.example")

    # Even knowing Tenant B's user's real UUID, Tenant A gets a 404 —
    # not the record, and not a 403 that would confirm the id exists.
    response = client.get(f"/api/v1/users/{user_b.id}", headers=headers_a)
    assert response.status_code == 404


def test_login_is_scoped_to_the_named_organization(db, client):
    """The same email can exist in two different tenants (external
    consultant scenario, spec §22) as two distinct User rows — logging
    in against tenant-a's slug must never authenticate the tenant-b
    row, even with an identical password.
    """
    tenant_a = make_organization(db, name="Tenant A Pharma", slug="tenant-a")
    tenant_b = make_organization(db, name="Tenant B Pharma", slug="tenant-b")

    make_user(db, organization=tenant_a, email="shared@example.com", password="PasswordA!1")
    make_user(db, organization=tenant_b, email="shared@example.com", password="PasswordB!2")

    # Tenant A's password against Tenant B's slug must fail.
    response = client.post(
        "/api/v1/auth/login",
        json={"organization_slug": "tenant-b", "email": "shared@example.com", "password": "PasswordA!1"},
    )
    assert response.status_code == 401

    # But it succeeds against the organization it actually belongs to.
    response = client.post(
        "/api/v1/auth/login",
        json={"organization_slug": "tenant-a", "email": "shared@example.com", "password": "PasswordA!1"},
    )
    assert response.status_code == 200
