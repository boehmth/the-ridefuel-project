# TrainingsPlanner

Persönlicher Trainings- und Ernährungsplaner als Python-Web-App.

## Features

- **Google-Login** mit automatischer Benutzerverwaltung (Multi-User)
- **Kalender** mit Tag-, Wochen-, Monats- und Jahresansicht (ineinander zoombar)
- **Strava-Anbindung** zum Abrufen deiner eigenen Aktivitäten (OAuth2, pro Benutzer)
- **KI-Nahrungs-Eingabe**: Freitext → Kalorien-Schätzung per DeepSeek oder Gemini

## Technologie-Stack

- **Backend:** FastAPI (Python)
- **Frontend:** HTML + CSS + Vanilla JavaScript
- **Datenbank:** SQLite
- **KI:** DeepSeek (OpenAI-kompatibel) und Google Gemini
- **Auth:** Google OAuth 2.0 / OpenID Connect mit JWT-Session-Cookie

## Installation

```bash
# 1. Virtuelle Umgebung erstellen
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux

# 2. Abhängigkeiten installieren
pip install -r requirements.txt

# 3. .env-Datei anlegen
copy .env.example .env   # Windows
# cp .env.example .env   # macOS/Linux

# 4. API-Keys in .env eintragen
#    - GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET (für Login)
#    - DEEPSEEK_API_KEY oder GOOGLE_API_KEY (für KI-Kalorien)
#    - STRAVA_CLIENT_ID + STRAVA_CLIENT_SECRET (für Strava)
```

### Google OAuth einrichten

1. Gehe zur [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Erstelle ein neues OAuth-Client (Web-Anwendung)
3. Füge `http://localhost:8000/api/auth/google/callback` als Redirect-URI hinzu
4. Kopiere Client-ID und Client-Secret in die `.env`-Datei

## Starten

```bash
python run.py
```

Dann im Browser öffnen: **http://localhost:8000**

## Projektstruktur

```
trainingsplanner/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI-App
│   ├── models.py         # Pydantic-Modelle
│   ├── database.py       # SQLite-Zugriff
│   ├── auth.py           # JWT-Session-Verwaltung
│   ├── meal_service.py   # KI-Kalorien-Schätzung
│   ├── strava.py         # Strava-API-Anbindung
│   ├── ai/
│   │   ├── deepseek.py   # DeepSeek-Provider
│   │   └── gemini.py     # Gemini-Provider
│   └── routes/
│       ├── auth.py       # Google-Login-Endpunkte
│       ├── events.py     # Ereignis-Endpunkte
│       ├── activities.py # Aktivitäts-Endpunkte
│       ├── meals.py      # Mahlzeiten-Endpunkte
│       ├── strava.py     # Strava-OAuth-Endpunkte
│       └── calendar.py   # Kombinierte Kalenderdaten
├── static/
│   ├── index.html        # Frontend
│   ├── styles.css        # Styles
│   └── app.js            # Frontend-Logik
├── data/                 # SQLite-Datenbank
├── requirements.txt
├── run.py                # Einstiegspunkt
└── .env.example
```

## API-Endpunkte

| Methode | Pfad | Beschreibung |
|---------|------|--------------|
| GET | `/api/auth/status` | Auth-Status des aktuellen Benutzers |
| GET | `/api/auth/google/auth-url` | Google-Login-URL |
| POST | `/api/auth/google/token` | Google-Code gegen Session eintauschen |
| POST | `/api/auth/logout` | Abmelden |
| GET | `/api/events` | Alle Ereignisse |
| POST | `/api/events` | Neues Ereignis |
| GET | `/api/meals` | Alle Mahlzeiten |
| GET | `/api/meals/date/{YYYY-MM-DD}` | Mahlzeiten eines Tages |
| POST | `/api/meals` | Mahlzeit mit KI-Kalorien speichern |
| POST | `/api/meals/estimate` | Nur KI-Schätzung (ohne Speichern) |
| GET | `/api/activities` | Gespeicherte Strava-Aktivitäten |
| POST | `/api/activities/sync` | Aktivitäten von Strava synchronisieren |
| GET | `/api/strava/auth-url` | Strava-OAuth-URL |
| GET | `/api/strava/status` | Strava-Auth-Status |
| GET | `/api/calendar` | Kombinierte Kalenderdaten (Events + Aktivitäten + Mahlzeiten) |
| GET | `/api/health` | Health-Check |
