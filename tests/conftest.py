import os

# Point the app at a dedicated PostgreSQL test database *before* app.config/app.database
# are imported anywhere, so Settings() picks it up. Override with TEST_DATABASE_URL if your
# test database lives elsewhere.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://garmin_strava_app:GarminStrava_App_Pw_2026@localhost:5432/garmin_strava_test",
)

# Tests must be hermetic and not depend on the project's real .env (which may hold real
# Strava credentials for production). Settings() would otherwise still pick these up straight
# from the .env file even when unset in os.environ, so force them empty ("" is falsy) which
# makes StravaService fall back to the global_settings values each test writes to the DB itself.
os.environ["STRAVA_CLIENT_ID"] = ""
os.environ["STRAVA_CLIENT_SECRET"] = ""

import pytest
from app import database


@pytest.fixture(autouse=True)
def setup_temp_db():
    """
    Ensures a clean schema before every test and truncates all app tables
    afterwards, so tests never leak state into one another.
    """
    database.reset_pool()
    database.init_db()
    yield
    with database.get_db_cursor(commit=True) as cursor:
        cursor.execute("TRUNCATE TABLE activities, user_settings, global_settings, users RESTART IDENTITY CASCADE")
