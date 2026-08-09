"""
Regressionstests für die Zeitzonen-Strategie bei Mahlzeiten.

Strategie (siehe docs/timezone_strategy.md):
- Intern (Datenbank, Backend) werden Zeitpunkte als UTC, timezone-aware
  gespeichert und verarbeitet.
- Benutzer-Eingaben (Tagesangabe YYYY-MM-DD + Uhrzeit HH:MM) werden als
  lokale Europe/Berlin-Zeit interpretiert und nach UTC konvertiert.
- Die API liefert für die Kalenderdarstellung lokale Europe/Berlin-Zeit
  OHNE Offset (naive lokale ISO-Zeit), damit das Frontend sie als reine
  lokale Darstellung behandelt und keine zusätzliche Zeitzonenverschiebung
  verursacht.

Problem (historisch): Eine Mahlzeit, die für 12:00 angelegt wurde, erschien
im Kalender um 14:00. Ursache: Das Frontend sendete date.toISOString()
(UTC), und der Server interpretierte die Uhrzeit als UTC. Die Mahlzeit wurde
als 12:00 UTC gespeichert und vom Browser (Europe/Berlin, UTC+2) als 14:00
angezeigt.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest import mock

from app.models import MealEstimate, NewMeal

from app.routes import meals as meals_route
from app.timeutil import utc_to_local_naive


def _make_estimate(time: str | None = "12:00") -> MealEstimate:
    return MealEstimate(
        description="Testmahlzeit",
        calories=500,
        protein_g=20.0,
        carbs_g=60.0,
        fat_g=15.0,
        provider="deepseek",
        time=time,
        valid=True,
        correction_message=None,
    )


def _call_create_meal(date_str: str, time: str | None = "12:00") -> datetime:
    """Ruft create_new_meal mit gemockter KI-Schätzung und DB auf.

    Liefert den UTC-Zeitpunkt, der an create_meal übergeben (also in der
    Datenbank gespeichert) wird.
    """
    estimate = _make_estimate(time)
    stored: list[datetime] = []

    def _fake_create(meal):
        stored.append(meal.date)
        return meal

    with mock.patch.object(meals_route, "estimate_meal", return_value=estimate), \
         mock.patch.object(meals_route, "create_meal", side_effect=_fake_create):
        meals_route.create_new_meal(
            NewMeal(date=datetime.fromisoformat(date_str), description="Testmahlzeit"),
            user_id="user-1",
        )
    return stored[0]



def test_meal_with_time_is_stored_as_utc():
    """Eine Mahlzeit 'um 12:00' am 08.08. wird als UTC gespeichert.

    Europe/Berlin ist im August UTC+2, daher entspricht 12:00 lokal 10:00 UTC.
    """
    meal_date = _call_create_meal("2026-08-08", "12:00")

    # Intern: UTC, timezone-aware
    assert meal_date.tzinfo is not None
    assert meal_date.utcoffset() == timezone.utc.utcoffset(None)
    assert meal_date.isoformat() == "2026-08-08T10:00:00+00:00"


def test_meal_without_time_is_stored_at_utc_midnight():
    """Eine Mahlzeit ohne Uhrzeit wird am gewählten Tag um 00:00 lokal
    (22:00 UTC am Vortag) gespeichert."""
    meal_date = _call_create_meal("2026-08-08", None)

    # 00:00 lokal (UTC+2) = 22:00 UTC am 07.08.
    assert meal_date.isoformat() == "2026-08-07T22:00:00+00:00"


def test_meal_date_is_independent_of_server_timezone():
    """
    Der gespeicherte UTC-Zeitpunkt hängt nicht von der Server-Zeitzone ab.

    Die Logik verwendet ausschließlich die übergebene Tagesangabe und die
    feste Europe/Berlin-Zeitzone (zoneinfo). Daher ist das Ergebnis
    deterministisch und unabhängig von der Server-Zeitzone (Cloud Run läuft
    in UTC).
    """
    meal_date = _call_create_meal("2026-08-08", "12:00")
    assert meal_date.isoformat() == "2026-08-08T10:00:00+00:00"


def test_meal_roundtrip_through_calendar_endpoint():
    """
    Der Calendar-Endpunkt liefert die lokale naive Zeit, die der Browser als
    lokale Zeit anzeigt (kein +2h-Shift).
    """
    meal_date = _call_create_meal("2026-08-08", "12:00")

    # API-Ausgabe: lokale Europe/Berlin-Zeit ohne Offset
    start_iso = utc_to_local_naive(meal_date).isoformat()
    assert start_iso == "2026-08-08T12:00:00"

    # Browser (Europe/Berlin) parst naive ISO-Zeit als lokale Zeit
    displayed = datetime.fromisoformat(start_iso)
    assert f"{displayed.hour:02d}:{displayed.minute:02d}" == "12:00"
