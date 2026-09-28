"""
Development seed data (spec §56-57). NOT for production use — every
password here is printed to stdout on purpose so a developer can log in
immediately; run only against a local/dev database.

Usage:
    ./.venv/bin/python seed.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.database import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.organization import Organization, OrganizationStatus, ThemeName  # noqa: E402
from app.models.platform import FeatureFlag  # noqa: E402
from app.models.rbac import (  # noqa: E402
    Permission,
    PermissionAction,
    PermissionDomain,
    Role,
    RoleCategory,
    RolePermission,
    Scope,
    ScopeType,
    SoDPolicy,
    UserRoleAssignment,
)
from app.models.standards import RegulatoryStandard, StandardVersion, DocumentStatus  # noqa: E402
from app.models.user import User, UserStatus  # noqa: E402
from app.models.regulatory_structure import (  # noqa: E402
    RegulatoryAuthority,
    AuthorityType,
    Product,
    RegulatoryApplication,
    RegulatoryApplicationType,
)
from app.models.ctd import CTDModule, CTDSection
from app.models.dossier import Dossier, DossierStatus  # noqa: E402
from app.models.organization import OrganizationType  # noqa: E402
from app.models.intelligence import (  # noqa: E402
    IntelligenceSource,
    SourceType,
    RegulatoryIntelligenceItem,
    IntelligenceScope,
    IntelligenceType,
    IntelligenceStatus,
    ImpactLevel,
    IntelligenceTag,
    IntelligenceItemTag,
    IntelligenceDistribution,
)
from datetime import date, datetime, timezone  # noqa: E402

DEV_PASSWORD = "DevOnly!2026"  # noqa: S105 — intentionally not a secret, see module docstring


def seed_permissions(db) -> dict:
    perms = {}
    for domain in PermissionDomain:
        for action in PermissionAction:
            code = f"{domain.value}_{action.value}"
            existing = db.query(Permission).filter(Permission.code == code).first()
            if existing:
                perms[code] = existing
                continue
            p = Permission(domain=domain, action=action, code=code)
            db.add(p)
            perms[code] = p
    db.commit()
    return {code: p for code, p in perms.items()}


def get_or_create_role(db, *, code, name, category, description, organization_id=None, is_system_role=False) -> Role:
    role = db.query(Role).filter(Role.code == code, Role.organization_id == organization_id).first()
    if role:
        return role
    role = Role(
        code=code,
        name=name,
        category=category,
        description=description,
        organization_id=organization_id,
        is_system_role=is_system_role,
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


def grant(db, role: Role, perms: dict, codes: list[str]) -> None:
    # dict.fromkeys dedupes while preserving order — defends against a
    # code appearing twice across a hand-written list (which happened
    # once already: harmless in intent, but a same-transaction
    # duplicate INSERT is a real IntegrityError, not just redundant).
    for code in dict.fromkeys(codes):
        permission = perms[code]
        exists = (
            db.query(RolePermission)
            .filter(RolePermission.role_id == role.id, RolePermission.permission_id == permission.id)
            .first()
        )
        if not exists:
            db.add(RolePermission(role_id=role.id, permission_id=permission.id))
    db.commit()


def set_role_permissions(db, role: Role, perms: dict, codes: list[str]) -> None:
    """Make `role` hold EXACTLY `codes` — adds what's missing AND revokes
    anything else. grant() is add-only, which is right for most roles but
    wrong for a security invariant: when a role's definition narrows
    between releases, an add-only seed leaves the old broader grants in
    every already-seeded database. Used only for SYSTEM_ADMINISTRATOR."""
    wanted = {perms[c].id for c in dict.fromkeys(codes)}
    stale = [rp for rp in db.query(RolePermission).filter(RolePermission.role_id == role.id) if rp.permission_id not in wanted]
    for rp in stale:
        db.delete(rp)
    db.commit()
    if stale:
        print(f"Revoked {len(stale)} stale permission grant(s) from {role.code}")
    grant(db, role, perms, codes)


# System Administrator is defined by an ALLOW-list of technical domains.
# The earlier deny-list ("everything except DOCUMENT_/PRODUCT_/...")
# silently granted every new domain a later layer added; an allow-list
# makes "no automatic scientific/regulatory content access" the default
# for anything not named here. AUDIT is view-only: the audit trail is
# append-only, so CREATE/EDIT/DELETE on it should not exist for anyone.
SYSTEM_ADMIN_ALLOWED: dict[str, tuple[str, ...]] = {
    "USER": tuple(a.value for a in PermissionAction),
    "ROLE": tuple(a.value for a in PermissionAction),
    "ORGANIZATION": tuple(a.value for a in PermissionAction),
    "ACCESS": tuple(a.value for a in PermissionAction),
    "STANDARDS": tuple(a.value for a in PermissionAction),
    "AUDIT": ("VIEW",),
}


def seed_platform_roles(db, perms) -> dict:
    all_codes = list(perms.keys())
    super_admin = get_or_create_role(
        db,
        code="COLAB_SUPER_ADMIN",
        name="CoLAB Super Admin",
        category=RoleCategory.PLATFORM,
        description="Platform-level administrator across all tenants.",
        is_system_role=True,
    )
    grant(db, super_admin, perms, all_codes)

    system_admin = get_or_create_role(
        db,
        code="SYSTEM_ADMINISTRATOR",
        name="System Administrator",
        category=RoleCategory.PLATFORM,
        description="Technical administration. Does NOT automatically receive scientific/dossier-content permissions (spec §16).",
        is_system_role=True,
    )
    set_role_permissions(
        db, system_admin, perms,
        [f"{domain}_{action}" for domain, actions in SYSTEM_ADMIN_ALLOWED.items() for action in actions],
    )

    tenant_admin = get_or_create_role(
        db,
        code="TENANT_ADMINISTRATOR",
        name="Tenant Administrator",
        category=RoleCategory.PLATFORM,
        description="Administers a single organization.",
        is_system_role=True,
    )
    grant(
        db,
        tenant_admin,
        perms,
        [
            "USER_VIEW", "USER_CREATE", "USER_EDIT", "USER_ADMINISTER",
            "ROLE_VIEW", "ROLE_ADMINISTER",
            "ORGANIZATION_VIEW", "ORGANIZATION_EDIT",
            "AUDIT_VIEW",
            "DOCUMENT_VIEW", "SUBMISSION_VIEW", "RESPONSE_VIEW", "INTELLIGENCE_VIEW",
            "STANDARDS_VIEW",
            # Layer 2
            "PRODUCT_VIEW", "PRODUCT_CREATE", "PRODUCT_EDIT", "PRODUCT_ADMINISTER",
            "APPLICATION_VIEW", "APPLICATION_CREATE", "APPLICATION_EDIT",
            "DOSSIER_VIEW", "ACTIVITY_VIEW",
            # Layer 3: manages the tenant's own intelligence + its
            # configuration, but ownership checks (not permission grants)
            # are what stop this from ever touching CoLAB's global items.
            "INTELLIGENCE_CREATE", "INTELLIGENCE_EDIT", "INTELLIGENCE_PUBLISH", "INTELLIGENCE_ADMINISTER",
            "INTELLIGENCE_CONFIGURATION_VIEW", "INTELLIGENCE_CONFIGURATION_EDIT",
        ],
    )

    auditor = get_or_create_role(
        db,
        code="AUDITOR",
        name="Auditor",
        category=RoleCategory.PLATFORM,
        description="Controlled read-only access (spec §16).",
        is_system_role=True,
    )
    grant(
        db,
        auditor,
        perms,
        [
            "AUDIT_VIEW", "DOCUMENT_VIEW", "SUBMISSION_VIEW", "RESPONSE_VIEW", "USER_VIEW", "ROLE_VIEW",
            # Layer 2 — read-only across the new regulatory entities too.
            "PRODUCT_VIEW", "APPLICATION_VIEW", "DOSSIER_VIEW", "ACTIVITY_VIEW",
            # Layer 3
            "INTELLIGENCE_VIEW",
        ],
    )

    return {
        "COLAB_SUPER_ADMIN": super_admin,
        "SYSTEM_ADMINISTRATOR": system_admin,
        "TENANT_ADMINISTRATOR": tenant_admin,
        "AUDITOR": auditor,
    }


def seed_regulatory_role_templates(db, perms) -> dict:
    trainee = get_or_create_role(
        db, code="RA_TRAINEE", name="RA Trainee / Associate",
        category=RoleCategory.REGULATORY_TEMPLATE, description="Entry-level regulatory affairs role.",
    )
    grant(
        db, trainee, perms,
        [
            "DOCUMENT_VIEW", "DOCUMENT_CREATE",
            # Layer 2 (spec §20): create/edit drafts, view dossiers —
            # explicitly no DOSSIER_APPROVE, no DOSSIER_PUBLISH (lock).
            "PRODUCT_VIEW", "APPLICATION_VIEW", "DOSSIER_VIEW", "DOSSIER_CREATE", "DOSSIER_EDIT", "ACTIVITY_VIEW",
            "INTELLIGENCE_VIEW",
        ],
    )

    senior = get_or_create_role(
        db, code="SENIOR_RA_SPECIALIST", name="Senior RA Specialist / Lead",
        category=RoleCategory.REGULATORY_TEMPLATE, description="Experienced individual contributor.",
    )
    grant(
        db, senior, perms,
        [
            "DOCUMENT_VIEW", "DOCUMENT_CREATE", "DOCUMENT_EDIT", "DOCUMENT_REVIEW", "SUBMISSION_VIEW", "SUBMISSION_CREATE",
            # Layer 2: create/edit/review, "can request approval" ==
            # DOSSIER_EDIT is what actually gates DRAFT -> UNDER_REVIEW
            # (see _TRANSITION_PERMISSION) — still no DOSSIER_APPROVE.
            "PRODUCT_VIEW", "PRODUCT_CREATE", "APPLICATION_VIEW", "APPLICATION_CREATE",
            "DOSSIER_VIEW", "DOSSIER_CREATE", "DOSSIER_EDIT", "DOSSIER_REVIEW",
            "ACTIVITY_VIEW", "ACTIVITY_CREATE",
            # Layer 3: "Regulatory Specialist" capability (spec §19) —
            # view + create tenant-specific intelligence if permitted.
            "INTELLIGENCE_VIEW", "INTELLIGENCE_CREATE", "INTELLIGENCE_EDIT",
        ],
    )

    manager = get_or_create_role(
        db, code="RA_MANAGER", name="RA Manager / Country Lead",
        category=RoleCategory.REGULATORY_TEMPLATE, description="Manages a market/country regulatory team.",
    )
    grant(
        db, manager, perms,
        [
            "DOCUMENT_VIEW", "DOCUMENT_CREATE", "DOCUMENT_EDIT", "DOCUMENT_REVIEW",
            "SUBMISSION_VIEW", "SUBMISSION_CREATE", "SUBMISSION_EDIT", "SUBMISSION_REVIEW",
            # Layer 2: "Approve, Export, ... Lock sequences/dossiers
            # where authorized" — DOSSIER_PUBLISH is what gates the
            # ACTIVE<->LOCKED transition.
            "PRODUCT_VIEW", "PRODUCT_CREATE", "PRODUCT_EDIT", "APPLICATION_VIEW", "APPLICATION_CREATE", "APPLICATION_EDIT",
            "DOSSIER_VIEW", "DOSSIER_CREATE", "DOSSIER_EDIT", "DOSSIER_REVIEW", "DOSSIER_APPROVE", "DOSSIER_PUBLISH", "DOSSIER_EXPORT",
            "ACTIVITY_VIEW", "ACTIVITY_CREATE",
            # Layer 3: "Regulatory Manager" capability (spec §19) — view,
            # configure permitted regulatory interests, review
            # tenant-relevant intelligence where authorized.
            "INTELLIGENCE_VIEW", "INTELLIGENCE_REVIEW", "INTELLIGENCE_CONFIGURATION_VIEW",
        ],
    )

    publisher = get_or_create_role(
        db, code="PUBLISHING_SPECIALIST", name="Publishing / eCTD Specialist",
        category=RoleCategory.REGULATORY_TEMPLATE, description="Prepares and publishes submission sequences.",
    )
    grant(
        db, publisher, perms,
        [
            "DOCUMENT_VIEW", "SUBMISSION_VIEW", "SUBMISSION_CREATE", "SUBMISSION_EDIT", "SUBMISSION_PUBLISH",
            # Layer 2: "Compile/prepare, validate, lock/dispatch where
            # authorized" — no DOSSIER_APPROVE (that's RA Manager/Head
            # of RA's call), but does get DOSSIER_PUBLISH to lock.
            "PRODUCT_VIEW", "APPLICATION_VIEW", "DOSSIER_VIEW", "DOSSIER_EDIT", "DOSSIER_PUBLISH", "ACTIVITY_VIEW",
            "INTELLIGENCE_VIEW",
        ],
    )

    head_of_ra = get_or_create_role(
        db, code="HEAD_OF_RA", name="Head of RA / Executive",
        category=RoleCategory.REGULATORY_TEMPLATE, description="Final approval authority.",
    )
    grant(
        db, head_of_ra, perms,
        [
            "DOCUMENT_VIEW", "DOCUMENT_APPROVE", "SUBMISSION_VIEW", "SUBMISSION_APPROVE",
            "RESPONSE_VIEW", "INTELLIGENCE_VIEW",
            # Layer 2: "Global read within tenant scope, high-level
            # approval/signoff where configured".
            "PRODUCT_VIEW", "APPLICATION_VIEW", "DOSSIER_VIEW", "DOSSIER_APPROVE", "ACTIVITY_VIEW",
        ],
    )

    consultant = get_or_create_role(
        db, code="EXTERNAL_CONSULTANT", name="External Consultant / CRO",
        category=RoleCategory.REGULATORY_TEMPLATE,
        description="Time-bounded external access (spec §22) — pair with valid_until on the assignment or the user.",
    )
    grant(
        db, consultant, perms,
        ["DOCUMENT_VIEW", "DOCUMENT_CREATE", "DOCUMENT_EDIT", "DOSSIER_VIEW", "DOSSIER_CREATE", "DOSSIER_EDIT", "INTELLIGENCE_VIEW"],
    )

    return {
        "RA_TRAINEE": trainee,
        "SENIOR_RA_SPECIALIST": senior,
        "RA_MANAGER": manager,
        "PUBLISHING_SPECIALIST": publisher,
        "HEAD_OF_RA": head_of_ra,
        "EXTERNAL_CONSULTANT": consultant,
    }


def seed_sod_policies(db) -> None:
    existing = db.query(SoDPolicy).filter(SoDPolicy.name == "Author cannot be final approver").first()
    if existing:
        return
    db.add(
        SoDPolicy(
            organization_id=None,  # platform-wide default
            name="Author cannot be final approver",
            action_a=PermissionAction.CREATE,
            action_b=PermissionAction.APPROVE,
            description="The user who created a resource may not also approve it (spec §20).",
            active=True,
        )
    )
    db.commit()


def seed_feature_flags(db) -> None:
    flags = [
        ("response_center", "Health Authority Response Center (Layer 5)"),
        ("global_intelligence", "Global Intelligence ingestion (Layer 6)"),
        ("ectd_v4", "Full eCTD v4.0 generation/validation engine (Layer 4)"),
        ("regulatory_writing", "Module 2 AI regulatory writing (Layer 3)"),
        ("validation_center", "GxP validation center (Layer 8)"),
        ("genx_theme", "RAISA GenX theme availability"),
    ]
    for key, description in flags:
        if not db.query(FeatureFlag).filter(FeatureFlag.key == key).first():
            db.add(FeatureFlag(key=key, description=description, enabled_globally=(key == "genx_theme")))
    db.commit()


def seed_standards_registry(db) -> None:
    entries = [
        ("ICH eCTD v4.0 Comprehensive Table of Contents", "ICH", "GLOBAL", "2.2"),
        ("FDA eCTD v4.0 Validation Criteria", "FDA", "US", "1.6"),
        ("FDA File Format Specification", "FDA", "US", "9.3"),
        ("FDA Transmission Specification", "FDA", "US", "2.0"),
        ("EU eCTD Module 1 Implementation Guide", "EMA", "EU", "1.2"),
        ("EU Practical Guidance", "EMA", "EU", "1.0"),
        ("EU Accepted File Formats", "EMA", "EU", "1.0"),
        ("EU Controlled Vocabularies", "EMA", "EU", "1.0"),
    ]
    for name, authority, region, version_label in entries:
        standard = db.query(RegulatoryStandard).filter(RegulatoryStandard.name == name).first()
        if not standard:
            standard = RegulatoryStandard(name=name, authority=authority, region=region)
            db.add(standard)
            db.commit()
            db.refresh(standard)
        if not db.query(StandardVersion).filter(StandardVersion.standard_id == standard.id).first():
            db.add(
                StandardVersion(
                    standard_id=standard.id,
                    version_label=version_label,
                    document_status=DocumentStatus.FINAL,
                    source_reference="Supplied source package (spec §33) — see /docs/STANDARDS_REGISTRY.md",
                )
            )
    db.commit()


def seed_regulatory_authorities(db) -> dict:
    """Small reference set (spec Layer 2 §2: "Seed only a small set of
    reference authorities required for development/demo purposes")."""
    authorities = [
        ("U.S. Food and Drug Administration", "FDA", "United States", "US", AuthorityType.NATIONAL),
        ("European Medicines Agency", "EMA", None, "EU", AuthorityType.REGIONAL),
        ("Central Drugs Standard Control Organisation", "CDSCO", "India", "IN", AuthorityType.NATIONAL),
    ]
    result = {}
    for name, short_name, country, region, authority_type in authorities:
        authority = db.query(RegulatoryAuthority).filter(RegulatoryAuthority.short_name == short_name).first()
        if not authority:
            authority = RegulatoryAuthority(
                name=name, short_name=short_name, country=country, region=region, authority_type=authority_type
            )
            db.add(authority)
            db.commit()
            db.refresh(authority)
        result[short_name] = authority
    return result


def _get_or_create_module(db, *, code, title, display_order, authority_id=None) -> CTDModule:
    module = db.query(CTDModule).filter(CTDModule.code == code, CTDModule.authority_id == authority_id).first()
    if module:
        return module
    module = CTDModule(code=code, title=title, display_order=display_order, authority_id=authority_id)
    db.add(module)
    db.commit()
    db.refresh(module)
    return module


def _get_or_create_section(db, *, module, section_code, title, display_order, parent=None, authority_id=None, region=None) -> CTDSection:
    existing = (
        db.query(CTDSection)
        .filter(CTDSection.module_id == module.id, CTDSection.section_code == section_code, CTDSection.authority_id == authority_id)
        .first()
    )
    if existing:
        return existing
    section = CTDSection(
        module_id=module.id,
        parent_section_id=parent.id if parent else None,
        section_code=section_code,
        title=title,
        display_order=display_order,
        authority_id=authority_id,
        region=region,
    )
    db.add(section)
    db.commit()
    db.refresh(section)
    return section


def seed_ctd_registry(db, authorities: dict) -> None:
    """Populates the registry Layer 1 §34 built the (empty) architecture
    for. Modules 2-5 are the universal ICH structure (spec §7-10);
    Module 1 is deliberately NOT one universal structure (spec §6) — the
    generic module holds a couple of common sections, and FDA/EMA each
    get their own authority-specific Module 1 sections underneath it.
    """
    # --- Module 1: authority-specific (spec §6) ---
    module_1 = _get_or_create_module(db, code="MODULE_1", title="Regional Administrative Information", display_order=1)
    _get_or_create_section(db, module=module_1, section_code="1.1", title="Table of Contents (Module 1)", display_order=1)
    _get_or_create_section(
        db, module=module_1, section_code="1.2", title="Application Form", display_order=2,
        authority_id=authorities["FDA"].id, region="US",
    )
    _get_or_create_section(
        db, module=module_1, section_code="1.2", title="Application Form (EU CTA)", display_order=2,
        authority_id=authorities["EMA"].id, region="EU",
    )
    _get_or_create_section(
        db, module=module_1, section_code="1.3", title="Product Information", display_order=3,
        authority_id=authorities["EMA"].id, region="EU",
    )

    # --- Module 2: CTD Summaries — 2.1 through 2.7 (spec §7) ---
    module_2 = _get_or_create_module(db, code="MODULE_2", title="CTD Summaries", display_order=2)
    for code, title, order in [
        ("2.1", "CTD Table of Contents", 1),
        ("2.2", "CTD Introduction", 2),
        ("2.3", "Quality Overall Summary", 3),
        ("2.4", "Nonclinical Overview", 4),
        ("2.5", "Clinical Overview", 5),
        ("2.6", "Nonclinical Written and Tabulated Summaries", 6),
        ("2.7", "Clinical Summary", 7),
    ]:
        _get_or_create_section(db, module=module_2, section_code=code, title=title, display_order=order)

    # --- Module 3: Quality (spec §8) ---
    module_3 = _get_or_create_module(db, code="MODULE_3", title="Quality", display_order=3)
    m3_toc = _get_or_create_section(db, module=module_3, section_code="3.1", title="Table of Contents", display_order=1)
    m3_body = _get_or_create_section(db, module=module_3, section_code="3.2", title="Body of Data", display_order=2)
    for code, title, order in [
        ("3.2.S", "Drug Substance", 1),
        ("3.2.P", "Drug Product", 2),
        ("3.2.A", "Appendices", 3),
        ("3.2.R", "Regional Information", 4),
    ]:
        _get_or_create_section(db, module=module_3, section_code=code, title=title, display_order=order, parent=m3_body)
    _get_or_create_section(db, module=module_3, section_code="3.3", title="Literature References", display_order=3)

    # --- Module 4: Nonclinical Study Reports (spec §9) ---
    module_4 = _get_or_create_module(db, code="MODULE_4", title="Nonclinical Study Reports", display_order=4)
    for code, title, order in [
        ("4.1", "Table of Contents", 1),
        ("4.2", "Study Reports", 2),
        ("4.3", "Literature References", 3),
    ]:
        _get_or_create_section(db, module=module_4, section_code=code, title=title, display_order=order)

    # --- Module 5: Clinical Study Reports (spec §10) ---
    module_5 = _get_or_create_module(db, code="MODULE_5", title="Clinical Study Reports", display_order=5)
    for code, title, order in [
        ("5.1", "Table of Contents", 1),
        ("5.2", "Tabular Listing of Clinical Studies", 2),
        ("5.3", "Clinical Study Reports", 3),
        ("5.4", "Literature References", 4),
    ]:
        _get_or_create_section(db, module=module_5, section_code=code, title=title, display_order=order)


def seed_colab_platform_and_intelligence(db, *, platform_roles: dict, demo_org: Organization, tenant_b_org: Organization, authorities: dict) -> None:
    """CoLAB Systems as a real, ordinary organization (organization_type
    = PLATFORM), per your confirmed design decision — not a magic
    tenant-zero id. Owns every GLOBAL intelligence item."""
    colab_org = db.query(Organization).filter(Organization.slug == "colab-systems").first()
    if not colab_org:
        colab_org = Organization(name="CoLAB Systems", slug="colab-systems", organization_type=OrganizationType.PLATFORM)
        db.add(colab_org)
        db.commit()
        db.refresh(colab_org)

    colab_admin = db.query(User).filter(User.organization_id == colab_org.id, User.email == "colab.admin@example.com").first()
    if not colab_admin:
        colab_admin = User(
            organization_id=colab_org.id, email="colab.admin@example.com",
            password_hash=hash_password(DEV_PASSWORD), name="CoLAB Platform Admin", status=UserStatus.ACTIVE,
        )
        db.add(colab_admin)
        db.commit()
        db.refresh(colab_admin)
        db.add(UserRoleAssignment(
            user_id=colab_admin.id, organization_id=colab_org.id, role_id=platform_roles["COLAB_SUPER_ADMIN"].id,
            granted_at=datetime.now(timezone.utc),
        ))
        db.commit()

    # --- Source registry (spec §4) — a small, configurable set, not a
    # hard-coded crawl list. ---
    sources = {}
    for name, source_type, authority_key, url in [
        ("FDA Guidance Documents", SourceType.REGULATORY_AUTHORITY, "FDA", "https://www.fda.gov/regulatory-information/search-fda-guidance-documents"),
        ("EMA News", SourceType.REGULATORY_AUTHORITY, "EMA", "https://www.ema.europa.eu/en/news"),
        ("Fictional Pharma Industry Wire", SourceType.INDUSTRY_PUBLICATION, None, None),
    ]:
        source = db.query(IntelligenceSource).filter(IntelligenceSource.name == name).first()
        if not source:
            source = IntelligenceSource(
                name=name, source_type=source_type,
                authority_id=authorities[authority_key].id if authority_key else None,
                country_region=authorities[authority_key].region if authority_key else "GLOBAL",
                url=url, active=True,
            )
            db.add(source)
            db.commit()
            db.refresh(source)
        sources[name] = source

    # --- Tags (spec §10) ---
    tag_defs = [
        ("THERAPEUTIC_AREA", "Oncology"), ("THERAPEUTIC_AREA", "Cardiology"),
        ("REGULATORY_TOPIC", "Labeling"), ("REGULATORY_TOPIC", "Post-Approval Change"),
        ("CTD_MODULE", "Module 3"),
    ]
    tags = {}
    for tag_type, name in tag_defs:
        tag = db.query(IntelligenceTag).filter(IntelligenceTag.tag_type == tag_type, IntelligenceTag.name == name).first()
        if not tag:
            tag = IntelligenceTag(tag_type=tag_type, name=name)
            db.add(tag)
            db.commit()
            db.refresh(tag)
        tags[name] = tag

    # --- A GLOBAL, published, distributed item ---
    global_item = (
        db.query(RegulatoryIntelligenceItem)
        .filter(RegulatoryIntelligenceItem.organization_id == colab_org.id, RegulatoryIntelligenceItem.title.like("FDA finalizes%"))
        .first()
    )
    if not global_item:
        global_item = RegulatoryIntelligenceItem(
            organization_id=colab_org.id,
            scope=IntelligenceScope.GLOBAL,
            source_id=sources["FDA Guidance Documents"].id,
            source_url=sources["FDA Guidance Documents"].url,
            title="FDA finalizes updated Module 3 quality guidance (fictional demo item)",
            summary="Demo/fictional summary of a Module 3 quality guidance update, for seed purposes only.",
            intelligence_type=IntelligenceType.REGULATORY_GUIDELINE,
            authority_id=authorities["FDA"].id,
            country_region="US",
            publication_date=date.today(),
            status=IntelligenceStatus.PUBLISHED,
            impact_level=ImpactLevel.HIGH,
            impact_reason="Demo seed data — illustrative impact assessment, not a real regulatory judgment.",
            impact_assessment_source="MANUAL",
            therapeutic_area=None,
            regulatory_area="Quality",
            created_by=colab_admin.id,
            updated_by=colab_admin.id,
        )
        db.add(global_item)
        db.commit()
        db.refresh(global_item)
        db.add(IntelligenceItemTag(intelligence_item_id=global_item.id, tag_id=tags["Module 3"].id))
        db.add(IntelligenceDistribution(
            intelligence_item_id=global_item.id, organization_id=demo_org.id,
            distributed_at=datetime.now(timezone.utc), distributed_by=colab_admin.id,
        ))
        # Deliberately NOT distributed to tenant_b_org — demonstrates
        # that distribution is per-organization, not "every customer
        # sees every global item" (spec §24 test 5).
        db.commit()

    # --- A TENANT-scope item, owned by the customer itself ---
    ra_specialist = db.query(User).filter(User.organization_id == demo_org.id, User.email == "ra.specialist@example.com").first()
    if ra_specialist and not db.query(RegulatoryIntelligenceItem).filter(RegulatoryIntelligenceItem.organization_id == demo_org.id).first():
        db.add(RegulatoryIntelligenceItem(
            organization_id=demo_org.id,
            scope=IntelligenceScope.TENANT,
            title="Internal note: upcoming renewal deadline (fictional demo item)",
            summary="Tenant-authored note tracking an internal regulatory deadline — never shared with other tenants.",
            intelligence_type=IntelligenceType.REGULATORY_CHANGE,
            country_region="US",
            publication_date=date.today(),
            status=IntelligenceStatus.PUBLISHED,
            impact_level=ImpactLevel.MEDIUM,
            impact_reason="Demo seed data.",
            created_by=ra_specialist.id,
            updated_by=ra_specialist.id,
        ))
        db.commit()


def seed_tenant(db, *, name, slug, platform_roles, template_roles, users_spec) -> Organization:
    org = db.query(Organization).filter(Organization.slug == slug).first()
    if not org:
        org = Organization(
            name=name,
            slug=slug,
            status=OrganizationStatus.ACTIVE,
            default_theme=ThemeName.RAISA_OFFICE,
        )
        db.add(org)
        db.commit()
        db.refresh(org)

    # Sample scope hierarchy matching the spec's own example: "Product
    # ABC / India" (spec §19, §66).
    product_scope = db.query(Scope).filter(Scope.organization_id == org.id, Scope.label == "Product ABC").first()
    if not product_scope:
        product_scope = Scope(organization_id=org.id, scope_type=ScopeType.PRODUCT, label="Product ABC")
        db.add(product_scope)
        db.commit()
        db.refresh(product_scope)

    market_scope = (
        db.query(Scope).filter(Scope.organization_id == org.id, Scope.label == "Product ABC / India").first()
    )
    if not market_scope:
        market_scope = Scope(
            organization_id=org.id,
            scope_type=ScopeType.MARKET,
            label="Product ABC / India",
            parent_id=product_scope.id,
        )
        db.add(market_scope)
        db.commit()
        db.refresh(market_scope)

    for email, name, role_key, role_source, scoped in users_spec:
        user = db.query(User).filter(User.organization_id == org.id, User.email == email).first()
        if not user:
            user = User(
                organization_id=org.id,
                email=email,
                password_hash=hash_password(DEV_PASSWORD),
                name=name,
                status=UserStatus.ACTIVE,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        role = (platform_roles if role_source == "platform" else template_roles)[role_key]
        already_assigned = (
            db.query(UserRoleAssignment)
            .filter(UserRoleAssignment.user_id == user.id, UserRoleAssignment.role_id == role.id)
            .first()
        )
        if not already_assigned:
            db.add(
                UserRoleAssignment(
                    user_id=user.id,
                    organization_id=org.id,
                    role_id=role.id,
                    scope_id=market_scope.id if scoped else None,
                    granted_at=datetime.now(timezone.utc),
                )
            )
    db.commit()
    return org


def seed_layer2_demo_data(db, *, org: Organization, authorities: dict, owner_email: str) -> None:
    """Fictional demo data only (spec Layer 2 §28) — never a real
    pharmaceutical company, regardless of what a real customer roster
    might one day look like."""
    owner = db.query(User).filter(User.organization_id == org.id, User.email == owner_email).first()

    product = db.query(Product).filter(Product.organization_id == org.id, Product.name == "Synapizol").first()
    if not product:
        product = Product(
            organization_id=org.id,
            name="Synapizol",  # fictional INN-style name, not a real product
            active_ingredient="synapizol citrate",
            dosage_form="Film-coated tablet",
            strength="10 mg",
            route_of_administration="Oral",
            indication="Fictional demo indication — not a real therapeutic claim",
            created_by=owner.id if owner else None,
            updated_by=owner.id if owner else None,
        )
        db.add(product)
        db.commit()
        db.refresh(product)

    application = (
        db.query(RegulatoryApplication)
        .filter(RegulatoryApplication.organization_id == org.id, RegulatoryApplication.product_id == product.id)
        .first()
    )
    if not application:
        application = RegulatoryApplication(
            organization_id=org.id,
            product_id=product.id,
            authority_id=authorities["FDA"].id,
            country_region="US",
            application_type=RegulatoryApplicationType.MARKETING_AUTHORIZATION,
            created_by=owner.id if owner else None,
            updated_by=owner.id if owner else None,
        )
        db.add(application)
        db.commit()
        db.refresh(application)

    if not db.query(Dossier).filter(Dossier.organization_id == org.id, Dossier.product_id == product.id).first():
        db.add(
            Dossier(
                organization_id=org.id,
                product_id=product.id,
                regulatory_application_id=application.id,
                authority_id=authorities["FDA"].id,
                region="US",
                standard_version="4.0",
                status=DossierStatus.DRAFT,
                owner_id=owner.id if owner else application.created_by,
                created_by=owner.id if owner else None,
                updated_by=owner.id if owner else None,
            )
        )
        db.commit()


def main() -> None:
    db = SessionLocal()
    try:
        perms = seed_permissions(db)
        platform_roles = seed_platform_roles(db, perms)
        template_roles = seed_regulatory_role_templates(db, perms)
        seed_sod_policies(db)
        seed_feature_flags(db)
        seed_standards_registry(db)
        authorities = seed_regulatory_authorities(db)
        seed_ctd_registry(db, authorities)

        seed_tenant(
            db,
            name="Demo Pharma",
            slug="demo-pharma",
            platform_roles=platform_roles,
            template_roles=template_roles,
            users_spec=[
                ("tenant.admin@example.com", "Demo Tenant Admin", "TENANT_ADMINISTRATOR", "platform", False),
                ("ra.specialist@example.com", "Demo RA Specialist", "SENIOR_RA_SPECIALIST", "template", True),
                # Org-wide on purpose (spec §66 only scopes the Senior RA
                # Specialist to "Product ABC / India"). Layer 2/3 service
                # checks are org-level, so a scoped-only assignment can't
                # perform Layer 2/3 writes yet — see
                # docs/LAYER_3_REGULATORY_INTELLIGENCE.md, Known limitations.
                ("ra.manager@example.com", "Demo RA Manager", "RA_MANAGER", "template", False),
                ("publisher@example.com", "Demo Publisher", "PUBLISHING_SPECIALIST", "template", False),
                ("auditor@example.com", "Demo Auditor", "AUDITOR", "platform", False),
            ],
        )

        # Second tenant, so the mandatory tenant-isolation demo (spec §66)
        # has something to isolate against out of the box.
        seed_tenant(
            db,
            name="Tenant B Pharma",
            slug="tenant-b-pharma",
            platform_roles=platform_roles,
            template_roles=template_roles,
            users_spec=[
                ("ra.manager@example.com", "Tenant B RA Manager", "RA_MANAGER", "template", False),
            ],
        )

        demo_org = db.query(Organization).filter(Organization.slug == "demo-pharma").first()
        tenant_b_org = db.query(Organization).filter(Organization.slug == "tenant-b-pharma").first()
        seed_layer2_demo_data(db, org=demo_org, authorities=authorities, owner_email="ra.specialist@example.com")
        seed_layer2_demo_data(db, org=tenant_b_org, authorities=authorities, owner_email="ra.manager@example.com")

        seed_colab_platform_and_intelligence(db, platform_roles=platform_roles, demo_org=demo_org, tenant_b_org=tenant_b_org, authorities=authorities)

        print("Seed complete.")
        print(f"Dev password for every seeded user: {DEV_PASSWORD}")
        print("Try: demo-pharma / tenant.admin@example.com")
        print("     tenant-b-pharma / ra.manager@example.com")
        print("     colab-systems / colab.admin@example.com")
    finally:
        db.close()


if __name__ == "__main__":
    main()
