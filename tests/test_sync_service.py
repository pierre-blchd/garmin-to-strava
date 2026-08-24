from unittest.mock import MagicMock
from app import database
from app.sync_service import SyncService


def test_push_activity_to_strava_success():
    user = database.create_user("runner@test.com", "pass123")
    user_id = user["id"]

    database.upsert_activity(user_id, {
        "garmin_activity_id": "5555",
        "activity_name": "Course Nature 10km",
        "activity_type": "RUNNING",
        "sport_type_key": "running",
        "start_time": "2026-08-24T09:00:00",
        "distance_meters": 10000.0,
        "duration_seconds": 3000.0,
        "status": "not_synced"
    })

    sync = SyncService(user_id=user_id)
    sync.garmin.download_activity_file = MagicMock(return_value=(b"fit_content", "5555.fit"))
    sync.strava.upload_activity = MagicMock(return_value={"id": "upload_123"})
    sync.strava.poll_upload_until_complete = MagicMock(return_value=(True, "strava_987", None))

    result = sync.push_activity_to_strava("5555", custom_name="Course Nature 10km Modifiée")

    assert result["success"] is True
    assert result["strava_activity_id"] == "strava_987"
    assert result["strava_upload_id"] == "upload_123"

    act = database.get_activity(user_id, "5555")
    assert act["status"] == "synced"
    assert act["strava_activity_id"] == "strava_987"


def test_push_swimming_activity_manual_creation():
    user = database.create_user("swimmer@test.com", "pass123")
    user_id = user["id"]

    database.upsert_activity(user_id, {
        "garmin_activity_id": "6666",
        "activity_name": "Natation en bassin 1500m",
        "activity_type": "SWIMMING",
        "sport_type_key": "swimming",
        "start_time": "2026-08-24T12:00:00",
        "distance_meters": 0.0,
        "duration_seconds": 1800.0,
        "status": "not_synced"
    })

    sync = SyncService(user_id=user_id)
    sync.strava.create_manual_activity = MagicMock(return_value={
        "id": "strava_swim_111",
        "name": "Natation 1500m",
        "sport_type": "Swim"
    })

    result = sync.push_activity_to_strava("6666", custom_distance=1500.0)

    assert result["success"] is True
    assert result["strava_activity_id"] == "strava_swim_111"
    sync.strava.create_manual_activity.assert_called_once()
    
    act = database.get_activity(user_id, "6666")
    assert act["status"] == "synced"
    assert act["distance_meters"] == 1500.0
