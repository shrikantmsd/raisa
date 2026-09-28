from app.models.auth_event import AuthenticationEvent, AuthEventType

from tests.conftest import login_headers, make_organization, make_user


def test_login_success_returns_token_and_logs_event(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    make_user(db, organization=org, email="user@acme.example", password="CorrectHorse!1")

    response = client.post(
        "/api/v1/auth/login",
        json={"organization_slug": "acme", "email": "user@acme.example", "password": "CorrectHorse!1"},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()

    events = db.query(AuthenticationEvent).filter(AuthenticationEvent.organization_id == org.id).all()
    assert len(events) == 1
    assert events[0].event_type == AuthEventType.LOGIN_SUCCESS
    assert events[0].success is True


def test_login_failure_wrong_password_logs_event_and_does_not_leak_reason(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    make_user(db, organization=org, email="user@acme.example", password="CorrectHorse!1")

    response = client.post(
        "/api/v1/auth/login",
        json={"organization_slug": "acme", "email": "user@acme.example", "password": "WrongPassword"},
    )
    assert response.status_code == 401
    # Generic message — never "wrong password" vs "no such user", which
    # would let an attacker enumerate valid emails.
    assert response.json()["message"] == "Invalid credentials"

    events = db.query(AuthenticationEvent).filter(AuthenticationEvent.organization_id == org.id).all()
    assert len(events) == 1
    assert events[0].event_type == AuthEventType.LOGIN_FAILED
    assert events[0].success is False


def test_login_failure_unknown_organization_logs_event(db, client):
    response = client.post(
        "/api/v1/auth/login",
        json={"organization_slug": "does-not-exist", "email": "nobody@example.com", "password": "whatever"},
    )
    assert response.status_code == 401

    events = db.query(AuthenticationEvent).filter(AuthenticationEvent.organization_id.is_(None)).all()
    assert len(events) == 1
    assert events[0].event_type == AuthEventType.LOGIN_FAILED
    assert events[0].reason == "Unknown organization"


def test_me_endpoint_requires_authentication(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_endpoint_returns_current_user(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    make_user(db, organization=org, email="user@acme.example", password="CorrectHorse!1")
    headers = login_headers(client, organization_slug="acme", email="user@acme.example", password="CorrectHorse!1")

    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["email"] == "user@acme.example"


def test_logout_revokes_session_and_logs_event(db, client):
    org = make_organization(db, name="Acme Pharma", slug="acme")
    make_user(db, organization=org, email="user@acme.example", password="CorrectHorse!1")
    headers = login_headers(client, organization_slug="acme", email="user@acme.example", password="CorrectHorse!1")

    response = client.post("/api/v1/auth/logout", headers=headers)
    assert response.status_code == 200

    logout_events = (
        db.query(AuthenticationEvent).filter(AuthenticationEvent.event_type == AuthEventType.LOGOUT).all()
    )
    assert len(logout_events) == 1
