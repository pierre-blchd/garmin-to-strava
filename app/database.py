import hashlib
import hmac
import secrets
import json
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras
import psycopg2.pool
from psycopg2 import errors as pg_errors

from app.config import settings

# --- Connection Pool (PostgreSQL) ---

_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            settings.DB_POOL_MIN_CONN,
            settings.DB_POOL_MAX_CONN,
            dsn=settings.database_dsn,
        )
    return _pool


def reset_pool():
    """Closes and discards the current pool so a new DSN can take effect (used by tests)."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


@contextmanager
def get_db_cursor(commit: bool = False):
    """
    Borrows a connection from the pool, yields a RealDictCursor, commits on
    success if requested, rolls back on error, and always returns the
    connection to the pool (never leaks connections).
    """
    pool = _get_pool()
    conn = pool.getconn()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield cursor
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


# --- Password Hashing with PBKDF2-HMAC-SHA256 ---

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 600000)
    return f"{salt}:{pw_hash.hex()}"


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        salt, pw_hash = stored_hash.split(":", 1)
        check_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 600000)
        return hmac.compare_digest(check_hash.hex(), pw_hash)
    except Exception:
        return False


def init_db():
    with get_db_cursor(commit=True) as cursor:
        # 1. Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 2. Global settings (Strava App Client ID / Secret configured for the server)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS global_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 3. User settings (per-user Strava tokens, athlete info, Garmin email)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, key),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # 4. Activities table (scoped by user_id)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                user_id INTEGER NOT NULL,
                garmin_activity_id TEXT NOT NULL,
                activity_name TEXT NOT NULL,
                activity_type TEXT NOT NULL,
                sport_type_key TEXT,
                start_time TEXT NOT NULL,
                distance_meters DOUBLE PRECISION DEFAULT 0.0,
                duration_seconds DOUBLE PRECISION DEFAULT 0.0,
                elevation_gain_meters DOUBLE PRECISION DEFAULT 0.0,
                average_hr DOUBLE PRECISION,
                max_hr DOUBLE PRECISION,
                calories DOUBLE PRECISION,
                status TEXT DEFAULT 'not_synced', -- 'not_synced', 'uploading', 'synced', 'error'
                strava_upload_id TEXT,
                strava_activity_id TEXT,
                error_message TEXT,
                synced_at TEXT,
                raw_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, garmin_activity_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_activities_user_start_time ON activities(user_id, start_time DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_activities_user_status ON activities(user_id, status)")


# --- User Management Helpers ---

def create_user(email: str, password: str, display_name: Optional[str] = None) -> Dict[str, Any]:
    email_clean = email.strip().lower()
    pw_hash = hash_password(password)
    name = display_name.strip() if display_name else email_clean.split("@")[0]

    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute("""
                INSERT INTO users (email, password_hash, display_name)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (email_clean, pw_hash, name))
            user_id = cursor.fetchone()["id"]

            return {
                "id": user_id,
                "email": email_clean,
                "display_name": name
            }
    except pg_errors.UniqueViolation as e:
        raise ValueError(f"Email '{email_clean}' already registered.") from e


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM users WHERE LOWER(email) = %s", (email.strip().lower(),))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


# --- Global Settings Helpers ---

def get_global_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    with get_db_cursor() as cursor:
        cursor.execute("SELECT value FROM global_settings WHERE key = %s", (key,))
        row = cursor.fetchone()
        return row["value"] if row else default


def set_global_setting(key: str, value: str):
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("""
            INSERT INTO global_settings (key, value, updated_at)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
        """, (key, value))


# --- Per-User Settings Helpers ---

def get_user_setting(user_id: int, key: str, default: Optional[str] = None) -> Optional[str]:
    with get_db_cursor() as cursor:
        cursor.execute("SELECT value FROM user_settings WHERE user_id = %s AND key = %s", (user_id, key))
        row = cursor.fetchone()
        return row["value"] if row else default


def set_user_setting(user_id: int, key: str, value: str):
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("""
            INSERT INTO user_settings (user_id, key, value, updated_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
        """, (user_id, key, value))


def delete_user_setting(user_id: int, key: str):
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("DELETE FROM user_settings WHERE user_id = %s AND key = %s", (user_id, key))


def get_all_user_settings(user_id: int) -> Dict[str, str]:
    with get_db_cursor() as cursor:
        cursor.execute("SELECT key, value FROM user_settings WHERE user_id = %s", (user_id,))
        return {row["key"]: row["value"] for row in cursor.fetchall()}


# --- Per-User Activities Helpers ---

