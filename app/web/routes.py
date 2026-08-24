import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr

from app.config import BASE_DIR, settings
from app.auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    create_session_token,
    get_current_user,
    get_current_user_optional,
    verify_session_token,
)
from app.database import (
    count_activities,
    create_user,
    get_global_setting,
    get_sync_stats,
    get_user_by_email,
    get_user_by_id,
    list_activities,
    set_global_setting,
    verify_password,
)
from app.garmin_client import get_user_garmin_service
from app.strava_client import get_user_strava_service
from app.sync_service import get_user_sync_service

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "web" / "templates"))


# --- Pydantic Request Models ---

class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: Optional[str] = None


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class GarminLoginRequest(BaseModel):
    email: str
    password: str


class PushActivityRequest(BaseModel):
    custom_name: Optional[str] = None
    custom_description: Optional[str] = None
    custom_distance: Optional[float] = None  # in meters
    custom_duration: Optional[float] = None  # in seconds
    commute: int = 0
    trainer: int = 0
    upload_mode: Optional[str] = "auto"  # "auto", "manual", "fit"


class UpdateActivityRequest(BaseModel):
    activity_name: Optional[str] = None
    distance_meters: Optional[float] = None
    duration_seconds: Optional[float] = None


class BatchPushRequest(BaseModel):
    activity_ids: List[str]


# --- Favicon ---

@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


# --- Authentication HTML Views ---

@router.get("/login", response_class=HTMLResponse)
async def login_view(request: Request):
    user = get_current_user_optional(request)
    if user:
        return RedirectResponse(url="/")
    return templates.TemplateResponse(request=request, name="login.html")


@router.get("/register", response_class=HTMLResponse)
async def register_view(request: Request):
    user = get_current_user_optional(request)
    if user:
        return RedirectResponse(url="/")
    return templates.TemplateResponse(request=request, name="register.html")


# --- Main Web Page Views (Protected) ---

@router.get("/", response_class=HTMLResponse)
async def index_view(request: Request, user: Dict[str, Any] = Depends(get_current_user)):
    return templates.TemplateResponse(request=request, name="index.html", context={"user": user})


@router.get("/settings", response_class=HTMLResponse)
async def settings_view(request: Request, user: Dict[str, Any] = Depends(get_current_user)):
    return templates.TemplateResponse(request=request, name="settings.html", context={"user": user})


# --- Authentication API Endpoints ---

@router.post("/api/auth/register")
async def auth_register(data: UserRegisterRequest, response: Response):
    """
    Registers a new user and signs them in via session cookie.
    """
    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="Le mot de passe doit comporter au moins 6 caractères.")

    try:
        user = create_user(
            email=data.email,
            password=data.password,
            display_name=data.display_name
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    session_token = create_session_token(user["id"])
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE
    )

    return {
        "success": True,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"]
        }
    }


@router.post("/api/auth/login")
async def auth_login(data: UserLoginRequest, response: Response):
    """
    Authenticates user and sets session cookie.
    """
    user = get_user_by_email(data.email)
    if not user:
        raise HTTPException(status_code=400, detail="Email ou mot de passe incorrect.")

    if not verify_password(user["password_hash"], data.password):
        raise HTTPException(status_code=400, detail="Email ou mot de passe incorrect.")

    session_token = create_session_token(user["id"])
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE
    )

    return {
        "success": True,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user.get("display_name")
        }
    }


@router.post("/api/auth/logout")
async def auth_logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"success": True, "message": "Déconnexion réussie."}


@router.get("/api/auth/me")
async def auth_me(user: Dict[str, Any] = Depends(get_current_user)):
    return {
        "id": user["id"],
        "email": user["email"],
        "display_name": user.get("display_name")
    }


# --- Status & Data Endpoints (User-Scoped) ---

