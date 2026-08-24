import io
import os
import zipfile
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from app.config import GARMIN_TOKENS_DIR, settings
from app.database import get_user_setting, set_user_setting, delete_user_setting

logger = logging.getLogger(__name__)


class GarminService:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.client: Optional[Garmin] = None
        self.tokens_path = GARMIN_TOKENS_DIR / str(user_id)
        self.tokens_path.mkdir(parents=True, exist_ok=True)
        self._email: Optional[str] = None

    @property
    def email(self) -> Optional[str]:
        return self._email or get_user_setting(self.user_id, "garmin_email")

    def is_authenticated(self) -> bool:
        return self.client is not None

    def init_session(self) -> bool:
        """
        Attempts to restore a cached session token from disk without needing credentials.
        """
        token_dir_str = str(self.tokens_path)
        try:
            if not os.path.exists(token_dir_str) or not os.listdir(token_dir_str):
                return False

            client = Garmin()
            client.login(token_dir_str)
            self.client = client
            logger.info(f"Garmin session restored from cached tokens for user {self.user_id}.")
            return True
        except Exception as e:
            logger.warning(f"Could not restore Garmin session for user {self.user_id}: {e}")
            self.client = None
            return False

    def login(self, email: str, password: str) -> Tuple[bool, Optional[str]]:
        """
        Logs into Garmin Connect using email & password, saving tokens to disk for this user.
        Returns: (success: bool, error_message: Optional[str])
        """
        try:
            token_dir_str = str(self.tokens_path)
            client = Garmin(email=email, password=password)
            
            # Pass token directory to login for automatic token storage
            try:
                client.login(token_dir_str)
            except Exception:
                client.login()
                if hasattr(client, "dump"):
                    try:
                        client.dump(token_dir_str)
                    except Exception:
                        pass
                elif hasattr(client, "garth") and hasattr(client.garth, "dump"):
                    try:
                        client.garth.dump(token_dir_str)
                    except Exception:
                        pass

            self.client = client
            self._email = email
            set_user_setting(self.user_id, "garmin_email", email)
            logger.info(f"Garmin login successful for user {self.user_id} ({email})")
            return True, None
        except GarminConnectAuthenticationError as auth_err:
            msg = f"Erreur d'authentification Garmin : {auth_err}"
            logger.error(msg)
            return False, msg
        except GarminConnectTooManyRequestsError:
            msg = "Trop de requêtes vers Garmin Connect. Veuillez patienter quelques minutes."
            logger.error(msg)
            return False, msg
        except GarminConnectConnectionError as conn_err:
            msg = f"Erreur de connexion aux serveurs Garmin : {conn_err}"
            logger.error(msg)
            return False, msg
        except Exception as e:
            msg = f"Erreur inattendue lors de la connexion Garmin : {str(e)}"
            logger.exception(msg)
            return False, msg

    def logout(self):
        """Logs out and clears saved tokens for this user."""
        self.client = None
        self._email = None
        delete_user_setting(self.user_id, "garmin_email")
        if self.tokens_path.exists():
            for f in self.tokens_path.glob("*"):
                try:
                    if f.is_file():
                        f.unlink()
                except Exception as e:
                    logger.warning(f"Could not delete token file {f}: {e}")

    def fetch_activities(self, limit: int = 50, start: int = 0) -> List[Dict[str, Any]]:
        """
        Fetches recent activities from Garmin Connect and normalizes metadata.
        """
        if not self.is_authenticated():
            if not self.init_session():
                raise RuntimeError("Non connecté à Garmin Connect. Veuillez vous connecter d'abord.")

        raw_activities = self.client.get_activities(start, limit)
        normalized = []

        for item in raw_activities:
            activity_id = str(item.get("activityId"))
            activity_name = item.get("activityName") or "Activité Garmin"
            
            activity_type_dict = item.get("activityType") or {}
            sport_type = activity_type_dict.get("typeKey", "other")
            
            start_time = item.get("startTimeLocal") or item.get("startTimeGMT") or ""
            distance = item.get("distance", 0.0)
            duration = item.get("duration") or item.get("elapsedDuration") or 0.0
            elevation = item.get("elevationGain") or item.get("totalElevationGain") or 0.0
            avg_hr = item.get("averageHR")
            max_hr = item.get("maxHR")
            calories = item.get("calories")

            normalized.append({
                "garmin_activity_id": activity_id,
                "activity_name": activity_name,
                "activity_type": sport_type.upper(),
                "sport_type_key": sport_type.lower(),
                "start_time": start_time,
                "distance_meters": distance,
                "duration_seconds": duration,
                "elevation_gain_meters": elevation,
                "average_hr": avg_hr,
                "max_hr": max_hr,
                "calories": calories,
                "raw_json": item
            })

        return normalized

    def download_activity_file(self, activity_id: str) -> Tuple[bytes, str]:
        """
        Downloads activity file from Garmin.
        Tries ORIGINAL (.fit zipped or unzipped), fallback to GPX/TCX.
        Returns: (file_bytes: bytes, file_name: str)
        """
        if not self.is_authenticated():
            if not self.init_session():
                raise RuntimeError("Non connecté à Garmin Connect.")

        # 1. Try download ORIGINAL
        try:
            data = self.client.download_activity(activity_id, dl_fmt=self.client.ActivityDownloadFormat.ORIGINAL)
            
            if data and data[:4] == b"PK\x03\x04":
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    for filename in z.namelist():
                        if filename.lower().endswith(".fit"):
                            fit_data = z.read(filename)
                            return fit_data, f"{activity_id}.fit"
                    if z.namelist():
                        first_file = z.namelist()[0]
                        return z.read(first_file), first_file
            
            return data, f"{activity_id}.fit"
        except Exception as orig_err:
            logger.warning(f"Failed to download ORIGINAL format for activity {activity_id}: {orig_err}. Trying GPX...")

        # 2. Fallback to GPX
        try:
            gpx_data = self.client.download_activity(activity_id, dl_fmt=self.client.ActivityDownloadFormat.GPX)
            return gpx_data, f"{activity_id}.gpx"
        except Exception as gpx_err:
            logger.warning(f"Failed to download GPX format for activity {activity_id}: {gpx_err}. Trying TCX...")

        # 3. Fallback to TCX
        tcx_data = self.client.download_activity(activity_id, dl_fmt=self.client.ActivityDownloadFormat.TCX)
        return tcx_data, f"{activity_id}.tcx"


# Cache of per-user service instances
_garmin_services: Dict[int, GarminService] = {}

def get_user_garmin_service(user_id: int) -> GarminService:
    if user_id not in _garmin_services:
        _garmin_services[user_id] = GarminService(user_id=user_id)
    return _garmin_services[user_id]
