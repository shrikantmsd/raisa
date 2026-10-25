import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Point at the test database BEFORE importing app.core.config (its
# Settings are read once and cached).
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://raisa_synapse:devpassword_local_only@localhost:5432/raisa_synapse_test",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.database import Base, get_db  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.organization import Organization, OrganizationStatus  # noqa: E402
from app.models.rbac import (  # noqa: E402
    Permission,
    PermissionAction,
    PermissionDomain,
    Role,
    RoleCategory,
    RolePermission,
    Scope,
    ScopeType,
    UserRoleAssignment,
)
from app.models.user import User, UserStatus  # noqa: E402
# NOTE: do not `import app.models` here — it rebinds the name `app` in
# this module to the *package*, shadowing the `from app.main import app`
# FastAPI instance above. Every model module is already imported
# transitively via `app.main` -> the v1 routers -> `app.models.*`.
import seed as seed_module  # noqa: E402  (the actual shipped seed script)

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(TEST_DATABASE_URL, future=True)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# Tables treated as immutable global reference data for the whole test
# session — seeded once below, excluded from the per-test truncate so
# every Layer 2 test doesn't have to re-seed the CTD registry itself.
# Mirrors production reality: nobody re-seeds these per request either.
# NOTE: standard_versions/regulatory_standards must be excluded too even
# though tests don't read them — ctd_sections.standard_version_id is a
# real FK to standard_versions, and Postgres's TRUNCATE ... CASCADE
# pulls in *any* table with a live FK to a truncated table regardless of
# whether it's in the explicit list, which was silently wiping
# ctd_sections every test until this was added.
_REFERENCE_TABLES = {"regulatory_authorities", "ctd_modules", "ctd_sections", "standard_versions", "regulatory_standards"}


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        authorities = seed_module.seed_regulatory_authorities(session)
        seed_module.seed_ctd_registry(session, authorities)
    finally:
        session.close()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clean_tables():
    """Every test starts from an empty database. Truncating (rather than
    relying on transaction rollback) matches how the app itself uses the
    session — service-layer code calls db.commit() internally, which
    would otherwise defeat a rollback-based isolation strategy."""
    with engine.begin() as conn:
        table_names = ", ".join(
            f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables) if t.name not in _REFERENCE_TABLES
        )
        conn.exec_driver_sql(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE")
    yield


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# --------------------------------------------------------------------
# Data-building helpers (plain functions, not fixtures, so tests can
# call them however many times they need with whatever arguments).
# --------------------------------------------------------------------

def make_organization(db, *, name: str, slug: str) -> Organization:
    org = Organization(name=name, slug=slug, status=OrganizationStatus.ACTIVE)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def make_user(db, *, organization: Organization, email: str, password: str = "Password!123", status=UserStatus.ACTIVE) -> User:
    user = User(
        organization_id=organization.id,
        email=email,
        password_hash=hash_password(password),
        name=email.split("@")[0],
        status=status,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_or_create_permission(db, *, domain: PermissionDomain, action: PermissionAction) -> Permission:
    code = f"{domain.value}_{action.value}"
    perm = db.query(Permission).filter(Permission.code == code).first()
    if perm:
        return perm
    perm = Permission(domain=domain, action=action, code=code)
    db.add(perm)
    db.commit()
    db.refresh(perm)
    return perm


def make_role_with_permissions(
    db, *, organization: Organization | None, name: str, permissions: list[tuple[PermissionDomain, PermissionAction]]
) -> Role:
    role = Role(
        organization_id=organization.id if organization else None,
        code=name.upper().replace(" ", "_"),
        name=name,
        category=RoleCategory.CUSTOM if organization else RoleCategory.PLATFORM,
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    for domain, action in permissions:
        perm = get_or_create_permission(db, domain=domain, action=action)
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.commit()
    return role


def assign_role(db, *, user: User, organization: Organization, role: Role, scope: Scope | None = None) -> UserRoleAssignment:
    assignment = UserRoleAssignment(
        user_id=user.id,
        organization_id=organization.id,
        role_id=role.id,
        scope_id=scope.id if scope else None,
        granted_at=datetime.now(timezone.utc),
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


def make_scope(db, *, organization: Organization, label: str, scope_type: ScopeType = ScopeType.PRODUCT, parent: Scope | None = None) -> Scope:
    scope = Scope(
        organization_id=organization.id,
        scope_type=scope_type,
        label=label,
        parent_id=parent.id if parent else None,
    )
    db.add(scope)
    db.commit()
    db.refresh(scope)
    return scope


def login_headers(client: TestClient, *, organization_slug: str, email: str, password: str = "Password!123") -> dict:
    response = client.post(
        "/api/v1/auth/login",
        json={"organization_slug": organization_slug, "email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------
# Layer 2 helpers (Dossier & CTD Foundation)
# --------------------------------------------------------------------

def make_authority(db, *, short_name: str = "FDA", region: str = "US"):
    from app.models.regulatory_structure import AuthorityType, RegulatoryAuthority

    authority = db.query(RegulatoryAuthority).filter(RegulatoryAuthority.short_name == short_name).first()
    if authority:
        return authority
    authority = RegulatoryAuthority(
        name=f"{short_name} (test)", short_name=short_name, region=region, authority_type=AuthorityType.NATIONAL
    )
    db.add(authority)
    db.commit()
    db.refresh(authority)
    return authority


def make_product(db, *, organization, name: str = "Test Product"):
    from app.models.regulatory_structure import Product

    product = Product(organization_id=organization.id, name=name)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def make_regulatory_application(db, *, organization, product, authority, application_type=None):
    from app.models.regulatory_structure import RegulatoryApplication, RegulatoryApplicationType

    application = RegulatoryApplication(
        organization_id=organization.id,
        product_id=product.id,
        authority_id=authority.id,
        country_region=authority.region,
        application_type=application_type or RegulatoryApplicationType.MARKETING_AUTHORIZATION,
    )
    db.add(application)
    db.commit()
    db.refresh(application)
    return application


def make_dossier(db, *, organization, product, application, authority, owner, status=None):
    from app.models.dossier import Dossier, DossierStatus

    dossier = Dossier(
        organization_id=organization.id,
        product_id=product.id,
        regulatory_application_id=application.id,
        authority_id=authority.id,
        region=authority.region,
        standard_version="4.0",
        status=status or DossierStatus.DRAFT,
        owner_id=owner.id,
    )
    db.add(dossier)
    db.commit()
    db.refresh(dossier)
    return dossier


def make_dossier_chain(db, *, organization, owner, authority=None):
    """One-call convenience: authority + product + application + DRAFT
    dossier, all under the same organization."""
    authority = authority or make_authority(db)
    product = make_product(db, organization=organization)
    application = make_regulatory_application(db, organization=organization, product=product, authority=authority)
    dossier = make_dossier(db, organization=organization, product=product, application=application, authority=authority, owner=owner)
    return product, application, dossier


# --------------------------------------------------------------------
# Layer 3 helpers (Regulatory Intelligence Foundation)
# --------------------------------------------------------------------

def make_platform_organization(db, *, name: str = "CoLAB Systems", slug: str = "colab-systems"):
    from app.models.organization import OrganizationType

    org = db.query(Organization).filter(Organization.slug == slug).first()
    if org:
        return org
    org = Organization(name=name, slug=slug, organization_type=OrganizationType.PLATFORM)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def make_intelligence_item(db, *, organization, creator, scope=None, status=None, impact_level=None, intelligence_type=None, title="Test intelligence item"):
    from app.models.intelligence import ImpactLevel, IntelligenceScope, IntelligenceStatus, IntelligenceType, RegulatoryIntelligenceItem

    item = RegulatoryIntelligenceItem(
        organization_id=organization.id,
        scope=scope or IntelligenceScope.TENANT,
        title=title,
        summary="Test summary",
        intelligence_type=intelligence_type or IntelligenceType.REGULATORY_GUIDELINE,
        status=status or IntelligenceStatus.DRAFT,
        impact_level=impact_level or ImpactLevel.MEDIUM,
        impact_reason="Test impact reason",
        created_by=creator.id if creator else None,
        updated_by=creator.id if creator else None,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def make_distribution(db, *, item, organization, actor=None):
    from datetime import datetime, timezone

    from app.models.intelligence import IntelligenceDistribution

    grant = IntelligenceDistribution(
        intelligence_item_id=item.id, organization_id=organization.id,
        distributed_at=datetime.now(timezone.utc), distributed_by=actor.id if actor else None,
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)
    return grant
