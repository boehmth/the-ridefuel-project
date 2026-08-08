"""
Strava-Anbindung.

Implementiert den OAuth2-Flow und den Abruf von Aktivitäten.
Jeder Benutzer verbindet sein eigenes Strava-Konto. Die Tokens werden
als ConnectedAccount in der Datenbank gespeichert.
"""
from __future__ import annotations

import os
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests

from .database import (
    consume_oauth_state,
    create_oauth_state,
    get_connected_account,
    get_oauth_state,
    upsert_activity,
    upsert_connected_account,
)
from .models import Activity, ConnectedAccount, OAuthState

# Strava-API-Endpunkte
STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_URL = "https://www.strava.com/api/v3"

PROVIDER = "STRAVA"

# Gültigkeitsdauer eines OAuth-States (Nonce) in Sekunden.
# Nach Ablauf wird der State im Callback abgelehnt.
OAUTH_STATE_TTL_SECONDS = 600  # 10 Minuten



def get_client_id() -> str:
    """Liefert die Strava Client ID."""
    client_id = os.getenv("STRAVA_CLIENT_ID")
    if not client_id:
        raise RuntimeError("STRAVA_CLIENT_ID fehlt in .env")
    return client_id


def get_client_secret() -> str:
    """Liefert das Strava Client Secret."""
    secret = os.getenv("STRAVA_CLIENT_SECRET")
    if not secret:
        raise RuntimeError("STRAVA_CLIENT_SECRET fehlt in .env")
    return secret


def get_redirect_uri() -> str:
    """Liefert die Redirect-URI für den OAuth-Flow."""
    return os.getenv(
        "STRAVA_REDIRECT_URI", "http://localhost:8000/api/strava/callback"
    )


def _generate_state(user_id: str) -> str:
    """Erzeugt einen kryptographisch sicheren OAuth-State (Nonce).

    Der State wird serverseitig gespeichert und eindeutig dem aktuellen
    Benutzer zugeordnet. Er enthält NICHT die rohe user_id, sondern ist
    ein zufälliger, nicht erratbarer Wert.
    """
    state_value = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    oauth_state = OAuthState(
        state=state_value,
        user_id=user_id,
        provider=PROVIDER,
        created_at=now,
        expires_at=now + timedelta(seconds=OAUTH_STATE_TTL_SECONDS),
    )
    create_oauth_state(oauth_state)
    return state_value


