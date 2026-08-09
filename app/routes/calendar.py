"""
REST-Endpunkt für kombinierte Kalenderdaten.

Liefert alle Ereignisse (Kalender-Events, Aktivitäten, Mahlzeiten)
normalisiert mit start/end-Zeit für die Kalenderansicht.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends

from ..auth import get_current_user_id
from ..database import get_activities, get_events, get_meals
from ..models import Activity, CalendarEvent, Meal
from ..timeutil import utc_to_local_naive


router = APIRouter(prefix="/api/calendar", tags=["calendar"])

# Standard-Dauer für Mahlzeiten (30 Minuten)
MEAL_DURATION_MIN = 30


def _activity_to_calendar_item(activity: Activity) -> dict:
    """Wandelt eine Aktivität in ein Kalender-Item um.

    Die Ausgabe erfolgt als lokale Europe/Berlin-Zeit OHNE Offset (naive
    lokale ISO-Zeit), damit das Frontend sie als reine lokale Darstellung
    behandelt und keine zusätzliche Zeitzonenverschiebung verursacht.
    """
    start = activity.start_date
    # Dauer aus elapsed_time_s (oder moving_time_s als Fallback)
    duration_s = activity.elapsed_time_s or activity.moving_time_s or 3600
    end = start + timedelta(seconds=duration_s)

    # Lokale Europe/Berlin-Zeit (naive) für die Anzeige
    start_local = utc_to_local_naive(start)
    end_local = utc_to_local_naive(end)

    return {
        "id": f"activity-{activity.id}",
        "source_id": activity.id,
        "type": "activity",
        "start": start_local.isoformat(),
        "end": end_local.isoformat(),

        "title": activity.name,
        "activity_type": activity.activity_type,
        "distance_m": activity.distance_m,
        "moving_time_s": activity.moving_time_s,
        "calories": activity.calories,
        "metadata": {
            "distance_km": round(activity.distance_m / 1000, 2),
            "moving_time_min": round(activity.moving_time_s / 60),
            "calories": activity.calories,
        },
    }


def _meal_to_calendar_item(meal: Meal) -> dict:
    """Wandelt eine Mahlzeit in ein Kalender-Item um.

    Die Ausgabe erfolgt als lokale Europe/Berlin-Zeit OHNE Offset (naive
    lokale ISO-Zeit), damit das Frontend sie als reine lokale Darstellung
    behandelt und keine zusätzliche Zeitzonenverschiebung verursacht.
    """
    start = meal.date
    end = start + timedelta(minutes=MEAL_DURATION_MIN)

    # Lokale Europe/Berlin-Zeit (naive) für die Anzeige
    start_local = utc_to_local_naive(start)
    end_local = utc_to_local_naive(end)

    return {
        "id": f"meal-{meal.id}",
        "source_id": meal.id,
        "type": "meal",
        "start": start_local.isoformat(),
        "end": end_local.isoformat(),

        "title": meal.description,
        "calories": meal.calories,
        "protein_g": meal.protein_g,
        "carbs_g": meal.carbs_g,
        "fat_g": meal.fat_g,
        "metadata": {
            "calories": meal.calories,
            "protein_g": meal.protein_g,
            "carbs_g": meal.carbs_g,
            "fat_g": meal.fat_g,
        },
    }


def _event_to_calendar_item(event: CalendarEvent) -> dict:
    """Wandelt ein Kalender-Ereignis in ein Kalender-Item um.

    Die Ausgabe erfolgt als lokale Europe/Berlin-Zeit OHNE Offset (naive
    lokale ISO-Zeit), damit das Frontend sie als reine lokale Darstellung
    behandelt und keine zusätzliche Zeitzonenverschiebung verursacht.
    """
    start_local = utc_to_local_naive(event.start)
    end_local = utc_to_local_naive(event.end)

    return {
        "id": f"event-{event.id}",
        "source_id": event.id,
        "type": "event",
        "start": start_local.isoformat(),
        "end": end_local.isoformat(),

        "title": event.title,
        "event_type": event.event_type.value,
        "description": event.description,
        "metadata": event.metadata,
    }


@router.get("")
def get_calendar_data(
    start: str | None = None,
    end: str | None = None,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Liefert alle Kalender-Items des aktuellen Benutzers.

    Optional kann ein Zeitraum über start/end (ISO-Format) gefiltert werden.
    """
    items: list[dict] = []

    # Kalender-Events
    for event in get_events(user_id):
        items.append(_event_to_calendar_item(event))

    # Aktivitäten
    for activity in get_activities(user_id):
        items.append(_activity_to_calendar_item(activity))

    # Mahlzeiten
    for meal in get_meals(user_id):
        items.append(_meal_to_calendar_item(meal))

    # Zeitraum-Filter
    if start:
        start_dt = datetime.fromisoformat(start)
        items = [i for i in items if datetime.fromisoformat(i["end"]) >= start_dt]
    if end:
        end_dt = datetime.fromisoformat(end)
        items = [i for i in items if datetime.fromisoformat(i["start"]) <= end_dt]

    # Nach Startzeit sortieren
    items.sort(key=lambda i: i["start"])

    return {"items": items}
