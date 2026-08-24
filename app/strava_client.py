import time
import urllib.parse
import logging
import requests
from typing import Any, Dict, Optional, Tuple

from app.config import settings
from app.database import (
    get_global_setting,
    get_user_setting,
    set_user_setting,
    delete_user_setting,
)
from app.auth import create_session_token, verify_session_token

logger = logging.getLogger(__name__)

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE_URL = "https://www.strava.com/api/v3"


class StravaService:
    def __init__(self, user_id: int):
        self.user_id = user_id

    @property
    def client_id(self) -> Optional[str]:
        return settings.STRAVA_CLIENT_ID or get_global_setting("strava_client_id")

    @property
    def client_secret(self) -> Optional[str]:
        return settings.STRAVA_CLIENT_SECRET or get_global_setting("strava_client_secret")

    @property
    def redirect_uri(self) -> str:
        return settings.STRAVA_REDIRECT_URI or get_global_setting("strava_redirect_uri")

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def is_authenticated(self) -> bool:
        return bool(
            get_user_setting(self.user_id, "strava_access_token") and
            get_user_setting(self.user_id, "strava_refresh_token")
        )

    def get_athlete_name(self) -> Optional[str]:
        return get_user_setting(self.user_id, "strava_athlete_name")

    def get_authorization_url(self) -> str:
        if not self.is_configured():
            raise ValueError("Strava Client ID et Client Secret doivent être configurés par l'administrateur.")

        # Sign the user_id into the OAuth state to securely correlate on callback
        state_token = create_session_token(self.user_id)

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "approval_prompt": "auto",
            "scope": "read,activity:write,activity:read_all",
            "state": state_token
        }
        return f"{STRAVA_AUTH_URL}?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code: str) -> Dict[str, Any]:
        """
        Exchanges temporary authorization code for access & refresh tokens.
        """
        if not self.is_configured():
            raise ValueError("Strava Client ID et Client Secret non configurés.")

        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code"
        }

        resp = requests.post(STRAVA_TOKEN_URL, data=payload, timeout=15)
        if resp.status_code != 200:
            logger.error(f"Failed to exchange Strava token for user {self.user_id}: {resp.status_code} - {resp.text}")
            raise RuntimeError(f"Erreur d'autorisation Strava ({resp.status_code}) : {resp.text}")

        data = resp.json()
        self._save_token_data(data)
        return data

    def refresh_access_token(self) -> str:
        """
        Refreshes expired access token using refresh_token.
        """
        refresh_token = get_user_setting(self.user_id, "strava_refresh_token")
        if not refresh_token:
            raise RuntimeError("Aucun refresh token Strava disponible. Veuillez vous reconnecter à Strava.")

        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }

        resp = requests.post(STRAVA_TOKEN_URL, data=payload, timeout=15)
        if resp.status_code != 200:
            logger.error(f"Failed to refresh Strava token for user {self.user_id}: {resp.status_code} - {resp.text}")
            raise RuntimeError(f"Impossible de rafraîchir le token Strava : {resp.text}")

        data = resp.json()
        self._save_token_data(data)
        return data["access_token"]

    def _save_token_data(self, data: Dict[str, Any]):
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        expires_at = data.get("expires_at", 0)
        
        if access_token:
            set_user_setting(self.user_id, "strava_access_token", access_token)
        if refresh_token:
            set_user_setting(self.user_id, "strava_refresh_token", refresh_token)
        if expires_at:
            set_user_setting(self.user_id, "strava_expires_at", str(expires_at))

        athlete = data.get("athlete")
        if athlete:
            name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip()
            if name:
                set_user_setting(self.user_id, "strava_athlete_name", name)
            if athlete.get("id"):
                set_user_setting(self.user_id, "strava_athlete_id", str(athlete.get("id")))

    def disconnect(self):
        delete_user_setting(self.user_id, "strava_access_token")
        delete_user_setting(self.user_id, "strava_refresh_token")
        delete_user_setting(self.user_id, "strava_expires_at")
        delete_user_setting(self.user_id, "strava_athlete_name")
        delete_user_setting(self.user_id, "strava_athlete_id")

    def get_valid_access_token(self) -> str:
        """
        Returns a guaranteed valid access token, auto-refreshing if expired.
        """
        access_token = get_user_setting(self.user_id, "strava_access_token")
        expires_at_str = get_user_setting(self.user_id, "strava_expires_at")
        
        if not access_token:
            raise RuntimeError("Non connecté à Strava. Veuillez autoriser l'application.")

        expires_at = int(expires_at_str) if expires_at_str else 0
        if time.time() >= (expires_at - 300):
            logger.info(f"Strava access token for user {self.user_id} expired or expiring soon. Refreshing...")
            access_token = self.refresh_access_token()

        return access_token

    def upload_activity(
        self,
        file_bytes: bytes,
        filename: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        trainer: int = 0,
        commute: int = 0,
        activity_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Uploads an activity file (FIT, GPX, TCX) to Strava API.
        Returns: raw upload object from Strava.
        """
        token = self.get_valid_access_token()
        
        ext = filename.split(".")[-1].lower()
        if ext not in ["fit", "gpx", "tcx", "gz"]:
            ext = "fit"

        files = {
            "file": (filename, file_bytes, "application/octet-stream")
        }
        
        data: Dict[str, Any] = {
            "data_type": ext,
            "trainer": trainer,
            "commute": commute
        }
        if name:
            data["name"] = name
        if description:
            data["description"] = description
        if activity_type:
            data["activity_type"] = activity_type

        headers = {
            "Authorization": f"Bearer {token}"
        }

        url = f"{STRAVA_API_BASE_URL}/uploads"
        logger.info(f"Uploading file {filename} to Strava for user {self.user_id} ({url})...")
        resp = requests.post(url, headers=headers, data=data, files=files, timeout=60)
        
        if resp.status_code not in [200, 201, 202]:
            err_msg = f"Erreur Strava Upload ({resp.status_code}): {resp.text}"
            logger.error(err_msg)
            raise RuntimeError(err_msg)

        return resp.json()

    def create_manual_activity(
        self,
        name: str,
        sport_type: str,
        start_date_local: str,
        elapsed_time: int,
        distance_meters: float,
        description: Optional[str] = None,
        trainer: int = 0,
        commute: int = 0
    ) -> Dict[str, Any]:
        """
        Creates a manual activity directly on Strava API with exact distance and time.
        Perfect for indoor swimming, treadmill or non-GPS workouts so Strava computes pace/100m.
        """
        token = self.get_valid_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # Normalize start_date_local to ISO 8601
        formatted_date = start_date_local
        if formatted_date and not (formatted_date.endswith("Z") or "+" in formatted_date or "-" in formatted_date[-6:]):
            formatted_date = f"{formatted_date}Z"

        payload: Dict[str, Any] = {
            "name": name,
            "sport_type": sport_type,
            "start_date_local": formatted_date,
            "elapsed_time": max(int(elapsed_time), 1),
            "distance": max(float(distance_meters), 0.0),
            "trainer": trainer,
            "commute": commute
        }
        if description:
            payload["description"] = description

        url = f"{STRAVA_API_BASE_URL}/activities"
        logger.info(f"Creating manual Strava activity '{name}' ({sport_type}, {distance_meters}m) for user {self.user_id}...")
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if resp.status_code not in [200, 201]:
            err_msg = f"Erreur Strava Manual Activity ({resp.status_code}): {resp.text}"
            logger.error(err_msg)
            raise RuntimeError(err_msg)

        return resp.json()

    def check_upload_status(self, upload_id: str) -> Dict[str, Any]:
        token = self.get_valid_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{STRAVA_API_BASE_URL}/uploads/{upload_id}"

        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(f"Erreur lors de la vérification de l'upload {upload_id}: {resp.text}")

        return resp.json()

    def poll_upload_until_complete(self, upload_id: str, max_retries: int = 15, delay: float = 2.0) -> Tuple[bool, Optional[str], Optional[str]]:
        for _ in range(max_retries):
            info = self.check_upload_status(upload_id)
            error = info.get("error")
            status_text = info.get("status", "")
            activity_id = info.get("activity_id")

            if error:
                return False, None, f"Erreur Strava: {error}"

            if activity_id:
                return True, str(activity_id), None

            if "ready" in status_text.lower():
                return True, str(activity_id) if activity_id else None, None

            if "error" in status_text.lower():
                return False, None, status_text

            time.sleep(delay)

        return False, None, "Délai d'attente de traitement Strava dépassé."


# Cache of per-user service instances
_strava_services: Dict[int, StravaService] = {}

def get_user_strava_service(user_id: int) -> StravaService:
    if user_id not in _strava_services:
        _strava_services[user_id] = StravaService(user_id=user_id)
    return _strava_services[user_id]


def map_garmin_to_strava_sport(garmin_type: str) -> str:
    t = (garmin_type or "").lower()
    if "swim" in t or "natation" in t:
        return "Swim"
    elif "run" in t or "course" in t or "jog" in t:
        return "Run"
    elif "bik" in t or "cycl" in t or "velo" in t or "ride" in t:
        return "Ride"
    elif "walk" in t or "marche" in t:
        return "Walk"
    elif "hik" in t or "rando" in t:
        return "Hike"
    elif "fit" in t or "strength" in t or "muscu" in t or "weight" in t:
        return "WeightTraining"
    return "Workout"

