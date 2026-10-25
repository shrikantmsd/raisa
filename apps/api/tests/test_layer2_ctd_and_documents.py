"""
Layer 2 spec §27.C/D/F/G/H-K/L/O — product/application creation, CTD
hierarchy (including Module 1's authority-specific foundation), and
regulatory activities.
"""
from app.models.ctd import CTDModule, CTDSection, DocumentCTDPlacement
from app.models.document import Document
from app.models.rbac import PermissionAction, PermissionDomain

from tests.conftest import (
    assign_role,
    login_headers,
    make_authority,
    make_dossier_chain,
    make_organization,
    make_role_with_permissions,
    make_user,
)


def test_ctd_modules_1_through_5_exist_with_correct_titles(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    make_user(db, organization=org, email="user@acme.example")
    headers = login_headers(client, organization_slug="acme", email="user@acme.example")

    response = client.get("/api/v1/ctd/modules", headers=headers)
    assert response.status_code == 200
    modules = {m["code"]: m["title"] for m in response.json()}
    assert modules == {
        "MODULE_1": "Regional Administrative Information",
        "MODULE_2": "CTD Summaries",
        "MODULE_3": "Quality",
        "MODULE_4": "Nonclinical Study Reports",
        "MODULE_5": "Clinical Study Reports",
    }


def test_module_1_sections_are_authority_specific(db):
    """Spec §6: "DO NOT assume one universal Module 1 structure." — an
    FDA-flavored Module 1 section and an EMA-flavored one can coexist
    under the same module with the same section code."""
    module_1 = db.query(CTDModule).filter(CTDModule.code == "MODULE_1").first()
    assert module_1 is not None

    fda = make_authority(db, short_name="FDA", region="US")
    ema = make_authority(db, short_name="EMA", region="EU")

    fda_sections = db.query(CTDSection).filter(CTDSection.module_id == module_1.id, CTDSection.authority_id == fda.id).all()
    ema_sections = db.query(CTDSection).filter(CTDSection.module_id == module_1.id, CTDSection.authority_id == ema.id).all()

    assert len(fda_sections) >= 1
    assert len(ema_sections) >= 1
    # Same section_code ("1.2"), different authority — proves the
    # registry doesn't force one universal Module 1 layout.
    assert {s.section_code for s in fda_sections} & {s.section_code for s in ema_sections}


def test_module_2_has_all_seven_standard_sections(db):
    module_2 = db.query(CTDModule).filter(CTDModule.code == "MODULE_2").first()
    codes = {
        s.section_code
        for s in db.query(CTDSection).filter(CTDSection.module_id == module_2.id, CTDSection.authority_id.is_(None)).all()
    }
    assert codes == {"2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7"}


def test_module_3_has_drug_substance_and_drug_product_under_body_of_data(db):
    module_3 = db.query(CTDModule).filter(CTDModule.code == "MODULE_3").first()
    body = db.query(CTDSection).filter(CTDSection.module_id == module_3.id, CTDSection.section_code == "3.2").first()
    assert body is not None
    children = {s.section_code for s in db.query(CTDSection).filter(CTDSection.parent_section_id == body.id).all()}
    assert children == {"3.2.S", "3.2.P", "3.2.A", "3.2.R"}


def test_modules_4_and_5_have_their_foundational_sections(db):
    module_4 = db.query(CTDModule).filter(CTDModule.code == "MODULE_4").first()
    module_5 = db.query(CTDModule).filter(CTDModule.code == "MODULE_5").first()
    m4_codes = {s.section_code for s in db.query(CTDSection).filter(CTDSection.module_id == module_4.id).all()}
    m5_codes = {s.section_code for s in db.query(CTDSection).filter(CTDSection.module_id == module_5.id).all()}
    assert m4_codes == {"4.1", "4.2", "4.3"}
    assert m5_codes == {"5.1", "5.2", "5.3", "5.4"}


def test_document_can_be_placed_at_a_ctd_location(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = make_role_with_permissions(
        db, organization=None, name="Editor",
        permissions=[(PermissionDomain.DOSSIER, PermissionAction.VIEW), (PermissionDomain.DOSSIER, PermissionAction.EDIT)],
    )
    user = make_user(db, organization=org, email="editor@acme.example")
    assign_role(db, user=user, organization=org, role=role)
    _, _, dossier = make_dossier_chain(db, organization=org, owner=user)

    document = Document(organization_id=org.id, file_name="qos.pdf", mime_type="application/pdf", owner_id=user.id)
    db.add(document)
    db.commit()
    db.refresh(document)

    module_2 = db.query(CTDModule).filter(CTDModule.code == "MODULE_2").first()
    section_2_3 = (
        db.query(CTDSection).filter(CTDSection.module_id == module_2.id, CTDSection.section_code == "2.3").first()
    )

    headers = login_headers(client, organization_slug="acme", email="editor@acme.example")
    response = client.post(
        f"/api/v1/dossiers/{dossier.id}/documents",
        headers=headers,
        json={"document_id": str(document.id), "ctd_section_id": str(section_2_3.id)},
    )
    assert response.status_code == 201
    placement = db.query(DocumentCTDPlacement).filter(DocumentCTDPlacement.document_id == document.id).first()
    assert placement is not None
    assert placement.ctd_section_id == section_2_3.id
    assert placement.dossier_id == dossier.id


def test_create_product_and_application(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = make_role_with_permissions(
        db, organization=None, name="Creator",
        permissions=[(PermissionDomain.PRODUCT, PermissionAction.CREATE), (PermissionDomain.APPLICATION, PermissionAction.CREATE)],
    )
    user = make_user(db, organization=org, email="creator@acme.example")
    assign_role(db, user=user, organization=org, role=role)
    authority = make_authority(db)

    headers = login_headers(client, organization_slug="acme", email="creator@acme.example")
    product_response = client.post("/api/v1/products", headers=headers, json={"name": "Fictoprazole"})
    assert product_response.status_code == 201
    product_id = product_response.json()["id"]

    application_response = client.post(
        "/api/v1/applications",
        headers=headers,
        json={
            "product_id": product_id,
            "authority_id": str(authority.id),
            "country_region": authority.region,
            "application_type": "MARKETING_AUTHORIZATION",
        },
    )
    assert application_response.status_code == 201
    assert application_response.json()["product_id"] == product_id


def test_create_regulatory_activity_and_it_appears_on_the_timeline(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    role = make_role_with_permissions(
        db, organization=None, name="Activity Creator", permissions=[(PermissionDomain.ACTIVITY, PermissionAction.CREATE)]
    )
    user = make_user(db, organization=org, email="creator@acme.example")
    assign_role(db, user=user, organization=org, role=role)
    authority = make_authority(db)
    product, _, dossier = make_dossier_chain(db, organization=org, owner=user, authority=authority)

    headers = login_headers(client, organization_slug="acme", email="creator@acme.example")
    response = client.post(
        "/api/v1/activities",
        headers=headers,
        json={
            "product_id": str(product.id),
            "authority_id": str(authority.id),
            "activity_type": "INITIAL_SUBMISSION",
            "dossier_id": str(dossier.id),
        },
    )
    assert response.status_code == 201

    events = client.get(f"/api/v1/activities/events?dossier_id={dossier.id}", headers=headers)
    assert events.status_code == 200
    assert any(e["event_type"] == "ACTIVITY_CREATED" for e in events.json())
