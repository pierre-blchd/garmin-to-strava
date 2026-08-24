from app import database


def test_user_and_global_settings():
    # Global settings
    database.set_global_setting("strava_client_id", "123456")
    assert database.get_global_setting("strava_client_id") == "123456"

    # User settings
    user1 = database.create_user("user1@example.com", "pass123")
    user2 = database.create_user("user2@example.com", "pass456")

    database.set_user_setting(user1["id"], "garmin_email", "garmin1@test.com")
    database.set_user_setting(user2["id"], "garmin_email", "garmin2@test.com")

    assert database.get_user_setting(user1["id"], "garmin_email") == "garmin1@test.com"
    assert database.get_user_setting(user2["id"], "garmin_email") == "garmin2@test.com"

    database.delete_user_setting(user1["id"], "garmin_email")
    assert database.get_user_setting(user1["id"], "garmin_email") is None
    assert database.get_user_setting(user2["id"], "garmin_email") == "garmin2@test.com"


def test_activity_multi_user_isolation():
    user1 = database.create_user("u1@test.com", "pass123")
    user2 = database.create_user("u2@test.com", "pass123")

    sample_act1 = {
        "garmin_activity_id": "1001",
        "activity_name": "Sortie vélo User 1",
        "activity_type": "CYCLING",
        "sport_type_key": "cycling",
        "start_time": "2026-08-24T08:00:00",
        "distance_meters": 25000.0,
        "duration_seconds": 3600.0,
        "status": "not_synced"
    }

    sample_act2 = {
        "garmin_activity_id": "2002",
        "activity_name": "Course User 2",
        "activity_type": "RUNNING",
        "sport_type_key": "running",
        "start_time": "2026-08-24T09:00:00",
        "distance_meters": 10000.0,
        "duration_seconds": 3000.0,
        "status": "not_synced"
    }

    database.upsert_activity(user1["id"], sample_act1)
    database.upsert_activity(user2["id"], sample_act2)

    # User 1 should only see activity 1001
    acts1 = database.list_activities(user_id=user1["id"])
    assert len(acts1) == 1
    assert acts1[0]["garmin_activity_id"] == "1001"
    assert database.get_activity(user1["id"], "2002") is None

    # User 2 should only see activity 2002
    acts2 = database.list_activities(user_id=user2["id"])
    assert len(acts2) == 1
    assert acts2[0]["garmin_activity_id"] == "2002"
    assert database.get_activity(user2["id"], "1001") is None

    stats1 = database.get_sync_stats(user1["id"])
    assert stats1["total"] == 1
    stats2 = database.get_sync_stats(user2["id"])
    assert stats2["total"] == 1