def upsert_activity(user_id: int, act: Dict[str, Any]):
    with get_db_cursor(commit=True) as cursor:
        # Check if activity already exists for this user to preserve sync status
        cursor.execute("""
            SELECT status, strava_activity_id, strava_upload_id, synced_at
            FROM activities
            WHERE user_id = %s AND garmin_activity_id = %s
        """, (user_id, str(act["garmin_activity_id"])))
        existing = cursor.fetchone()

        status = existing["status"] if existing else act.get("status", "not_synced")
        strava_activity_id = existing["strava_activity_id"] if existing else act.get("strava_activity_id")
        strava_upload_id = existing["strava_upload_id"] if existing else act.get("strava_upload_id")
        synced_at = existing["synced_at"] if existing else act.get("synced_at")

        raw_json_str = json.dumps(act.get("raw_json", {})) if isinstance(act.get("raw_json"), (dict, list)) else act.get("raw_json", "{}")

        cursor.execute("""
            INSERT INTO activities (
                user_id, garmin_activity_id, activity_name, activity_type, sport_type_key,
                start_time, distance_meters, duration_seconds, elevation_gain_meters,
                average_hr, max_hr, calories, status, strava_upload_id,
                strava_activity_id, error_message, synced_at, raw_json, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, garmin_activity_id) DO UPDATE SET
                activity_name = excluded.activity_name,
                activity_type = excluded.activity_type,
                sport_type_key = excluded.sport_type_key,
                start_time = excluded.start_time,
                distance_meters = excluded.distance_meters,
                duration_seconds = excluded.duration_seconds,
                elevation_gain_meters = excluded.elevation_gain_meters,
                average_hr = excluded.average_hr,
                max_hr = excluded.max_hr,
                calories = excluded.calories,
                raw_json = excluded.raw_json,
                updated_at = CURRENT_TIMESTAMP
        """, (
            user_id,
            str(act["garmin_activity_id"]),
            act.get("activity_name", "Activité Garmin"),
            act.get("activity_type", "OTHER"),
            act.get("sport_type_key", ""),
            act.get("start_time", datetime.now().isoformat()),
            float(act.get("distance_meters") or 0.0),
            float(act.get("duration_seconds") or 0.0),
            float(act.get("elevation_gain_meters") or 0.0),
            act.get("average_hr"),
            act.get("max_hr"),
            act.get("calories"),
            status,
            strava_upload_id,
            strava_activity_id,
            act.get("error_message"),
            synced_at,
            raw_json_str
        ))


def upsert_activities(user_id: int, activities: List[Dict[str, Any]]):
    for act in activities:
        upsert_activity(user_id, act)


def get_activity(user_id: int, garmin_activity_id: str) -> Optional[Dict[str, Any]]:
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM activities WHERE user_id = %s AND garmin_activity_id = %s", (user_id, str(garmin_activity_id)))
        row = cursor.fetchone()
        return dict(row) if row else None


def list_activities(
    user_id: int,
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    activity_type: Optional[str] = None,
    search: Optional[str] = None
) -> List[Dict[str, Any]]:
    with get_db_cursor() as cursor:
        query = "SELECT * FROM activities WHERE user_id = %s"
        params: List[Any] = [user_id]

        if status and status != "all":
            query += " AND status = %s"
            params.append(status)

        if activity_type and activity_type != "all":
            query += " AND (activity_type ILIKE %s OR sport_type_key ILIKE %s)"
            params.append(f"%{activity_type}%")
            params.append(f"%{activity_type}%")

        if search:
            query += " AND (activity_name ILIKE %s OR garmin_activity_id ILIKE %s)"
            params.append(f"%{search}%")
            params.append(f"%{search}%")

        query += " ORDER BY start_time DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def count_activities(
    user_id: int,
    status: Optional[str] = None,
    activity_type: Optional[str] = None,
    search: Optional[str] = None
) -> int:
    with get_db_cursor() as cursor:
        query = "SELECT COUNT(*) as total FROM activities WHERE user_id = %s"
        params: List[Any] = [user_id]

        if status and status != "all":
            query += " AND status = %s"
            params.append(status)

        if activity_type and activity_type != "all":
            query += " AND (activity_type ILIKE %s OR sport_type_key ILIKE %s)"
            params.append(f"%{activity_type}%")
            params.append(f"%{activity_type}%")

        if search:
            query += " AND (activity_name ILIKE %s OR garmin_activity_id ILIKE %s)"
            params.append(f"%{search}%")
            params.append(f"%{search}%")

        cursor.execute(query, params)
        row = cursor.fetchone()
        return row["total"] if row else 0


def update_activity_sync_status(
    user_id: int,
    garmin_activity_id: str,
    status: str,
    strava_upload_id: Optional[str] = None,
    strava_activity_id: Optional[str] = None,
    error_message: Optional[str] = None
):
    with get_db_cursor(commit=True) as cursor:
        synced_at = datetime.now().isoformat() if status == "synced" else None

        cursor.execute("""
            UPDATE activities
            SET status = %s,
                strava_upload_id = COALESCE(%s, strava_upload_id),
                strava_activity_id = COALESCE(%s, strava_activity_id),
                error_message = %s,
                synced_at = CASE WHEN %s = 'synced' THEN COALESCE(synced_at, %s) ELSE synced_at END,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s AND garmin_activity_id = %s
        """, (
            status,
            strava_upload_id,
            strava_activity_id,
            error_message,
            status,
            synced_at,
            user_id,
            str(garmin_activity_id)
        ))


def update_activity_data(
    user_id: int,
    garmin_activity_id: str,
    activity_name: Optional[str] = None,
    distance_meters: Optional[float] = None,
    duration_seconds: Optional[float] = None
):
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("""
            UPDATE activities
            SET activity_name = COALESCE(%s, activity_name),
                distance_meters = COALESCE(%s, distance_meters),
                duration_seconds = COALESCE(%s, duration_seconds),
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s AND garmin_activity_id = %s
        """, (
            activity_name,
            distance_meters,
            duration_seconds,
            user_id,
            str(garmin_activity_id)
        ))


def get_sync_stats(user_id: int) -> Dict[str, int]:
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'synced' THEN 1 ELSE 0 END) as synced,
                SUM(CASE WHEN status = 'not_synced' THEN 1 ELSE 0 END) as not_synced,
                SUM(CASE WHEN status = 'uploading' THEN 1 ELSE 0 END) as uploading,
                SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error
            FROM activities
            WHERE user_id = %s
        """, (user_id,))
        row = cursor.fetchone()
        return {
            "total": row["total"] or 0,
            "synced": row["synced"] or 0,
            "not_synced": row["not_synced"] or 0,
            "uploading": row["uploading"] or 0,
            "error": row["error"] or 0
        }
