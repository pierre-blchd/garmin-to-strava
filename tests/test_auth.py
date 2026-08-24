import os
import tempfile
import pytest
from app import database
from app.auth import create_session_token, verify_session_token


@pytest.fixture(autouse=True)
def setup_temp_db(monkeypatch):
    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test.db")
    monkeypatch.setattr(database, "DB_PATH", temp_db_path)
    database.init_db()
    yield
    if os.path.exists(temp_db_path):
        os.remove(temp_db_path)


def test_password_hashing_and_verification():
    pw = "MonMotDePasseSecret123!"
    hashed = database.hash_password(pw)
    assert hashed != pw
    assert ":" in hashed

    assert database.verify_password(hashed, pw) is True
    assert database.verify_password(hashed, "MauvaisMotDePasse") is False


def test_user_creation_and_retrieval():
    user = database.create_user("test@example.com", "secret123", "Tester")
    assert user["id"] is not None
    assert user["email"] == "test@example.com"
    assert user["display_name"] == "Tester"

    by_email = database.get_user_by_email("test@example.com")
    assert by_email is not None
    assert by_email["id"] == user["id"]

    by_id = database.get_user_by_id(user["id"])
    assert by_id is not None
    assert by_id["email"] == "test@example.com"


def test_session_token_signing_and_verification():
    token = create_session_token(42)
    assert token is not None
    
    verified_id = verify_session_token(token)
    assert verified_id == 42

    # Tampered token
    tampered = token[:-4] + "abcd"
    assert verify_session_token(tampered) is None

    # Malformed token
    assert verify_session_token("invalid_token") is None