def get_auth_url(user_id: str) -> str:
    """Erzeugt die Autorisierungs-URL für den OAuth-Flow.

    Erzeugt einen serverseitig gespeicherten, zufälligen State (Nonce),
    der dem aktuellen Benutzer zugeordnet ist. Der Callback validiert
    diesen State und ermittelt daraus die user_id – nie aus einem
    untrusted Query-Parameter.
    """
    state = _generate_state(user_id)
    params = {
        "client_id": get_client_id(),
        "response_type": "code",
        "redirect_uri": get_redirect_uri(),
        "approval_prompt": "auto",
        "scope": "activity:read_all",
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{STRAVA_AUTH_URL}?{query}"



def is_authenticated(user_id: str) -> bool:
    """Prüft, ob der Benutzer ein Strava-Konto verbunden hat."""
    account = get_connected_account(user_id, PROVIDER)
    return account is not None and bool(account.access_token)


def _refresh_access_token(account: ConnectedAccount) -> Optional[ConnectedAccount]:
    """Erneuert das Access Token mit dem Refresh Token."""
    if not account.refresh_token:
        return None

    resp = requests.post(
        STRAVA_TOKEN_URL,
        data={
            "client_id": get_client_id(),
            "client_secret": get_client_secret(),
            "grant_type": "refresh_token",
            "refresh_token": account.refresh_token,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        return None

    data = resp.json()
    account.access_token = data["access_token"]
    account.refresh_token = data.get("refresh_token", account.refresh_token)
    account.expires_at = data.get("expires_at", 0)
    return upsert_connected_account(account)


def validate_state(state: str) -> Optional[str]:
    """Validiert einen OAuth-State und liefert die zugehörige user_id.

    Prüft, ob der State existiert und noch nicht abgelaufen ist.
    Liefert die user_id bei gültigem State, sonst None.
    Der State wird hier NICHT verbraucht (einmalige Verwendung erfolgt
    in handle_callback).
    """
    if not state:
        return None
    oauth_state = get_oauth_state(state)
    if not oauth_state:
        return None
    if datetime.now(timezone.utc) > oauth_state.expires_at:
        return None
    return oauth_state.user_id


def handle_callback(code: str, state: str, session_user_id: str) -> Optional[str]:
    """Verarbeitet den OAuth-Callback und speichert die Tokens.

    Der State wird serverseitig validiert (existiert, gültig, nicht
    abgelaufen) und nach erfolgreicher Verwendung gelöscht (einmalige
    Verwendung). Zusätzlich wird geprüft, dass der State dem aktuell
    angemeldeten Benutzer (session_user_id) gehört – ein fremder State
    wird abgelehnt (CSRF-Schutz). Die user_id wird ausschließlich aus dem
    validierten, serverseitig gespeicherten State ermittelt – nie aus
    einem untrusted Query-Parameter.

    Liefert die user_id bei Erfolg, sonst None.
    """
    # 1. State validieren und user_id ermitteln
    user_id = validate_state(state)
    if not user_id:
        return None

    # 2. CSRF-Schutz: Der State muss dem aktuell angemeldeten Benutzer gehören.
    #    Ein fremder State (z. B. von User A, eingereicht von User B) wird abgelehnt.
    if user_id != session_user_id:
        return None

    # 3. State verbrauchen (einmalige Verwendung) – vor dem Token-Tausch,
    #    damit ein State nicht mehrfach verwendet werden kann.
    consume_oauth_state(state)

    # 4. Authorization Code gegen Strava-Tokens tauschen
    resp = requests.post(
        STRAVA_TOKEN_URL,
        data={
            "client_id": get_client_id(),
            "client_secret": get_client_secret(),
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        return None

    data = resp.json()
    account = ConnectedAccount(
        id=str(uuid.uuid4()),
        user_id=user_id,
        provider=PROVIDER,
        provider_user_id=str(data.get("athlete", {}).get("id", "")),
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        expires_at=data.get("expires_at", 0),
    )
    upsert_connected_account(account)
    return user_id




def _get_access_token(user_id: str) -> Optional[str]:
    """Liefert ein gültiges Access Token für den Benutzer (erneuert bei Bedarf)."""
    account = get_connected_account(user_id, PROVIDER)
    if not account or not account.access_token:
        return None

    expires_at = account.expires_at or 0
    # Erneuern, wenn das Token in weniger als 60 Sekunden abläuft
    if expires_at and time.time() > expires_at - 60:
        refreshed = _refresh_access_token(account)
        if not refreshed:
            return None
        return refreshed.access_token

    return account.access_token


def _api_get(user_id: str, path: str, params: dict[str, Any] | None = None) -> Any:
    """Führt einen authentifizierten GET-Request gegen die Strava-API aus."""
    token = _get_access_token(user_id)
    if not token:
        raise RuntimeError("Nicht bei Strava authentifiziert")

    resp = requests.get(
        f"{STRAVA_API_URL}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params or {},
        timeout=30,
    )
    if resp.status_code == 401:
        # Token abgelaufen – einmal erneuern und erneut versuchen
        account = get_connected_account(user_id, PROVIDER)
        if account and _refresh_access_token(account):
            token = _get_access_token(user_id)
            resp = requests.get(
                f"{STRAVA_API_URL}{path}",
                headers={"Authorization": f"Bearer {token}"},
                params=params or {},
                timeout=30,
            )
    resp.raise_for_status()
    return resp.json()


def _parse_activity(user_id: str, data: dict[str, Any]) -> Activity:
    """Wandelt ein Strava-Activity-JSON in ein Activity-Modell um."""
    start_date = datetime.fromisoformat(
        data["start_date"].replace("Z", "+00:00")
    ).astimezone(timezone.utc)

    return Activity(
        id=str(uuid.uuid4()),
        user_id=user_id,
        strava_id=data["id"],
        name=data["name"],
        activity_type=data["type"],
        start_date=start_date,
        distance_m=data.get("distance", 0.0),
        moving_time_s=data.get("moving_time", 0),
        elapsed_time_s=data.get("elapsed_time", 0),
        total_elevation_gain_m=data.get("total_elevation_gain", 0.0),
        average_speed_ms=data.get("average_speed", 0.0),
        max_speed_ms=data.get("max_speed", 0.0),
        average_heartrate=data.get("average_heartrate"),
        max_heartrate=data.get("max_heartrate"),
        calories=data.get("calories"),
        kudos_count=data.get("kudos_count", 0),
    )


def fetch_activities(user_id: str, per_page: int = 30, page: int = 1) -> list[Activity]:
    """Ruft Aktivitäten von Strava ab und speichert sie in der Datenbank.

    Holt zusätzlich die Detail-Daten (inkl. Kalorien) für Aktivitäten,
    die noch keine Kalorien haben.
    """
    data = _api_get(
        user_id,
        "/athlete/activities",
        {"per_page": per_page, "page": page},
    )

    activities = [_parse_activity(user_id, item) for item in data]

    # Für Aktivitäten ohne Kalorien die Detail-Daten abrufen
    # (Strava liefert Kalorien nur im Detail-Endpunkt)
    for activity in activities:
        if activity.calories is None:
            try:
                detail = _api_get(user_id, f"/activities/{activity.strava_id}")
                if detail.get("calories"):
                    activity.calories = detail["calories"]
            except Exception:
                pass  # Detail-Abruf fehlgeschlagen – Kalorien bleiben None

    for activity in activities:
        upsert_activity(activity)
    return activities


def fetch_activity_detail(user_id: str, activity_id: int) -> Activity:
    """Ruft eine einzelne Aktivität mit Details ab."""
    data = _api_get(user_id, f"/activities/{activity_id}")
    activity = _parse_activity(user_id, data)
    upsert_activity(activity)
    return activity
