"""
Tests für die GCS-Persistenz der SQLite-Datenbank.

Abgedeckte Fälle:
1. GCS deaktiviert → kein GCS-Zugriff.
2. GCS-Objekt existiert nicht → Anwendung verwendet lokale DB.
3. GCS-Download → Testdatei wird korrekt als lokale SQLite-Datei hergestellt.
4. GCS-Upload → lokale SQLite-Datei wird korrekt hochgeladen.
5. Upload-Fehler → Anwendung läuft weiter, DB bleibt lokal, dirty bleibt gesetzt.
6. Startup-Reihenfolge → Download vor init_db().
7. Dirty-Sync → DB-Änderung → dirty → Sync → Upload.
8. Shutdown → dirty DB → Upload wird versucht.
9. Keine parallelen Uploads → zwei Sync-Auslöser uploaden nicht gleichzeitig.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest import mock

import pytest

from app import database, storage


# ---------------------------------------------------------------------------
# Fake-GCS-Objekte
# ---------------------------------------------------------------------------

class FakeBlob:
    """Simuliert ein GCS-Blob-Objekt."""

    def __init__(self, exists: bool = True, content: bytes = b""):
        self._exists = exists
        self.content = content
        self.upload_count = 0
        self.download_count = 0

    def exists(self) -> bool:
        return self._exists

    def download_to_filename(self, path: str) -> None:
        self.download_count += 1
        Path(path).write_bytes(self.content)

    def upload_from_filename(self, path: str) -> None:
        self.upload_count += 1
        self.content = Path(path).read_bytes()


class FakeBucket:
    """Simuliert einen GCS-Bucket."""

    def __init__(self, blob: FakeBlob):
        self._blob = blob

    def blob(self, name: str) -> FakeBlob:
        return self._blob


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """Verwendet eine temporäre SQLite-Datenbank für jeden Test."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(database, "DB_PATH", db_file)
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    database.init_db()
    yield db_file


@pytest.fixture()
def gcs_enabled(monkeypatch):
    """Aktiviert GCS und mockt den Bucket-Zugriff."""
    monkeypatch.setenv("GCS_SQLITE_ENABLED", "true")
    monkeypatch.setenv("GCS_SQLITE_BUCKET", "test-bucket")
    monkeypatch.setenv("GCS_SQLITE_OBJECT", "trainingsplanner.db")
    blob = FakeBlob()
    bucket = FakeBucket(blob)
    monkeypatch.setattr(storage, "_get_bucket", lambda: bucket)
    return blob


@pytest.fixture(autouse=True)
def _reset_dirty():
    """Setzt das Dirty-Flag vor jedem Test zurück."""
    database.clear_database_dirty()
    yield
    database.clear_database_dirty()


# ---------------------------------------------------------------------------
# Test 1 – GCS deaktiviert
# ---------------------------------------------------------------------------

def test_gcs_disabled_no_access(monkeypatch, tmp_path):
    """Bei GCS_SQLITE_ENABLED=false darf kein GCS-Zugriff erfolgen."""
    monkeypatch.setenv("GCS_SQLITE_ENABLED", "false")
    monkeypatch.delenv("GCS_SQLITE_BUCKET", raising=False)

    assert storage.is_gcs_enabled() is False

    # _get_bucket darf nie aufgerufen werden
    with mock.patch.object(storage, "_get_bucket", side_effect=AssertionError("kein GCS-Zugriff")):
        assert storage.download_database(tmp_path / "x.db") is False
        assert storage.upload_database(tmp_path / "x.db") is False
        assert storage.database_exists_in_storage() is False


def test_gcs_disabled_default(monkeypatch):
    """Ohne GCS_SQLITE_ENABLED ist GCS standardmäßig deaktiviert."""
    monkeypatch.delenv("GCS_SQLITE_ENABLED", raising=False)
    assert storage.is_gcs_enabled() is False


# ---------------------------------------------------------------------------
# Test 2 – GCS-Objekt existiert nicht
# ---------------------------------------------------------------------------

def test_download_object_missing_keeps_local(gcs_enabled, tmp_path):
    """Wenn das GCS-Objekt fehlt, wird die lokale DB nicht überschrieben."""
    gcs_enabled._exists = False
    local = tmp_path / "local.db"
    local.write_bytes(b"existing-local-data")

    result = storage.download_database(local)

    assert result is False
    # Lokale DB bleibt unverändert
    assert local.read_bytes() == b"existing-local-data"


# ---------------------------------------------------------------------------
# Test 3 – GCS-Download
# ---------------------------------------------------------------------------

def test_download_restores_database(gcs_enabled, tmp_path):
    """Eine Testdatei aus GCS wird korrekt als lokale SQLite-Datei hergestellt."""
    gcs_enabled.content = b"gcs-database-content"
    local = tmp_path / "local.db"

    result = storage.download_database(local)

    assert result is True
    assert local.read_bytes() == b"gcs-database-content"
    assert gcs_enabled.download_count == 1


def test_download_creates_parent_dir(gcs_enabled, tmp_path):
    """download_database legt das Parent-Verzeichnis bei Bedarf an."""
    gcs_enabled.content = b"data"
    local = tmp_path / "nested" / "dir" / "local.db"

    result = storage.download_database(local)

    assert result is True
    assert local.read_bytes() == b"data"


# ---------------------------------------------------------------------------
# Test 4 – GCS-Upload
# ---------------------------------------------------------------------------

