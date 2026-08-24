import hmac
import hashlib
import time
import logging
from typing import Any, Dict, Optional
from fastapi import HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.config import settings
from app.database import get_user_by_id

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "session_token"
SESSION_MAX_AGE_SECONDS = 30 * 24 * 3600  # 30 days


def create_session_token(user_id: int) -> str:
    """
    Creates a tamper-proof signed session token: {user_id}:{timestamp}:{signature}
    """
    timestamp = int(time.time())
    payload = f"{user_id}:{timestamp}"
    signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return f"{payload}:{signature}"


def verify_session_token(token: str) -> Optional[int]:
    """
    Verifies the session token signature and expiration.
    Returns: user_id (int) or None if invalid/expired.
    """
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return None

        user_id_str, timestamp_str, signature = parts
        payload = f"{user_id_str}:{timestamp_str}"
        
        expected_sig = hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            return None

        timestamp = int(timestamp_str)
        # Check expiration (30 days)
        if time.time() - timestamp > SESSION_MAX_AGE_SECONDS:
            return None

        return int(user_id_str)
    except Exception as e:
        logger.debug(f"Invalid session token: {e}")
        return None


def get_current_user_optional(request: Request) -> Optional[Dict[str, Any]]:
    """
    Retrieves current authenticated user if session cookie or Bearer header is valid.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    
    if not token:
        # Check Authorization header (Bearer ...)
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

    if not token:
        return None

    user_id = verify_session_token(token)
    if not user_id:
        return None

    user = get_user_by_id(user_id)
    return user


def get_current_user(request: Request) -> Dict[str, Any]:
    """
    FastAPI dependency requiring authentication.
    For HTML page views, raises redirect exception to /login.
    For API endpoints, raises HTTP 401.
    """
    user = get_current_user_optional(request)
    if user:
        return user

    # Distinguish API requests from HTML page requests
    is_api = request.url.path.startswith("/api/")
    if is_api:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expirée ou non authentifiée. Veuillez vous connecter."
        )
    else:
        # For HTML views, redirect directly to /login
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": f"/login?next={request.url.path}"}
        )
