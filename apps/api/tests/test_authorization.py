"""
Spec §55 — also-mandatory tests:
"User without APPROVE permission cannot perform an approval action."
"System Admin cannot automatically access restricted scientific content."
"""
from datetime import datetime, timedelta, timezone

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import seed as seed_module  # the actual shipped seed script, spec §56-57

from app.models.rbac import PermissionAction, PermissionDomain, ResourceState, SoDPolicy
from app.models.user import UserStatus
from app.services.authorization_service import authorize

from tests.conftest import (
    assign_role,
    get_or_create_permission,
    login_headers,
    make_organization,
    make_role_with_permissions,
    make_user,
)


def test_user_without_approve_permission_is_denied(db):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    editor_role = make_role_with_permissions(
        db, organization=None, name="Editor Only", permissions=[(PermissionDomain.DOCUMENT, PermissionAction.EDIT)]
    )
    # DOCUMENT_APPROVE exists as reference data (spec §18 — permissions
    # are seeded independently of which roles get granted them) even
    # though no role here grants it.
    get_or_create_permission(db, domain=PermissionDomain.DOCUMENT, action=PermissionAction.APPROVE)
    user = make_user(db, organization=org, email="editor@acme.example")
    assign_role(db, user=user, organization=org, role=editor_role)

    decision = authorize(
        db=db,
        user_id=user.id,
        organization_id=org.id,
        domain=PermissionDomain.DOCUMENT,
        action=PermissionAction.APPROVE,
    )
    assert decision.allowed is False
    assert decision.policy == "RBAC"


def test_user_with_approve_permission_is_allowed(db):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    approver_role = make_role_with_permissions(
        db, organization=None, name="Approver", permissions=[(PermissionDomain.DOCUMENT, PermissionAction.APPROVE)]
    )
    user = make_user(db, organization=org, email="approver@acme.example")
    assign_role(db, user=user, organization=org, role=approver_role)

    decision = authorize(
        db=db,
        user_id=user.id,
        organization_id=org.id,
        domain=PermissionDomain.DOCUMENT,
        action=PermissionAction.APPROVE,
    )
    assert decision.allowed is True


def test_access_preview_endpoint_reports_denied(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    viewer_role = make_role_with_permissions(
        db, organization=None, name="Viewer Only", permissions=[(PermissionDomain.DOCUMENT, PermissionAction.VIEW)]
    )
    get_or_create_permission(db, domain=PermissionDomain.DOCUMENT, action=PermissionAction.APPROVE)
    user_row = make_user(db, organization=org, email="viewer@acme.example")
    assign_role(db, user=user_row, organization=org, role=viewer_role)

    headers = login_headers(client, organization_slug="acme", email="viewer@acme.example")
    response = client.post(
        "/api/v1/access/preview",
        headers=headers,
        json={"domain": "DOCUMENT", "action": "APPROVE"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is False
    assert body["policy"] == "RBAC"


def test_seeded_system_administrator_cannot_view_documents(db):
    """Proves the actual shipped seed.py configuration (spec §16):
    "System Administrator should NOT automatically receive scientific
    or dossier-content permissions."
    """
    org = make_organization(db, name="Acme Pharma", slug="acme")
    perms = seed_module.seed_permissions(db)
    platform_roles = seed_module.seed_platform_roles(db, perms)
    system_admin_role = platform_roles["SYSTEM_ADMINISTRATOR"]

    user = make_user(db, organization=org, email="sysadmin@acme.example")
    assign_role(db, user=user, organization=org, role=system_admin_role)

    decision = authorize(
        db=db, user_id=user.id, organization_id=org.id, domain=PermissionDomain.DOCUMENT, action=PermissionAction.VIEW
    )
    assert decision.allowed is False

    # Meanwhile the same role legitimately administers users — this is
    # a scoping assertion, not "System Administrator can do nothing".
    decision_user_admin = authorize(
        db=db,
        user_id=user.id,
        organization_id=org.id,
        domain=PermissionDomain.USER,
        action=PermissionAction.ADMINISTER,
    )
    assert decision_user_admin.allowed is True


def test_edit_denied_on_approved_resource_state(db):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    editor_role = make_role_with_permissions(
        db, organization=None, name="Editor", permissions=[(PermissionDomain.DOCUMENT, PermissionAction.EDIT)]
    )
    user = make_user(db, organization=org, email="editor@acme.example")
    assign_role(db, user=user, organization=org, role=editor_role)

    draft_decision = authorize(
        db=db,
        user_id=user.id,
        organization_id=org.id,
        domain=PermissionDomain.DOCUMENT,
        action=PermissionAction.EDIT,
        resource_state=ResourceState.DRAFT,
    )
    assert draft_decision.allowed is True

    approved_decision = authorize(
        db=db,
        user_id=user.id,
        organization_id=org.id,
        domain=PermissionDomain.DOCUMENT,
        action=PermissionAction.EDIT,
        resource_state=ResourceState.APPROVED,
    )
    assert approved_decision.allowed is False
    assert approved_decision.policy == "RESOURCE_STATE"


def test_segregation_of_duties_author_cannot_approve_own_document(db):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    approver_role = make_role_with_permissions(
        db, organization=None, name="Approver", permissions=[(PermissionDomain.DOCUMENT, PermissionAction.APPROVE)]
    )
    user = make_user(db, organization=org, email="author-approver@acme.example")
    assign_role(db, user=user, organization=org, role=approver_role)

    db.add(
        SoDPolicy(
            organization_id=None,
            name="Author cannot be final approver",
            action_a=PermissionAction.CREATE,
            action_b=PermissionAction.APPROVE,
            active=True,
        )
    )
    db.commit()

    decision = authorize(
        db=db,
        user_id=user.id,
        organization_id=org.id,
        domain=PermissionDomain.DOCUMENT,
        action=PermissionAction.APPROVE,
        resource_owner_id=user.id,  # this user authored the resource
    )
    assert decision.allowed is False
    assert decision.policy == "SOD"


def test_expired_consultant_access_is_denied(db):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = make_role_with_permissions(
        db, organization=None, name="Consultant", permissions=[(PermissionDomain.DOCUMENT, PermissionAction.VIEW)]
    )
    user = make_user(db, organization=org, email="consultant@example.com")
    user.valid_from = datetime.now(timezone.utc) - timedelta(days=30)
    user.valid_until = datetime.now(timezone.utc) - timedelta(days=1)  # expired yesterday
    db.commit()
    assign_role(db, user=user, organization=org, role=role)

    decision = authorize(
        db=db, user_id=user.id, organization_id=org.id, domain=PermissionDomain.DOCUMENT, action=PermissionAction.VIEW
    )
    assert decision.allowed is False
    assert decision.policy == "TIME_BOUNDED_ACCESS"


def test_suspended_user_is_denied_even_with_a_valid_role(db):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = make_role_with_permissions(
        db, organization=None, name="Viewer", permissions=[(PermissionDomain.DOCUMENT, PermissionAction.VIEW)]
    )
    user = make_user(db, organization=org, email="suspended@acme.example", status=UserStatus.SUSPENDED)
    assign_role(db, user=user, organization=org, role=role)

    decision = authorize(
        db=db, user_id=user.id, organization_id=org.id, domain=PermissionDomain.DOCUMENT, action=PermissionAction.VIEW
    )
    assert decision.allowed is False
    assert decision.policy == "USER_STATUS"
