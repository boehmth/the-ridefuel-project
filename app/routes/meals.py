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
from ..timeutil import combine_local_date_time, utc_to_local_naive



router = APIRouter(prefix="/api/meals", tags=["meals"])


def _to_local_naive(meals: list[Meal]) -> list[Meal]:
    """Konvertiert die Mahlzeiten-Zeitpunkte in lokale Europe/Berlin-Zeit
    OHNE Offset (naive lokale ISO-Zeit).

    Damit gilt für die API-Ausgabe einheitlich: Das Frontend behandelt naive
    lokale ISO-Zeiten als reine lokale Darstellung (kein Offset-Shift).
    """
    for meal in meals:
        meal.date = utc_to_local_naive(meal.date)
    return meals


@router.get("", response_model=list[Meal])
def list_meals(user_id: str = Depends(get_current_user_id)) -> list[Meal]:
    """Liefert alle Mahlzeiten des aktuellen Benutzers."""
    return _to_local_naive(get_meals(user_id))


@router.get("/date/{date_str}", response_model=list[Meal])
def list_meals_for_date(
    date_str: str, user_id: str = Depends(get_current_user_id)
) -> list[Meal]:
    """Liefert alle Mahlzeiten für ein bestimmtes Datum (YYYY-MM-DD)."""
    try:
        date = datetime.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ungültiges Datumsformat")
    # Die Tagesangabe ist eine lokale Europe/Berlin-Zeit (Mitternacht).
    # Für den Vergleich in get_meals_for_date wird sie nach UTC normalisiert.
    return _to_local_naive(get_meals_for_date(user_id, combine_local_date_time(date, None)))




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

    # Datum mit Uhrzeit kombinieren (falls eine Uhrzeit extrahiert wurde).
    #
    # WICHTIG (Zeitzonen-Strategie): Die Tagesangabe (YYYY-MM-DD) und die
    # extrahierte Uhrzeit (HH:MM) werden als lokale Europe/Berlin-Zeit
    # interpretiert und anschließend nach UTC konvertiert. Intern wird UTC
    # gespeichert. Der Server darf sich NICHT auf seine eigene lokale
    # Zeitzone verlassen (Cloud Run läuft in UTC).
    meal_date = combine_local_date_time(data.date, estimate.time)

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
    created = create_meal(meal)
    # Einheitliche API-Ausgabe: lokale Europe/Berlin-Zeit ohne Offset
    return _to_local_naive([created])[0]



@router.delete("/{meal_id}", status_code=204)
def delete_existing_meal(
    meal_id: str, user_id: str = Depends(get_current_user_id)
) -> Response:
    """Löscht eine Mahlzeit."""
    if not delete_meal(user_id, meal_id):
        raise HTTPException(status_code=404, detail="Mahlzeit nicht gefunden")
    return Response(status_code=204)
