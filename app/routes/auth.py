"""
REST-Endpunkte für die Google-Authentifizierung.

Implementiert den Google OAuth 2.0 / OpenID Connect Flow.
Der Server verifiziert das Google-ID-Token und erstellt bei
Erstanmeldung automatisch einen neuen User-Datensatz.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel


from ..auth import (
    clear_session_cookie,
    get_current_user,
    revoke_current_session,
    set_session_cookie,
)

from ..database import create_user, get_user_by_google_id, update_user_last_login
from ..models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Google OAuth-Konfiguration (zur Laufzeit lesen, damit .env nach dem Import geladen wird)
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def _get_google_client_id() -> str:
    """Liefert die Google Client ID aus der Umgebung."""
    return os.getenv("GOOGLE_CLIENT_ID", "")


def _get_google_client_secret() -> str:
    """Liefert das Google Client Secret aus der Umgebung."""
    return os.getenv("GOOGLE_CLIENT_SECRET", "")


def _get_google_redirect_uri() -> str:
    """Liefert die Google Redirect-URI aus der Umgebung."""
    return os.getenv(
        "GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback"
    )



class GoogleTokenRequest(BaseModel):
    """Anfrage mit dem Google-Authorization-Code."""

    code: str


class AuthStatusResponse(BaseModel):
    """Status der Authentifizierung."""

    authenticated: bool
    user: dict | None = None


@router.get("/status")
def get_auth_status(request: Request) -> AuthStatusResponse:
    """Liefert den Authentifizierungsstatus des aktuellen Benutzers."""
    try:
        user = get_current_user(request)
        return AuthStatusResponse(
            authenticated=True,
            user={
                "id": user.id,
                "email": user.email,
                "display_name": user.display_name,
                "picture_url": user.picture_url,
            },
        )
    except HTTPException:
        return AuthStatusResponse(authenticated=False, user=None)


@router.get("/google/auth-url")
def get_google_auth_url() -> dict:
    """Liefert die Google-Autorisierungs-URL."""
    client_id = _get_google_client_id()
    if not client_id:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_CLIENT_ID fehlt in .env",
        )

    params = {
        "client_id": client_id,
        "redirect_uri": _get_google_redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return {"auth_url": f"{GOOGLE_AUTH_URL}?{query}"}



@router.get("/google/callback")
def google_callback(
    code: str = Query(...),
    error: str | None = Query(None),
) -> RedirectResponse:
    """Verarbeitet den Google-OAuth-Callback.

    Leitet den Benutzer auf die Hauptseite weiter, wobei der Code
    als Query-Parameter mitgegeben wird. Das Frontend liest den Code
    und sendet ihn an /api/auth/google/token.
    """
    if error:
        return RedirectResponse(url=f"/?error={error}")
    return RedirectResponse(url=f"/?code={code}")


@router.post("/google/token")
def exchange_google_token(
    data: GoogleTokenRequest,
    response: Response,
    request: Request,
) -> dict:


    """Tauscht den Google-Authorization-Code gegen ein ID-Token und erstellt eine Session.

    Der Server verifiziert das ID-Token und erstellt bei Erstanmeldung
    automatisch einen neuen User-Datensatz.
    """
    client_id = _get_google_client_id()
    client_secret = _get_google_client_secret()
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth-Konfiguration fehlt in .env",
        )

    # Authorization-Code gegen Tokens eintauschen
    import requests

    token_resp = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": data.code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": _get_google_redirect_uri(),
            "grant_type": "authorization_code",
        },
        timeout=30,
    )

    if token_resp.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail="Google-Token-Austausch fehlgeschlagen",
        )

    token_data = token_resp.json()
    id_token = token_data.get("id_token")
    if not id_token:
        raise HTTPException(status_code=400, detail="Kein ID-Token erhalten")

    # ID-Token verifizieren und Benutzerinformationen extrahieren
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests

        info = google_id_token.verify_oauth2_token(
            id_token,
            google_requests.Request(),
            client_id,
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"ID-Token-Verifikation fehlgeschlagen: {e}")

    google_id = info.get("sub")
    email = info.get("email", "")
    display_name = info.get("name")
    picture_url = info.get("picture")

    if not google_id:
        raise HTTPException(status_code=400, detail="Google-ID fehlt im Token")

    # Benutzer suchen oder erstellen
    user = get_user_by_google_id(google_id)
    now = datetime.now(timezone.utc)

    if not user:
        user = User(
            id=str(uuid.uuid4()),
            google_id=google_id,
            email=email,
            display_name=display_name,
            picture_url=picture_url,
            created_at=now,
            last_login=now,
        )
        create_user(user)
    else:
        update_user_last_login(user.id, now)

    # Session-Cookie setzen (erzeugt eine neue serverseitige Session)
    set_session_cookie(response, user.id, request)

    return {
        "authenticated": True,
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "picture_url": user.picture_url,
        },
    }


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    """Meldet den Benutzer ab.

    Widerruft die aktuelle Session serverseitig (revoked_at) und löscht
    das Session-Cookie im Browser. Ein altes Cookie ist danach sofort
    ungültig.
    """
    revoke_current_session(request)
    clear_session_cookie(response)
    return {"authenticated": False}