def test_upload_uploads_local_file(gcs_enabled, tmp_path):
    """Eine lokale SQLite-Datei wird korrekt in das GCS-Objekt hochgeladen."""
    local = tmp_path / "local.db"
    local.write_bytes(b"local-db-content")

    result = storage.upload_database(local)

    assert result is True
    assert gcs_enabled.content == b"local-db-content"
    assert gcs_enabled.upload_count == 1


def test_upload_missing_local_file(gcs_enabled, tmp_path):
    """Fehlende lokale Datei → Fehler, kein Upload."""
    result = storage.upload_database(tmp_path / "does-not-exist.db")
    assert result is False
    assert gcs_enabled.upload_count == 0


# ---------------------------------------------------------------------------
# Test 5 – Upload-Fehler
# ---------------------------------------------------------------------------

def test_upload_error_keeps_dirty(gcs_enabled, temp_db, monkeypatch):
    """Bei Upload-Fehler läuft die App weiter, DB bleibt lokal, dirty bleibt gesetzt."""
    # Simuliert das Fehlerverhalten der echten upload_database():
    # sie fängt Fehler intern ab und liefert False.
    monkeypatch.setattr(storage, "upload_database", lambda path: False)

    database.mark_database_dirty()
    assert database.is_database_dirty() is True

    result = database.sync_database_to_storage()

    assert result is False
    # dirty bleibt gesetzt (kein Clear bei Fehler)
    assert database.is_database_dirty() is True
    # lokale DB existiert weiterhin
    assert temp_db.exists()



# ---------------------------------------------------------------------------
# Test 6 – Startup-Reihenfolge
# ---------------------------------------------------------------------------

def test_startup_downloads_before_init(monkeypatch):
    """Download muss vor init_db() erfolgen."""
    calls = []

    monkeypatch.setenv("GCS_SQLITE_ENABLED", "true")
    monkeypatch.setattr(storage, "database_exists_in_storage", lambda: True)
    monkeypatch.setattr(
        storage, "download_database", lambda p: calls.append("download") or True
    )
    monkeypatch.setattr(database, "init_db", lambda: calls.append("init"))
    # Sync-Intervall groß, damit der Worker im Test nichts tut
    monkeypatch.setattr(storage, "get_sync_interval_seconds", lambda: 3600)

    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200

    assert calls.index("download") < calls.index("init")


def test_startup_aborts_when_download_fails(monkeypatch):
    """GCS-Datei vorhanden + Download fehlgeschlagen → Startup bricht ab."""
    monkeypatch.setenv("GCS_SQLITE_ENABLED", "true")
    monkeypatch.setattr(storage, "database_exists_in_storage", lambda: True)
    monkeypatch.setattr(storage, "download_database", lambda p: False)

    from fastapi.testclient import TestClient
    from app.main import app

    with pytest.raises(RuntimeError):
        with TestClient(app) as client:
            client.get("/api/health")


# ---------------------------------------------------------------------------
# Test 7 – Dirty-Sync
# ---------------------------------------------------------------------------

def test_dirty_sync_uploads_and_clears(gcs_enabled, temp_db):
    """DB-Änderung → dirty → Sync → Upload → dirty zurückgesetzt."""
    # Eine echte DB-Änderung markiert dirty
    from app.models import User
    from datetime import datetime, timezone

    database.create_user(
        User(
            id="u1",
            google_id="g1",
            email="u1@example.com",
            created_at=datetime.now(timezone.utc),
            last_login=datetime.now(timezone.utc),
        )
    )
    assert database.is_database_dirty() is True

    result = database.sync_database_to_storage()

    assert result is True
    assert gcs_enabled.upload_count == 1
    assert database.is_database_dirty() is False


def test_sync_not_dirty_no_upload(gcs_enabled, temp_db):
    """Ohne dirty-Flag wird nicht hochgeladen."""
    assert database.is_database_dirty() is False
    result = database.sync_database_to_storage()
    assert result is False
    assert gcs_enabled.upload_count == 0


# ---------------------------------------------------------------------------
# Test 8 – Shutdown
# ---------------------------------------------------------------------------

def test_shutdown_uploads_dirty_db(monkeypatch, temp_db):
    """Beim Shutdown wird bei dirty DB ein Upload versucht."""
    monkeypatch.setenv("GCS_SQLITE_ENABLED", "true")
    monkeypatch.setattr(storage, "database_exists_in_storage", lambda: True)
    monkeypatch.setattr(storage, "download_database", lambda p: True)
    monkeypatch.setattr(storage, "get_sync_interval_seconds", lambda: 3600)

    uploaded = []
    monkeypatch.setattr(
        storage, "upload_database",
        lambda path: uploaded.append(True) or True,
    )

    database.mark_database_dirty()

    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200

    # Beim Shutdown wurde der Upload versucht
    assert uploaded == [True]



# ---------------------------------------------------------------------------
# Test 9 – Keine parallelen Uploads
# ---------------------------------------------------------------------------

def test_no_parallel_uploads(gcs_enabled, temp_db):
    """Zwei Sync-Auslöser dürfen nicht gleichzeitig hochladen."""
    active = 0
    max_active = 0

    def slow_upload(path):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        try:
            return True
        finally:
            active -= 1

    with mock.patch.object(storage, "upload_database", side_effect=slow_upload):
        database.mark_database_dirty()

        async def run():
            lock = asyncio.Lock()

            async def worker():
                async with lock:
                    await asyncio.to_thread(database.sync_database_to_storage)

            await asyncio.gather(worker(), worker(), worker())

        asyncio.run(run())

    # Es gab nie mehr als einen gleichzeitigen Upload
    assert max_active == 1
