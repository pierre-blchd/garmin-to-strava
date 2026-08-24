import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch
from app import database
from app.strava_client import StravaService


@pytest.fixture(autouse=True)
def setup_temp_db(monkeypatch):
    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test.db")
    monkeypatch.setattr(database, "DB_PATH", temp_db_path)
    database.init_db()
    yield
    if os.path.exists(temp_db_path):
        os.remove(temp_db_path)


def test_strava_authorization_url():
    user = database.create_user("athlete@example.com", "pass123")
    service = StravaService(user_id=user["id"])
    database.set_global_setting("strava_client_id", "123456")
    database.set_global_setting("strava_client_secret", "secret_abc")

    url = service.get_authorization_url()
    assert "https://www.strava.com/oauth/authorize" in url
    assert "client_id=123456" in url
    assert "state=" in url


def test_strava_exchange_code():
    user = database.create_user("athlete@example.com", "pass123")
    service = StravaService(user_id=user["id"])
    database.set_global_setting("strava_client_id", "123456")
    database.set_global_setting("strava_client_secret", "secret_abc")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "token_abc123",
        "refresh_token": "refresh_xyz456",
        "expires_at": 1800000000,
        "athlete": {
            "id": 99999,
            "firstname": "Pierre",
            "lastname": "B"
        }
    }

    with patch("requests.post", return_value=mock_response):
        data = service.exchange_code("code_test_123")
        assert data["access_token"] == "token_abc123"
        assert database.get_user_setting(user["id"], "strava_access_token") == "token_abc123"
        assert database.get_user_setting(user["id"], "strava_athlete_name") == "Pierre B"
