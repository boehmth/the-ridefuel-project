"""
Datums-Hilfsfunktionen für den Kalender.

Übertragen aus der TypeScript-Version (dateUtils.ts).
Alle Berechnungen arbeiten mit lokalen Datumsangaben.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

# Wochentagsnamen (Montag bis Sonntag)
WEEKDAY_LABELS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

# Monatsnamen
MONTH_LABELS = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


def to_iso_date(d: date) -> str:
    """Formatiert ein Datum als ISO-Datum (YYYY-MM-DD)."""
    return d.isoformat()


def from_iso_date(iso: str) -> date:
    """Erzeugt ein Datum aus einem ISO-Datum (YYYY-MM-DD)."""
    return date.fromisoformat(iso)


def start_of_month(d: date) -> date:
    """Liefert den ersten Tag des Monats."""
    return d.replace(day=1)


def end_of_month(d: date) -> date:
    """Liefert den letzten Tag des Monats."""
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


def start_of_week(d: date) -> date:
    """Liefert den Montag der Woche, in der das Datum liegt."""
    # Python: weekday() 0=Montag, 6=Sonntag
    return d - timedelta(days=d.weekday())


def end_of_week(d: date) -> date:
    """Liefert den Sonntag der Woche, in der das Datum liegt."""
    return start_of_week(d) + timedelta(days=6)


def add_days(d: date, days: int) -> date:
    """Addiert Tage zu einem Datum."""
    return d + timedelta(days=days)


def add_months(d: date, months: int) -> date:
    """Addiert Monate zu einem Datum."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def add_years(d: date, years: int) -> date:
    """Addiert Jahre zu einem Datum."""
    return date(d.year + years, d.month, 1)


def is_same_day(a: date, b: date) -> bool:
    """Prüft, ob zwei Daten am selben Tag liegen."""
    return a == b


def is_same_month(a: date, b: date) -> bool:
    """Prüft, ob zwei Daten im selben Monat liegen."""
    return a.year == b.year and a.month == b.month


def is_same_year(a: date, b: date) -> bool:
    """Prüft, ob zwei Daten im selben Jahr liegen."""
    return a.year == b.year


def days_in_month(d: date) -> int:
    """Liefert die Anzahl der Tage im Monat."""
    return end_of_month(d).day


def month_grid(month_date: date) -> list[date]:
    """Liefert die Tage eines Monats als 42er-Raster (6 Wochen × 7 Tage)."""
    grid_start = start_of_week(start_of_month(month_date))
    return [grid_start + timedelta(days=i) for i in range(42)]


def year_month_grid(month_date: date) -> list[date]:
    """Liefert die Tage eines Monats als kompaktes Raster (inkl. Auffülltage)."""
    start = start_of_week(start_of_month(month_date))
    count = days_in_month(month_date)
    # Berechne, wie viele Wochen der Monat braucht
    offset = start.weekday()  # 0=Montag
    total = ((offset + count + 6) // 7) * 7
    return [start + timedelta(days=i) for i in range(total)]
