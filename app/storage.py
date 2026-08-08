"""
Google Cloud Storage (GCS) Persistenz für die SQLite-Datenbank.

Kapselt sämtliche GCS-spezifische Logik. Die restliche Anwendung kennt
keine GCS-Details und nutzt nur die hier angebotenen Funktionen.

Konfiguration ausschließlich über Environment-Variablen:
  GCS_SQLITE_ENABLED              - "true" aktiviert die GCS-Persistenz (Default: false)
  GCS_SQLITE_BUCKET               - Name des GCS-Buckets
  GCS_SQLITE_OBJECT               - Objektname (Dateiname) im Bucket
  GCS_SQLITE_SYNC_INTERVAL_SECONDS - Sync-Intervall in Sekunden (Default: 30)

Der Zugriff erfolgt ausschließlich über Application Default Credentials
(Cloud-Run-Service-Account). Es werden keine Secrets, Tokens oder
Credentials geloggt.
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def is_gcs_enabled() -> bool:
    """Liefert True, wenn die GCS-Persistenz aktiviert ist."""
    return os.getenv("GCS_SQLITE_ENABLED", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def get_bucket_name() -> str:
    """Liefert den konfigurierten GCS-Bucket-Namen."""
    return os.getenv("GCS_SQLITE_BUCKET", "")


def get_object_name() -> str:
    """Liefert den konfigurierten GCS-Objektnamen (Dateiname)."""
    return os.getenv("GCS_SQLITE_OBJECT", "trainingsplanner.db")


def get_sync_interval_seconds() -> int:
    """Liefert das Sync-Intervall in Sekunden (mindestens 1)."""
    try:
        return max(1, int(os.getenv("GCS_SQLITE_SYNC_INTERVAL_SECONDS", "30")))
    except ValueError:
        return 30


def _get_bucket():
    """Liefert das GCS-Bucket-Objekt (Application Default Credentials)."""
    from google.cloud import storage

    client = storage.Client()
    return client.bucket(get_bucket_name())


def database_exists_in_storage() -> bool:
    """Prüft, ob das SQLite-Objekt im GCS-Bucket existiert.

    Liefert False, wenn das Objekt sicher nicht existiert. Wirft bei
    echten Fehlern (z. B. Auth-/Netzwerkfehler), damit der Startup
    entscheiden kann, ob ein gefährlicher Zustand vorliegt.
    """
    if not is_gcs_enabled():
        return False
    bucket = _get_bucket()
    blob = bucket.blob(get_object_name())
    return blob.exists()


def download_database(local_path: Path) -> bool:
    """Lädt die SQLite-Datei aus GCS nach local_path (atomar).

    - GCS deaktiviert: nichts tun, False.
    - Objekt existiert nicht: lokale DB nicht überschreiben, False.
    - Download: in temporäre Datei, dann atomar nach local_path verschieben.

    Die bestehende lokale Datenbank wird niemals zuerst gelöscht, bevor
    feststeht, dass der Download erfolgreich war.
    """
    if not is_gcs_enabled():
        return False

    local_path = Path(local_path)
    try:
        bucket = _get_bucket()
        blob = bucket.blob(get_object_name())
        if not blob.exists():
            logger.info("No SQLite database found in GCS; using local database")
            return False

        logger.info("Downloading SQLite database from GCS")
        # Parent-Verzeichnis bei Bedarf anlegen
        local_path.parent.mkdir(parents=True, exist_ok=True)

        # In temporäre Datei im selben Verzeichnis laden (für atomares Verschieben)
        fd, tmp_path = tempfile.mkstemp(dir=str(local_path.parent), suffix=".db.tmp")
        os.close(fd)
        tmp = Path(tmp_path)
        try:
            blob.download_to_filename(str(tmp))
            # Atomar verschieben – erst jetzt wird die lokale DB ersetzt
            shutil.move(str(tmp), str(local_path))
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)

        logger.info("SQLite database restored from GCS")
        return True
    except Exception as e:
        logger.error("GCS SQLite download failed: %s", e)
        return False


def upload_database(local_path: Path) -> bool:
    """Lädt die lokale SQLite-Datei nach GCS hoch.

    - GCS deaktiviert: nichts tun, False.
    - Lokale Datei fehlt: Fehler loggen, False.

    GCS-Object-Writes sind atomar, daher reicht ein normaler Upload.
    """
    if not is_gcs_enabled():
        return False

    local_path = Path(local_path)
    if not local_path.exists():
        logger.error(
            "GCS SQLite upload failed: local database file not found: %s", local_path
        )
        return False

    try:
        bucket = _get_bucket()
        blob = bucket.blob(get_object_name())
        blob.upload_from_filename(str(local_path))
        logger.info("SQLite database uploaded to GCS")
        return True
    except Exception as e:
        logger.error("GCS SQLite sync failed: %s", e)
        return False


def sync_database(local_path: Path) -> bool:
    """Zentraler Einstiegspunkt für den Upload der SQLite-Datei nach GCS."""
    return upload_database(local_path)
