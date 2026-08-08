"""
REST-Endpunkte für Aktivitäten (Strava).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user_id
from ..database import get_activities
from ..models import Activity
from .. import strava

router = APIRouter(prefix="/api/activities", tags=["activities"])


@router.get("", response_model=list[Activity])
def list_activities(user_id: str = Depends(get_current_user_id)) -> list[Activity]:
    """Liefert alle gespeicherten Aktivitäten des aktuellen Benutzers."""
    return get_activities(user_id)


@router.post("/sync", response_model=list[Activity])
def sync_activities(
    per_page: int = 30,
    page: int = 1,
    user_id: str = Depends(get_current_user_id),
) -> list[Activity]:
    """Ruft Aktivitäten von Strava ab und speichert sie."""
    try:
        return strava.fetch_activities(user_id, per_page=per_page, page=page)
    except RuntimeError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Strava-Fehler: {e}")
