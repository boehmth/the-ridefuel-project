# Zeitzonen-Strategie

Dieses Dokument beschreibt die einheitliche Zeitzonen-Behandlung im
TrainingsPlanner. Ziel ist eine **klare, konsistente Strategie** – es werden
nicht zwei verschiedene Ansätze vermischt.

## Kernprinzipien

1. **Intern (Datenbank, Backend): UTC, timezone-aware.**
   Alle Zeitpunkte werden als UTC mit Zeitzonen-Offset (`+00:00`) gespeichert
   und verarbeitet. Das macht die Daten unabhängig von der Server-Zeitzone
   (Cloud Run läuft in UTC) und von der Zeitzone des Entwicklungsrechners.

2. **Benutzer-Eingaben: lokale Europe/Berlin-Zeit.**
   Eine Tagesangabe (`YYYY-MM-DD`) und eine Uhrzeit (`HH:MM`) werden als
   lokale Europe/Berlin-Zeit interpretiert und anschließend nach UTC
   konvertiert. Es werden ausschließlich echte Zeitzonen über
   `zoneinfo.ZoneInfo("Europe/Berlin")` verwendet – keine hardcodierten
   +1/+2-Stunden-Regeln.

3. **API-Ausgabe für die Kalenderdarstellung: lokale Europe/Berlin-Zeit
   OHNE Offset (naive lokale ISO-Zeit).**
   Das Frontend behandelt naive ISO-Zeiten als reine lokale Darstellung
   (`new Date("2026-08-09T09:00:00")` → 09:00 lokal). Dadurch entsteht kein
   zusätzlicher Zeitzonen-Shift im Browser.

## Datenfluss

```
Frontend (lokal)          Backend (UTC)              Frontend (Anzeige)
─────────────────         ──────────────             ──────────────────
"2026-08-09"        →     combine_local_date_time    ←  utc_to_local_naive
"09:00" (Berlin)          → 2026-08-09T07:00:00+00:00    → "2026-08-09T09:00:00"
```

## Zentrale Helfer (`app/timeutil.py`)

| Funktion | Zweck |
|----------|-------|
| `utc_now()` | Aktueller Zeitpunkt als UTC, timezone-aware. |
| `ensure_utc(dt)` | Normalisiert einen Wert auf UTC (naive Werte als UTC interpretieren). |
| `local_to_utc(dt)` | Interpretiert einen Wert als Europe/Berlin und konvertiert nach UTC. |
| `utc_to_local(dt)` | Konvertiert nach Europe/Berlin (aware). |
| `utc_to_local_naive(dt)` | Konvertiert nach Europe/Berlin und entfernt den Offset (für API-Ausgabe). |
| `combine_local_date_time(date, time_str)` | Kombiniert lokale Tagesangabe + Uhrzeit zu UTC. |

## Anwendung

- **Mahlzeiten (`app/routes/meals.py`)**
  - Eingabe: `combine_local_date_time(data.date, estimate.time)` → UTC.
  - Speicherung: `create_meal` stellt UTC sicher (`ensure_utc`).
  - Ausgabe: `_to_local_naive(...)` → lokale naive Zeit.
- **Kalender (`app/routes/calendar.py`)**
  - Ausgabe: `utc_to_local_naive(...)` für Events, Aktivitäten und Mahlzeiten.
- **Sessions (`app/database.py`, `app/auth.py`)**
  - `datetime.now(timezone.utc)` bzw. `utc_now()` für Erstellung und Ablauf.
- **Strava (`app/database.py`)**
  - Strava liefert UTC-Zeitpunkte; `ensure_utc` stellt sicher, dass sie als
    UTC behandelt werden.

## Frontend

Das Frontend sendet die **lokale Tagesangabe** (`toISODate(date)`, z. B.
`"2026-08-09"`), **nicht** `date.toISOString()` (das wäre UTC). Die
API-Ausgabe (naive lokale ISO-Zeit) wird mit `new Date(...)` als lokale Zeit
interpretiert – die Anzeige ist damit unabhängig von der Server-Zeitzone
korrekt.

## Historisches Problem

Eine Mahlzeit, die für 12:00 angelegt wurde, erschien im Kalender um 14:00.
Ursache: Das Frontend sendete `date.toISOString()` (UTC), und der Server
interpretierte die Uhrzeit als UTC. Die Mahlzeit wurde als 12:00 UTC
gespeichert und vom Browser (Europe/Berlin, UTC+2) als 14:00 angezeigt.
Die neue Strategie löst das durch die klare Trennung von Eingabe (lokal),
Speicherung (UTC) und Ausgabe (lokal, naive).
