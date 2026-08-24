import logging
from typing import Any, Dict, List, Optional

from app.database import (
    get_activity,
    update_activity_data,
    update_activity_sync_status,
    upsert_activities,
    upsert_activity,
)
from app.garmin_client import get_user_garmin_service
from app.strava_client import get_user_strava_service, map_garmin_to_strava_sport

logger = logging.getLogger(__name__)


class SyncService:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.garmin = get_user_garmin_service(user_id)
        self.strava = get_user_strava_service(user_id)

    def refresh_garmin_activities(self, limit: int = 50) -> Dict[str, Any]:
        """
        Fetches latest activities from Garmin and updates the local database for this user.
        """
        activities = self.garmin.fetch_activities(limit=limit)
        upsert_activities(self.user_id, activities)
        logger.info(f"Successfully refreshed and stored {len(activities)} Garmin activities for user {self.user_id}.")
        return {
            "success": True,
            "count": len(activities)
        }

    def push_activity_to_strava(
        self,
        garmin_activity_id: str,
        custom_name: Optional[str] = None,
        custom_description: Optional[str] = None,
        custom_distance: Optional[float] = None,
        custom_duration: Optional[float] = None,
        commute: int = 0,
        trainer: int = 0,
        upload_mode: str = "auto"
    ) -> Dict[str, Any]:
        """
        Pushes activity to Strava for this user.
        For swimming or when custom distance is specified without GPS, creates an activity via Strava API
        so Strava computes the exact distance and pace/100m.
        """
        activity = get_activity(self.user_id, garmin_activity_id)
        if not activity:
            raise ValueError(f"Activité {garmin_activity_id} introuvable dans la base locale.")

        # Update activity metadata in local DB if customized
        if custom_distance is not None or custom_duration is not None or custom_name is not None:
            update_activity_data(
                user_id=self.user_id,
                garmin_activity_id=garmin_activity_id,
                activity_name=custom_name,
                distance_meters=custom_distance,
                duration_seconds=custom_duration
            )
            activity = get_activity(self.user_id, garmin_activity_id)

        update_activity_sync_status(self.user_id, garmin_activity_id, status="uploading")

        activity_name = custom_name or activity.get("activity_name") or f"Garmin Activity {garmin_activity_id}"
        description = custom_description or f"Synchronisé depuis Garmin Connect (ID: {garmin_activity_id})"
        sport_key = (activity.get("sport_type_key") or activity.get("activity_type") or "").lower()
        is_swim = "swim" in sport_key or "natation" in sport_key

        # For swimming or custom distance without GPS track, use Strava API manual activity creation
        # to ensure Strava records the exact distance and calculates the pace/100m
        use_manual_creation = (
            upload_mode == "manual" or
            (upload_mode == "auto" and (is_swim or (custom_distance is not None and custom_distance > 0)))
        )

        try:
            if use_manual_creation:
                logger.info(f"Using Strava Activity creation for {garmin_activity_id} (is_swim={is_swim})...")
                sport_type = map_garmin_to_strava_sport(activity.get("activity_type") or sport_key)
                dist = float(custom_distance if custom_distance is not None else activity.get("distance_meters", 0.0))
                dur = int(custom_duration if custom_duration is not None else activity.get("duration_seconds", 0))

                create_resp = self.strava.create_manual_activity(
                    name=activity_name,
                    sport_type=sport_type,
                    start_date_local=activity.get("start_time", ""),
                    elapsed_time=dur,
                    distance_meters=dist,
                    description=description,
                    trainer=trainer,
                    commute=commute
                )

                strava_act_id = str(create_resp.get("id"))
                update_activity_sync_status(
                    user_id=self.user_id,
                    garmin_activity_id=garmin_activity_id,
                    status="synced",
                    strava_activity_id=strava_act_id
                )
                return {
                    "success": True,
                    "garmin_activity_id": garmin_activity_id,
                    "strava_activity_id": strava_act_id,
                    "strava_url": f"https://www.strava.com/activities/{strava_act_id}",
                    "message": f"Activité créée sur Strava ({dist}m) avec calcul de l'allure !"
                }

            # Standard FIT file upload for GPS sports
            logger.info(f"Downloading file for Garmin activity {garmin_activity_id} (user {self.user_id})...")
            file_bytes, filename = self.garmin.download_activity_file(garmin_activity_id)

            if not file_bytes:
                raise RuntimeError(f"Le fichier d'activité pour {garmin_activity_id} est vide.")

            logger.info(f"Uploading {filename} to Strava for user {self.user_id}...")
            upload_resp = self.strava.upload_activity(
                file_bytes=file_bytes,
                filename=filename,
                name=activity_name,
                description=description,
                trainer=trainer,
                commute=commute
            )

            upload_id = str(upload_resp.get("id"))
            logger.info(f"Strava upload started with upload_id: {upload_id}")

            success, strava_activity_id, error_msg = self.strava.poll_upload_until_complete(upload_id)

            if success:
                update_activity_sync_status(
                    user_id=self.user_id,
                    garmin_activity_id=garmin_activity_id,
                    status="synced",
                    strava_upload_id=upload_id,
                    strava_activity_id=strava_activity_id
                )
                return {
                    "success": True,
                    "garmin_activity_id": garmin_activity_id,
                    "strava_upload_id": upload_id,
                    "strava_activity_id": strava_activity_id,
                    "strava_url": f"https://www.strava.com/activities/{strava_activity_id}" if strava_activity_id else None,
                    "message": "Activité synchronisée avec succès sur Strava !"
                }
            else:
                update_activity_sync_status(
                    user_id=self.user_id,
                    garmin_activity_id=garmin_activity_id,
                    status="error",
                    strava_upload_id=upload_id,
                    error_message=error_msg
                )
                return {
                    "success": False,
                    "garmin_activity_id": garmin_activity_id,
                    "strava_upload_id": upload_id,
                    "error": error_msg
                }

        except Exception as e:
            err_msg = str(e)
            logger.exception(f"Error during Strava push for activity {garmin_activity_id}: {err_msg}")
            update_activity_sync_status(
                user_id=self.user_id,
                garmin_activity_id=garmin_activity_id,
                status="error",
                error_message=err_msg
            )
            return {
                "success": False,
                "garmin_activity_id": garmin_activity_id,
                "error": err_msg
            }

    def push_batch(self, garmin_activity_ids: List[str]) -> Dict[str, Any]:
        results = []
        for act_id in garmin_activity_ids:
            res = self.push_activity_to_strava(act_id)
            results.append(res)

        successful = sum(1 for r in results if r.get("success"))
        return {
            "total": len(garmin_activity_ids),
            "successful": successful,
            "failed": len(garmin_activity_ids) - successful,
            "details": results
        }


# Cache of per-user sync instances
_sync_services: Dict[int, SyncService] = {}

def get_user_sync_service(user_id: int) -> SyncService:
    if user_id not in _sync_services:
        _sync_services[user_id] = SyncService(user_id=user_id)
    return _sync_services[user_id]
