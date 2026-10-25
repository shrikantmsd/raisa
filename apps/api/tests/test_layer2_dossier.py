"""
Layer 2 spec §27.B/E/N — RBAC and dossier lifecycle.
"""
from app.models.audit import AuditEvent, AuditEventType
from app.models.dossier import Dossier, DossierStatus
from app.models.rbac import PermissionAction, PermissionDomain
from app.models.regulatory_activity import RegulatoryEvent, RegulatoryEventType

from tests.conftest import (
    assign_role,
    login_headers,
    make_authority,
    make_dossier,
    make_dossier_chain,
    make_organization,
    make_product,
    make_regulatory_application,
    make_role_with_permissions,
    make_user,
)


def test_create_dossier_requires_create_permission(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    no_perms_role = make_role_with_permissions(db, organization=None, name="No Access", permissions=[])
    user = make_user(db, organization=org, email="nobody@acme.example")
    assign_role(db, user=user, organization=org, role=no_perms_role)
    authority = make_authority(db)
    product = make_product(db, organization=org)
    application = make_regulatory_application(db, organization=org, product=product, authority=authority)

    headers = login_headers(client, organization_slug="acme", email="nobody@acme.example")
    response = client.post(
        "/api/v1/dossiers",
        headers=headers,
        json={
            "product_id": str(product.id),
            "regulatory_application_id": str(application.id),
            "authority_id": str(authority.id),
            "region": "US",
            "standard_version": "4.0",
        },
    )
    assert response.status_code == 403


def test_create_dossier_succeeds_and_is_draft_and_audited(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = make_role_with_permissions(
        db, organization=None, name="Dossier Creator", permissions=[(PermissionDomain.DOSSIER, PermissionAction.CREATE)]
    )
    user = make_user(db, organization=org, email="creator@acme.example")
    assign_role(db, user=user, organization=org, role=role)
    authority = make_authority(db)
    product = make_product(db, organization=org)
    application = make_regulatory_application(db, organization=org, product=product, authority=authority)

    headers = login_headers(client, organization_slug="acme", email="creator@acme.example")
    response = client.post(
        "/api/v1/dossiers",
        headers=headers,
        json={
            "product_id": str(product.id),
            "regulatory_application_id": str(application.id),
            "authority_id": str(authority.id),
            "region": "US",
            "standard_version": "4.0",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "DRAFT"

    dossier_id = body["id"]
    audit_rows = db.query(AuditEvent).filter(AuditEvent.object_type == "Dossier", AuditEvent.object_id == dossier_id).all()
    assert any(a.event_type == AuditEventType.USER_CREATED for a in audit_rows)

    event_rows = db.query(RegulatoryEvent).filter(RegulatoryEvent.dossier_id == dossier_id).all()
    assert any(e.event_type == RegulatoryEventType.DOSSIER_CREATED for e in event_rows)


def test_editor_can_submit_draft_for_review_but_not_approve_it(db, client):
    """Spec §4/§20: EDIT gets you to UNDER_REVIEW; it does NOT get you to
    ACTIVE (that's APPROVE)."""
    org = make_organization(db, name="Acme Pharma", slug="acme")
    editor_role = make_role_with_permissions(
        db, organization=None, name="Editor",
        permissions=[(PermissionDomain.DOSSIER, PermissionAction.VIEW), (PermissionDomain.DOSSIER, PermissionAction.EDIT)],
    )
    user = make_user(db, organization=org, email="editor@acme.example")
    assign_role(db, user=user, organization=org, role=editor_role)
    _, _, dossier = make_dossier_chain(db, organization=org, owner=user)

    headers = login_headers(client, organization_slug="acme", email="editor@acme.example")

    to_review = client.post(
        f"/api/v1/dossiers/{dossier.id}/transition", headers=headers, json={"new_status": "UNDER_REVIEW"}
    )
    assert to_review.status_code == 200
    assert to_review.json()["status"] == "UNDER_REVIEW"

    to_active = client.post(f"/api/v1/dossiers/{dossier.id}/transition", headers=headers, json={"new_status": "ACTIVE"})
    assert to_active.status_code == 403


def test_approver_can_activate_and_manager_can_lock(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    manager_role = make_role_with_permissions(
        db, organization=None, name="Manager",
        permissions=[
            (PermissionDomain.DOSSIER, PermissionAction.VIEW),
            (PermissionDomain.DOSSIER, PermissionAction.APPROVE),
            (PermissionDomain.DOSSIER, PermissionAction.PUBLISH),
        ],
    )
    user = make_user(db, organization=org, email="manager@acme.example")
    assign_role(db, user=user, organization=org, role=manager_role)
    _, _, dossier = make_dossier_chain(db, organization=org, owner=user)
    dossier.status = DossierStatus.UNDER_REVIEW
    db.commit()

    headers = login_headers(client, organization_slug="acme", email="manager@acme.example")

    activated = client.post(f"/api/v1/dossiers/{dossier.id}/transition", headers=headers, json={"new_status": "ACTIVE"})
    assert activated.status_code == 200

    locked = client.post(f"/api/v1/dossiers/{dossier.id}/transition", headers=headers, json={"new_status": "LOCKED"})
    assert locked.status_code == 200
    assert locked.json()["status"] == "LOCKED"


def test_cannot_skip_directly_from_draft_to_locked(db, client):
    """Controlled transitions (spec §4/§14) — DRAFT -> LOCKED isn't a
    real edge in the state machine, no matter what permissions the
    caller holds."""
    org = make_organization(db, name="Acme Pharma", slug="acme")
    super_role = make_role_with_permissions(
        db, organization=None, name="Everything",
        permissions=[(PermissionDomain.DOSSIER, a) for a in PermissionAction],
    )
    user = make_user(db, organization=org, email="super@acme.example")
    assign_role(db, user=user, organization=org, role=super_role)
    _, _, dossier = make_dossier_chain(db, organization=org, owner=user)

    headers = login_headers(client, organization_slug="acme", email="super@acme.example")
    response = client.post(f"/api/v1/dossiers/{dossier.id}/transition", headers=headers, json={"new_status": "LOCKED"})
    assert response.status_code == 409


def test_archived_dossier_cannot_transition_further(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = make_role_with_permissions(
        db, organization=None, name="Full",
        permissions=[(PermissionDomain.DOSSIER, a) for a in PermissionAction],
    )
    user = make_user(db, organization=org, email="full@acme.example")
    assign_role(db, user=user, organization=org, role=role)
    _, _, dossier = make_dossier_chain(db, organization=org, owner=user)
    dossier.status = DossierStatus.ARCHIVED
    db.commit()

    headers = login_headers(client, organization_slug="acme", email="full@acme.example")
    response = client.post(f"/api/v1/dossiers/{dossier.id}/transition", headers=headers, json={"new_status": "DRAFT"})
    assert response.status_code == 409
