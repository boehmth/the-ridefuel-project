"""
Zentrale Zeitzonen-Helfer für RideFuel.

Strategie (siehe docs/timezone_strategy.md):
- Intern (Datenbank, Backend) werden Zeitpunkte als UTC, timezone-aware
  gespeichert und verarbeitet.
- Benutzer-Eingaben (z. B. "09:00") werden als lokale Europe/Berlin-Zeit
  interpretiert und anschließend nach UTC konvertiert.
- Die API liefert für die Kalenderdarstellung lokale Europe/Berlin-Zeit
  OHNE Offset (naive lokale ISO-Zeit), damit das Frontend sie als reine
  lokale Darstellung behandelt und keine zusätzliche Zeitzonenverschiebung
  verursacht.
- Strava liefert UTC-Zeitpunkte; diese werden als UTC behandelt.

Es werden ausschließlich echte Zeitzonen über zoneinfo.ZoneInfo verwendet –
keine hardcodierten +1/+2-Stunden-Regeln.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Lokale Benutzer-Zeitzone
LOCAL_TZ = ZoneInfo("Europe/Berlin")

# UTC-Zeitzone (Standard)
UTC = timezone.utc


def utc_now() -> datetime:
    """Liefert den aktuellen Zeitpunkt als UTC, timezone-aware."""
    return datetime.now(UTC)


def is_naive(dt: datetime) -> bool:
    """Prüft, ob ein datetime-Wert naive (ohne Zeitzone) ist."""
    return dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None


def ensure_utc(dt: datetime) -> datetime:
    """Normalisiert einen datetime-Wert auf UTC, timezone-aware.

    - aware Werte werden nach UTC konvertiert.
    - naive Werte werden als UTC interpretiert (Fallback für Alt-Daten,
      die bereits UTC enthalten, z. B. Strava).
    """
    if is_naive(dt):
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def local_to_utc(dt: datetime) -> datetime:
    """Interpretiert einen datetime-Wert als lokale Europe/Berlin-Zeit und
    konvertiert ihn nach UTC.

    - naive Werte werden als lokale Europe/Berlin-Zeit interpretiert.
    - aware Werte werden nach Europe/Berlin normalisiert und dann nach UTC
      konvertiert.
    """
    if is_naive(dt):
        dt = dt.replace(tzinfo=LOCAL_TZ)
    else:
        dt = dt.astimezone(LOCAL_TZ)
    return dt.astimezone(UTC)


def utc_to_local(dt: datetime) -> datetime:
    """Konvertiert einen datetime-Wert nach lokaler Europe/Berlin-Zeit.

    Liefert einen timezone-aware Wert in Europe/Berlin.
    """
    if is_naive(dt):
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(LOCAL_TZ)


def utc_to_local_naive(dt: datetime) -> datetime:
    """Konvertiert einen datetime-Wert nach lokaler Europe/Berlin-Zeit und
    entfernt den Offset (naive lokale Zeit).

    Wird für die API-Ausgabe verwendet: Das Frontend behandelt naive lokale
    ISO-Zeiten als reine lokale Darstellung (kein zusätzlicher Offset-Shift).
    """
    return utc_to_local(dt).replace(tzinfo=None)


def combine_local_date_time(date: datetime, time_str: str | None) -> datetime:
    """Kombiniert eine lokale Tagesangabe mit einer Uhrzeit (HH:MM) zu einem
    UTC-Zeitpunkt.

    - date: lokale Tagesangabe (naive oder aware).
    - time_str: Uhrzeit im Format "HH:MM" oder None (dann Mitternacht).

    Liefert einen UTC, timezone-aware Zeitpunkt.
    """
    # Nur das lokale Datum verwenden (Mitternacht)
    local_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
    if time_str:
        try:
            hour, minute = map(int, time_str.split(":"))
            local_date = local_date.replace(hour=hour, minute=minute)
        except (ValueError, TypeError):
            pass  # Ungültige Uhrzeit – Datum unverändert lassen
    return local_to_utc(local_date)
