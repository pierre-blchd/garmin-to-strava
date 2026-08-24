import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from app import database
from app.auth import create_session_token, SESSION_COOKIE_NAME
from main import app


@pytest.fixture(autouse=True)
def setup_temp_db(monkeypatch):
    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test.db")
    monkeypatch.setattr(database, "DB_PATH", temp_db_path)
    database.init_db()
    yield
    if os.path.exists(temp_db_path):
        os.remove(temp_db_path)


def test_auth_registration_and_login_flow():
    client = TestClient(app)

    # Register
    resp_reg = client.post("/api/auth/register", json={
        "email": "pierre@example.com",
        "password": "superpassword123",
        "display_name": "Pierre B"
    })
    assert resp_reg.status_code == 200
    data_reg = resp_reg.json()
    assert data_reg["success"] is True
    assert data_reg["user"]["email"] == "pierre@example.com"
    assert SESSION_COOKIE_NAME in resp_reg.cookies

    # Me endpoint with cookie
    resp_me = client.get("/api/auth/me", cookies={SESSION_COOKIE_NAME: resp_reg.cookies[SESSION_COOKIE_NAME]})
    assert resp_me.status_code == 200
    assert resp_me.json()["email"] == "pierre@example.com"

    # Logout
    resp_logout = client.post("/api/auth/logout")
    assert resp_logout.status_code == 200


def test_protected_routes_unauthenticated():
    client = TestClient(app, follow_redirects=False)

    # Unauthenticated access to / should redirect to /login
    resp_index = client.get("/")
    assert resp_index.status_code in [302, 307]
    assert "/login" in resp_index.headers.get("location", "")

    # Unauthenticated API access should return 401
    resp_api = client.get("/api/status")
    assert resp_api.status_code == 401


def test_user_isolated_activities_api():
    client = TestClient(app)

    # Create user 1
    u1 = database.create_user("u1@test.com", "pass123", "User 1")
    token1 = create_session_token(u1["id"])

    # Create user 2
    u2 = database.create_user("u2@test.com", "pass123", "User 2")
    token2 = create_session_token(u2["id"])

    # User 1 inserts an activity
    database.upsert_activity(u1["id"], {
        "garmin_activity_id": "777",
        "activity_name": "Course User 1",
        "activity_type": "RUNNING",
        "sport_type_key": "running",
        "start_time": "2026-08-24T18:00:00",
        "distance_meters": 5000.0,
        "duration_seconds": 1500.0,
        "status": "not_synced"
    })

    # User 1 lists activities
    resp1 = client.get("/api/activities", cookies={SESSION_COOKIE_NAME: token1})
    assert resp1.status_code == 200
    assert resp1.json()["total"] == 1
    assert resp1.json()["activities"][0]["garmin_activity_id"] == "777"

    # User 2 lists activities (should be empty!)
    resp2 = client.get("/api/activities", cookies={SESSION_COOKIE_NAME: token2})
    assert resp2.status_code == 200
    assert resp2.json()["total"] == 0
    assert len(resp2.json()["activities"]) == 0
