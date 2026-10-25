"""
Administration of the pieces of the intelligence domain that aren't
items: the source registry, the shared tag vocabulary, and each
tenant's intelligence preferences (spec §4, §7, §10, §20).

Two different scopes live here, and the difference matters:

* Sources and tags are GLOBAL, CoLAB-managed reference data — visible to
  every tenant. Writes therefore require the caller's organization to be
  the platform org, on top of the permission check (a customer org can
  define a custom role holding any permission; permissions alone can't
  stop it from editing something every other tenant reads).
* Preferences are per-tenant. They're stored in Layer 1's generic
  `Configuration` table under the caller's OWN organization_id — no
  function here takes an organization_id from a request body.

Every mutation goes through the existing Layer 1 audit service.
"""
import json
import uuid

from sqlalchemy.orm import Session

from app.models.audit import AuditEventType
from app.models.intelligence import IntelligenceSource, IntelligenceTag
from app.models.platform import Configuration, ConfigurationScope
from app.models.rbac import PermissionAction, PermissionDomain
from app.services import audit_service
from app.services.intelligence_service import DomainError, _require, require_platform_organization  # same domain package

PREFERENCES_KEY = "intelligence_preferences"


def _plain(value):
    return value.value if hasattr(value, "value") else (str(value) if value is not None else None)


def create_source(db: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID, **fields) -> IntelligenceSource:
    _require(db, user_id=actor_id, organization_id=organization_id, domain=PermissionDomain.INTELLIGENCE_SOURCE, action=PermissionAction.CREATE)
    require_platform_organization(db, organization_id, what="manage the intelligence source registry")
    source = IntelligenceSource(**fields)
    db.add(source)
    db.commit()
    db.refresh(source)
    audit_service.record(
        db, organization_id=organization_id, event_type=AuditEventType.INTELLIGENCE_SOURCE_CHANGED,
        object_type="IntelligenceSource", object_id=source.id, user_id=actor_id,
        new_value=json.dumps({k: _plain(v) for k, v in fields.items()}),
    )
    return source


_SOURCE_EDITABLE = {"name", "source_type", "authority_id", "country_region", "url", "status", "collection_method", "frequency", "reliability_notes", "active"}


def update_source(db: Session, *, source: IntelligenceSource, organization_id: uuid.UUID, actor_id: uuid.UUID, changes: dict) -> IntelligenceSource:
    _require(db, user_id=actor_id, organization_id=organization_id, domain=PermissionDomain.INTELLIGENCE_SOURCE, action=PermissionAction.EDIT)
    require_platform_organization(db, organization_id, what="manage the intelligence source registry")
    unknown = set(changes) - _SOURCE_EDITABLE
    if unknown:
        raise DomainError(f"Fields cannot be changed: {', '.join(sorted(unknown))}", status_code=400)
    previous, updated = {}, {}
    for field, new_value in changes.items():
        old_value = getattr(source, field)
        if old_value != new_value:
            previous[field], updated[field] = _plain(old_value), _plain(new_value)
            setattr(source, field, new_value)
    if not updated:
        return source
    db.commit()
    db.refresh(source)
    audit_service.record(
        db, organization_id=organization_id, event_type=AuditEventType.INTELLIGENCE_SOURCE_CHANGED,
        object_type="IntelligenceSource", object_id=source.id, user_id=actor_id,
        previous_value=json.dumps(previous), new_value=json.dumps(updated),
    )
    return source


def create_tag(db: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID, tag_type: str, name: str) -> IntelligenceTag:
    _require(db, user_id=actor_id, organization_id=organization_id, domain=PermissionDomain.INTELLIGENCE, action=PermissionAction.ADMINISTER)
    require_platform_organization(db, organization_id, what="manage the shared tag vocabulary")
    existing = db.query(IntelligenceTag).filter(IntelligenceTag.tag_type == tag_type, IntelligenceTag.name == name).first()
    if existing:
        return existing
    tag = IntelligenceTag(tag_type=tag_type, name=name)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    audit_service.record(
        db, organization_id=organization_id, event_type=AuditEventType.INTELLIGENCE_UPDATED,
        object_type="IntelligenceTag", object_id=tag.id, user_id=actor_id,
        new_value=json.dumps({"tag_type": tag_type, "name": name}),
    )
    return tag


def _preferences_row(db: Session, organization_id: uuid.UUID) -> Configuration | None:
    return (
        db.query(Configuration)
        .filter(
            Configuration.scope == ConfigurationScope.ORGANIZATION,
            Configuration.organization_id == organization_id,
            Configuration.key == PREFERENCES_KEY,
        )
        .first()
    )


def get_preferences(db: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID) -> dict:
    _require(db, user_id=actor_id, organization_id=organization_id, domain=PermissionDomain.INTELLIGENCE_CONFIGURATION, action=PermissionAction.VIEW)
    row = _preferences_row(db, organization_id)
    return json.loads(row.value) if row else {}


def set_preferences(db: Session, *, organization_id: uuid.UUID, actor_id: uuid.UUID, preferences: dict) -> dict:
    _require(db, user_id=actor_id, organization_id=organization_id, domain=PermissionDomain.INTELLIGENCE_CONFIGURATION, action=PermissionAction.EDIT)
    row = _preferences_row(db, organization_id)
    previous = row.value if row else None
    value = json.dumps(preferences)
    if row is None:
        db.add(Configuration(scope=ConfigurationScope.ORGANIZATION, organization_id=organization_id, key=PREFERENCES_KEY, value=value))
    else:
        row.value = value
    db.commit()
    audit_service.record(
        db, organization_id=organization_id, event_type=AuditEventType.CONFIGURATION_CHANGED,
        object_type="IntelligencePreferences", user_id=actor_id, previous_value=previous, new_value=value,
    )
    return preferences
