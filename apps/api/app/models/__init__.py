"""
Import every model module here. SQLAlchemy's declarative Base only
knows about a table once its model class has been imported somewhere
in the process — Alembic's `--autogenerate` (and `Base.metadata.create_all`
in tests) walks `Base.metadata`, so a model missing from this list is a
model that silently never gets a table.
"""
from app.models.organization import Organization, BusinessUnit  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.auth_event import UserSession, AuthenticationEvent  # noqa: F401
from app.models.rbac import (  # noqa: F401
    Permission,
    Role,
    RolePermission,
    Scope,
    UserRoleAssignment,
    SoDPolicy,
    ElectronicSignature,
)
from app.models.audit import AuditEvent  # noqa: F401
from app.models.document import Document, DocumentVersion  # noqa: F401
from app.models.standards import RegulatoryStandard, StandardVersion, RegionalImplementation  # noqa: F401
from app.models.platform import Configuration, FeatureFlag, FeatureFlagOverride, Notification  # noqa: F401

# --- Layer 2: Dossier & CTD Foundation ---
from app.models.regulatory_structure import (  # noqa: F401
    Product,
    RegulatoryPortfolio,
    RegulatoryAuthority,
    RegulatoryApplication,
)
from app.models.dossier import Dossier  # noqa: F401
from app.models.ctd import CTDModule, CTDSection, DocumentCTDPlacement  # noqa: F401
from app.models.regulatory_activity import RegulatoryActivity, RegulatoryEvent  # noqa: F401

# --- Layer 3: Regulatory Intelligence Foundation ---
from app.models.intelligence import (  # noqa: F401
    IntelligenceSource,
    RegulatoryIntelligenceItem,
    IntelligenceTag,
    IntelligenceItemTag,
    IntelligenceDistribution,
    IntelligenceObjectLink,
)
