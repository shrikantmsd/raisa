"""
Invariants of the roles `seed.py` ships. These exist because the same
mistake happened twice: a deny-list for System Administrator ("everything
except DOCUMENT_*") silently granted each newly added domain, and an
add-only seed never revoked the old grants in already-seeded databases.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import seed as seed_module

from app.models.rbac import (
    Permission,
    PermissionAction,
    PermissionDomain,
    RolePermission,
    ScopeType,
)
from app.services.authorization_service import authorize

from tests.conftest import assign_role, make_organization, make_role_with_permissions, make_scope, make_user

ALLOWED_DOMAINS = set(seed_module.SYSTEM_ADMIN_ALLOWED)


def _sysadmin_permissions(db, role):
    return (
        db.query(Permission)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .filter(RolePermission.role_id == role.id)
        .all()
    )


def test_system_administrator_holds_only_technical_domains(db):
    perms = seed_module.seed_permissions(db)
    roles = seed_module.seed_platform_roles(db, perms)
    held = _sysadmin_permissions(db, roles["SYSTEM_ADMINISTRATOR"])

    assert held, "System Administrator should still administer users/roles/etc."
    assert {p.domain.value for p in held} <= ALLOWED_DOMAINS
    # Stated the other way, so a future layer that adds a domain fails
    # HERE if someone grants it broadly: every domain outside the
    # allow-list must have zero grants.
    for domain in PermissionDomain:
        if domain.value not in ALLOWED_DOMAINS:
            assert not [p for p in held if p.domain == domain], f"System Administrator must not hold {domain.value}_*"
    # The audit trail is append-only: view is the only action that exists for it.
    assert {p.action for p in held if p.domain == PermissionDomain.AUDIT} == {PermissionAction.VIEW}


def test_reseeding_revokes_stale_system_administrator_grants(db):
    """Simulates a database seeded by an older release that granted
    everything except DOCUMENT_*: re-running the seed must take the
    extras away, not just stop adding them."""
    perms = seed_module.seed_permissions(db)
    roles = seed_module.seed_platform_roles(db, perms)
    sysadmin = roles["SYSTEM_ADMINISTRATOR"]

    for stale_code in ("INTELLIGENCE_VIEW", "SUBMISSION_VIEW", "RESPONSE_VIEW", "AUDIT_DELETE"):
        db.add(RolePermission(role_id=sysadmin.id, permission_id=perms[stale_code].id))
    db.commit()
    assert len(_sysadmin_permissions(db, sysadmin)) > len(ALLOWED_DOMAINS)

    seed_module.seed_platform_roles(db, perms)

    remaining = {p.code for p in _sysadmin_permissions(db, sysadmin)}
    assert not remaining & {"INTELLIGENCE_VIEW", "SUBMISSION_VIEW", "RESPONSE_VIEW", "AUDIT_DELETE"}
    assert "USER_ADMINISTER" in remaining and "AUDIT_VIEW" in remaining  # legitimate grants survive


def test_scoped_only_assignment_does_not_satisfy_unscoped_checks(db):
    """Documents a CURRENT LIMITATION, not a goal: Layer 1's authorize()
    counts a scoped role assignment only for scope-aware checks, and
    Layer 2/3 service checks are org-level (Products/Dossiers/Intelligence
    aren't mapped to Scope nodes yet). So a user whose only assignment is
    scoped — like the seeded demo RA specialist — can't do Layer 2/3
    writes. If resource->scope resolution is built later, this test
    should be updated deliberately."""
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = make_role_with_permissions(
        db, organization=None, name="Intel Contributor",
        permissions=[(PermissionDomain.INTELLIGENCE, PermissionAction.CREATE)],
    )
    scope = make_scope(db, organization=org, label="Product ABC / India", scope_type=ScopeType.MARKET)
    user = make_user(db, organization=org, email="specialist@acme.example")
    assign_role(db, user=user, organization=org, role=role, scope=scope)

    unscoped = authorize(db=db, user_id=user.id, organization_id=org.id, domain=PermissionDomain.INTELLIGENCE, action=PermissionAction.CREATE)
    scoped = authorize(db=db, user_id=user.id, organization_id=org.id, domain=PermissionDomain.INTELLIGENCE, action=PermissionAction.CREATE, scope_id=scope.id)
    assert unscoped.allowed is False
    assert scoped.allowed is True