@router.get("/api/status")
async def get_app_status(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Returns live connection and synchronization stats for current user.
    """
    user_id = user["id"]
    garmin_srv = get_user_garmin_service(user_id)
    strava_srv = get_user_strava_service(user_id)

    garmin_connected = garmin_srv.is_authenticated()
    if not garmin_connected:
        garmin_connected = garmin_srv.init_session()

    garmin_email = garmin_srv.email if garmin_connected else None

    strava_configured = strava_srv.is_configured()
    strava_connected = strava_srv.is_authenticated()
    strava_athlete = strava_srv.get_athlete_name() if strava_connected else None

    stats = get_sync_stats(user_id)

    return {
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user.get("display_name")
        },
        "garmin": {
            "connected": garmin_connected,
            "email": garmin_email,
        },
        "strava": {
            "configured": strava_configured,
            "connected": strava_connected,
            "athlete_name": strava_athlete,
            "client_id": strava_srv.client_id or "",
        },
        "stats": stats
    }


@router.post("/api/garmin/login")
async def garmin_login(data: GarminLoginRequest, user: Dict[str, Any] = Depends(get_current_user)):
    """
    Logs into Garmin Connect for current user.
    """
    if not data.email or not data.password:
        raise HTTPException(status_code=400, detail="L'email et le mot de passe sont requis.")

    user_id = user["id"]
    garmin_srv = get_user_garmin_service(user_id)
    success, error = garmin_srv.login(data.email, data.password)
    
    if not success:
        raise HTTPException(status_code=400, detail=error or "Échec de la connexion Garmin.")

    # Automatically fetch initial activities after login
    try:
        sync_srv = get_user_sync_service(user_id)
        sync_srv.refresh_garmin_activities(limit=30)
    except Exception as e:
        logger.warning(f"Initial sync after login failed for user {user_id}: {e}")

    return {
        "success": True,
        "message": f"Connecté à Garmin Connect avec succès ({data.email})."
    }


@router.post("/api/garmin/logout")
async def garmin_logout(user: Dict[str, Any] = Depends(get_current_user)):
    user_id = user["id"]
    garmin_srv = get_user_garmin_service(user_id)
    garmin_srv.logout()
    return {"success": True, "message": "Déconnecté de Garmin Connect."}


@router.post("/api/garmin/sync")
async def garmin_sync(limit: int = Query(default=50, ge=1, le=200), user: Dict[str, Any] = Depends(get_current_user)):
    """
    Syncs recent activities from Garmin Connect to local DB for current user.
    """
    try:
        sync_srv = get_user_sync_service(user["id"])
        result = sync_srv.refresh_garmin_activities(limit=limit)
        return {
            "success": True,
            "count": result["count"],
            "message": f"{result['count']} activités Garmin synchronisées."
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/activities")
async def get_activities(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = "all",
    activity_type: Optional[str] = "all",
    search: Optional[str] = None,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Returns filtered activities list for current user.
    """
    user_id = user["id"]
    activities = list_activities(
        user_id=user_id,
        limit=limit,
        offset=offset,
        status=status,
        activity_type=activity_type,
        search=search
    )
    total = count_activities(
        user_id=user_id,
        status=status,
        activity_type=activity_type,
        search=search
    )
    return {
        "activities": activities,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.patch("/api/activities/{garmin_activity_id}")
async def update_activity(
    garmin_activity_id: str,
    data: UpdateActivityRequest,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Updates activity details (name, distance, duration) in the local database.
    """
    from app.database import update_activity_data, get_activity
    user_id = user["id"]
    update_activity_data(
        user_id=user_id,
        garmin_activity_id=garmin_activity_id,
        activity_name=data.activity_name,
        distance_meters=data.distance_meters,
        duration_seconds=data.duration_seconds
    )
    act = get_activity(user_id, garmin_activity_id)
    return {"success": True, "activity": act}


@router.post("/api/push/{garmin_activity_id}")
async def push_single_activity(
    garmin_activity_id: str,
    data: Optional[PushActivityRequest] = None,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Pushes an individual Garmin activity to Strava for current user.
    """
    user_id = user["id"]
    strava_srv = get_user_strava_service(user_id)
    if not strava_srv.is_authenticated():
        raise HTTPException(status_code=400, detail="Veuillez d'abord connecter votre compte Strava.")

    sync_srv = get_user_sync_service(user_id)
    req = data or PushActivityRequest()
    result = sync_srv.push_activity_to_strava(
        garmin_activity_id=garmin_activity_id,
        custom_name=req.custom_name,
        custom_description=req.custom_description,
        custom_distance=req.custom_distance,
        custom_duration=req.custom_duration,
        commute=req.commute,
        trainer=req.trainer,
        upload_mode=req.upload_mode or "auto"
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error") or "Échec de l'envoi vers Strava.")

    return result


@router.post("/api/push-batch")
async def push_batch_activities(
    data: BatchPushRequest,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Pushes a batch of selected activities to Strava for current user.
    """
    user_id = user["id"]
    strava_srv = get_user_strava_service(user_id)
    if not strava_srv.is_authenticated():
        raise HTTPException(status_code=400, detail="Veuillez d'abord connecter votre compte Strava.")

    if not data.activity_ids:
        raise HTTPException(status_code=400, detail="Aucune activité sélectionnée.")

    sync_srv = get_user_sync_service(user_id)
    result = sync_srv.push_batch(data.activity_ids)
    return result


# --- Strava OAuth2 Flow (Multi-User) ---

@router.get("/api/strava/auth-url")
async def get_strava_auth_url(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Returns the Strava OAuth2 authorization URL with signed user state.
    """
    try:
        strava_srv = get_user_strava_service(user["id"])
        url = strava_srv.get_authorization_url()
        return {"url": url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/strava/callback")
async def strava_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    request: Request = None
):
    """
    OAuth2 callback from Strava. Decodes state to associate tokens with the right user.
    """
    if error:
        return HTMLResponse(f"<h3>Erreur d'autorisation Strava : {error}</h3><p><a href='/'>Retour à l'accueil</a></p>")

    if not code:
        return HTMLResponse("<h3>Code d'autorisation manquant.</h3><p><a href='/'>Retour à l'accueil</a></p>")

    # Determine user_id from state or current session
    user_id = verify_session_token(state) if state else None
    if not user_id:
        # Fallback to session cookie
        current_user = get_current_user_optional(request) if request else None
        if current_user:
            user_id = current_user["id"]

    if not user_id:
        return HTMLResponse("<h3>Session utilisateur introuvable pour lier le compte Strava.</h3><p><a href='/login'>Se connecter</a></p>")

    try:
        strava_srv = get_user_strava_service(user_id)
        strava_srv.exchange_code(code)
        return RedirectResponse(url="/?strava_connected=1")
    except Exception as e:
        return HTMLResponse(f"<h3>Erreur lors de la connexion Strava : {e}</h3><p><a href='/settings'>Paramètres</a></p>")


@router.post("/api/strava/disconnect")
async def strava_disconnect(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Disconnects Strava account for current user.
    """
    strava_srv = get_user_strava_service(user["id"])
    strava_srv.disconnect()
    return {"success": True, "message": "Compte Strava déconnecté."}
