"""
REST-Endpunkte für Mahlzeiten (mit KI-Kalorien-Schätzung).
"""
from __future__ import annotations

import uuid
from datetime import datetime, time

from fastapi import APIRouter, Depends, HTTPException, Response

from ..auth import get_current_user_id
from ..database import (
    create_meal,
    delete_meal,
    get_meals,
    get_meals_for_date,
)
from ..meal_service import estimate_meal
from ..models import Meal, MealEstimate, NewMeal

router = APIRouter(prefix="/api/meals", tags=["meals"])


@router.get("", response_model=list[Meal])
def list_meals(user_id: str = Depends(get_current_user_id)) -> list[Meal]:
    """Liefert alle Mahlzeiten des aktuellen Benutzers."""
    return get_meals(user_id)


@router.get("/date/{date_str}", response_model=list[Meal])
def list_meals_for_date(
    date_str: str, user_id: str = Depends(get_current_user_id)
) -> list[Meal]:
    """Liefert alle Mahlzeiten für ein bestimmtes Datum (YYYY-MM-DD)."""
    try:
        date = datetime.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ungültiges Datumsformat")
    return get_meals_for_date(user_id, date)


@router.post("/estimate", response_model=MealEstimate)
def estimate_meal_calories(data: NewMeal) -> MealEstimate:
    """Lässt eine Mahlzeit von der KI schätzen (ohne zu speichern)."""
    try:
        return estimate_meal(data.description)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=Meal, status_code=201)
def create_new_meal(
    data: NewMeal, user_id: str = Depends(get_current_user_id)
) -> Meal:
    """Schätzt die Kalorien per KI und speichert die Mahlzeit."""
    try:
        estimate = estimate_meal(data.description)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Datum mit Uhrzeit kombinieren (falls eine Uhrzeit extrahiert wurde)
    # Wichtig: Die Uhrzeit wird in lokaler Zeit interpretiert, nicht in UTC.
    # Das Frontend sendet date.toISOString() (UTC), daher müssen wir die
    # lokale Zeitkomponente verwenden und die Uhrzeit in lokaler Zeit setzen.
    meal_date = data.date
    if estimate.time:
        try:
            hour, minute = map(int, estimate.time.split(":"))
            # Lokale Zeitkomponente des Datums verwenden
            if meal_date.tzinfo is not None:
                local_date = meal_date.astimezone()
            else:
                local_date = meal_date
            meal_date = local_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except (ValueError, TypeError):
            pass  # Ungültige Uhrzeit – Datum unverändert lassen


    meal = Meal(
        id=str(uuid.uuid4()),
        user_id=user_id,
        date=meal_date,
        description=data.description,
        calories=estimate.calories,
        protein_g=estimate.protein_g,
        carbs_g=estimate.carbs_g,
        fat_g=estimate.fat_g,
        provider=estimate.provider,
    )
    return create_meal(meal)


@router.delete("/{meal_id}", status_code=204)
def delete_existing_meal(
    meal_id: str, user_id: str = Depends(get_current_user_id)
) -> Response:
    """Löscht eine Mahlzeit."""
    if not delete_meal(user_id, meal_id):
        raise HTTPException(status_code=404, detail="Mahlzeit nicht gefunden")
    return Response(status_code=204)
