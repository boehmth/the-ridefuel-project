"""
REST-Endpunkte für den Strava-OAuth-Flow.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from .. import strava
from ..auth import get_current_user_id

router = APIRouter(prefix="/api/strava", tags=["strava"])


@router.get("/auth-url")
def get_auth_url(user_id: str = Depends(get_current_user_id)) -> dict:
    """Liefert die Autorisierungs-URL für den OAuth-Flow des aktuellen Benutzers."""
    try:
        return {"auth_url": strava.get_auth_url(user_id)}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
def get_status(user_id: str = Depends(get_current_user_id)) -> dict:
    """Liefert den Authentifizierungsstatus des aktuellen Benutzers."""
    return {"authenticated": strava.is_authenticated(user_id)}


@router.get("/callback")
def oauth_callback(
    code: str = Query(...),
    state: str = Query(""),
    user_id: str = Depends(get_current_user_id),
) -> RedirectResponse:
    """Verarbeitet den OAuth-Callback von Strava.

    Der State wird serverseitig validiert (existiert, gültig, nicht
    abgelaufen, nicht bereits verwendet) und gegen die aktuelle Session
    geprüft (CSRF-Schutz). Die user_id wird ausschließlich aus dem
    validierten, serverseitig gespeicherten State ermittelt – nie aus
    einem untrusted Query-Parameter. Ein manipuliertes, fremdes,
    abgelaufenes oder bereits verwendetes State wird abgelehnt.
    """
    if not state:
        raise HTTPException(status_code=400, detail="State-Parameter fehlt")

    result_user_id = strava.handle_callback(code, state, user_id)
    if not result_user_id:
        raise HTTPException(
            status_code=400,
            detail="OAuth-Fehler bei Strava: State ungültig, abgelaufen, bereits verwendet oder fremd",
        )
    # Nach erfolgreicher Anmeldung zurück zur App
    return RedirectResponse(url="/")



