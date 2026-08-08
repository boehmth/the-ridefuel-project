"""
Hauptanwendung des TrainingsPlanners (FastAPI).

Startet den Server, initialisiert die Datenbank und registriert alle Routen.

Startup-Reihenfolge (GCS-Persistenz):
    GCS enabled?
        ├── ja + Objekt vorhanden → DB aus GCS herunterladen (vor init_db)
        ├── ja + Objekt fehlt     → lokale DB normal initialisieren
        └── nein                  → lokale DB normal initialisieren
    → init_db()
    → Hintergrund-Sync-Worker starten

Shutdown:
    → Worker stoppen
    → Best-effort Sync, falls DB dirty
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# .env-Datei laden (falls vorhanden) – explizit vom Projekt-Root
# WICHTIG: Vor allen anderen Imports, damit die Env-Variablen
# beim Import der Routen bereits gesetzt sind.
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import storage
from .database import (
    get_database_path,
    init_db,
    is_database_dirty,
    sync_database_to_storage,
)
from .routes import activities, auth, calendar, events, meals, strava

logger = logging.getLogger(__name__)


async def _sync_worker(stop_event: asyncio.Event, lock: asyncio.Lock) -> None:
    """Periodischer Hintergrund-Sync der SQLite-Datei nach GCS.

    - kein Busy Loop (Sleep über das Sync-Intervall)
    - kein paralleler Upload (asyncio.Lock)
    - Fehler beenden die Anwendung nicht
    """
    interval = storage.get_sync_interval_seconds()
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            break  # stop_event wurde gesetzt
        except asyncio.TimeoutError:
            pass

        if not storage.is_gcs_enabled():
            continue
        if not is_database_dirty():
            continue

        async with lock:
            try:
                await asyncio.to_thread(sync_database_to_storage)
            except Exception as e:  # noqa: BLE001
                logger.error("GCS SQLite background sync failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. GCS-Download VOR init_db() bzw. dem ersten DB-Zugriff
    if storage.is_gcs_enabled():
        try:
            exists = storage.database_exists_in_storage()
        except Exception as e:  # noqa: BLE001
            logger.error("GCS SQLite existence check failed: %s", e)
            raise RuntimeError(
                "GCS SQLite persistence enabled but storage check failed"
            ) from e

        if exists:
            ok = storage.download_database(get_database_path())
            if not ok:
                # GCS-Datei vorhanden, aber Download fehlgeschlagen:
                # nicht mit einer leeren DB starten (Datenverlust-Risiko).
                raise RuntimeError(
                    "GCS SQLite database exists but download failed; "
                    "refusing to start with an empty database."
                )
        else:
            logger.info("No SQLite database found in GCS; using local database")

    # 2. Datenbank initialisieren (erkennt bestehende Tabellen, überschreibt nichts)
    init_db()

    # 3. Hintergrund-Sync-Worker starten
    stop_event = asyncio.Event()
    lock = asyncio.Lock()
    task = asyncio.create_task(_sync_worker(stop_event, lock))

    try:
        yield
    finally:
        # 4. Shutdown: Worker stoppen
        stop_event.set()
        try:
            await asyncio.wait_for(task, timeout=5)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            task.cancel()

        # Best-effort Shutdown-Upload (nur zusätzlicher Schutz, nicht primär)
        if storage.is_gcs_enabled() and is_database_dirty():
            async with lock:
                try:
                    await asyncio.to_thread(sync_database_to_storage)
                except Exception as e:  # noqa: BLE001
                    logger.error("GCS SQLite shutdown sync failed: %s", e)


# FastAPI-App erstellen
app = FastAPI(
    title="TrainingsPlanner",
    description="Persönlicher Trainings- und Ernährungsplaner",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS für lokale Entwicklung
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API-Routen registrieren
app.include_router(auth.router)
app.include_router(events.router)
app.include_router(activities.router)
app.include_router(strava.router)
app.include_router(meals.router)
app.include_router(calendar.router)


# Statische Dateien (Frontend) servieren
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@app.get("/api/health")
def health_check() -> dict:
    """Health-Check-Endpunkt."""
    return {"status": "ok", "app": "TrainingsPlanner"}


@app.get("/")
def serve_index() -> FileResponse:
    """Serviert die Startseite."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/{filename}")
def serve_static(filename: str) -> FileResponse:
    """Serviert statische Dateien (styles.css, app.js)."""
    file_path = STATIC_DIR / filename
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(STATIC_DIR / "index.html")
