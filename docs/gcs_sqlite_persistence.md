# GCS-Persistenz für die SQLite-Datenbank

Der TrainingsPlanner läuft auf Cloud Run (ephemeral Filesystem). Damit die
SQLite-Datenbank zwischen Instanzen und Neustarts erhalten bleibt, wird sie
in **Google Cloud Storage (GCS)** gespiegelt.

## Konzept

- **Download beim Startup** (vor `init_db()`): Die Datenbank wird aus GCS
  geladen, bevor die Anwendung auf sie zugreift.
- **Upload gesammelt**: Schreibzugriffe markieren die Datenbank als *dirty*.
  Ein Hintergrund-Worker lädt sie periodisch hoch; zusätzlich erfolgt ein
  Best-effort-Upload beim Shutdown.
- **Kein paralleler Upload**: Ein `asyncio.Lock` verhindert gleichzeitige
  Uploads (Worker + Shutdown).
- **Kein Busy Loop**: Der Worker schläft über das Sync-Intervall.

## Konfiguration (Environment-Variablen)

| Variable | Default | Beschreibung |
|---|---|---|
| `GCS_SQLITE_ENABLED` | `false` | `true` aktiviert die GCS-Persistenz |
| `GCS_SQLITE_BUCKET` | – | Name des GCS-Buckets |
| `GCS_SQLITE_OBJECT` | `trainingsplanner.db` | Objektname im Bucket |
| `GCS_SQLITE_SYNC_INTERVAL_SECONDS` | `30` | Sync-Intervall in Sekunden |

Lokal ist GCS standardmäßig deaktiviert – die Anwendung nutzt dann die
lokale `data/trainingsplanner.db`.

## Dateien

- `app/storage.py` – kapselt sämtliche GCS-Logik (Download/Upload, atomar).
- `app/database.py` – zentraler DB-Pfad (`get_database_path()`), Dirty-Flag
  (`mark_database_dirty` / `is_database_dirty` / `clear_database_dirty`),
  `sync_database_to_storage()`.
- `app/main.py` – FastAPI-Lifespan: Download vor `init_db()`, Hintergrund-
  Worker, Shutdown-Sync.

## Startup-Reihenfolge

```
GCS enabled?
  ├── ja + Objekt vorhanden → DB aus GCS herunterladen (vor init_db)
  ├── ja + Objekt fehlt     → lokale DB normal initialisieren
  └── nein                  → lokale DB normal initialisieren
→ init_db()
→ Hintergrund-Sync-Worker starten
```

**Fehlerfälle:**

- GCS-Datei vorhanden + Download schlägt fehl → **Startup bricht ab**
  (kein Start mit leerer DB, kein Datenverlust-Risiko).
- Laufzeit-Upload schlägt fehl → Anwendung läuft weiter, DB bleibt lokal,
  `dirty` bleibt gesetzt (nächster Sync versucht es erneut).

## Dirty-Flag (zentraler Mechanismus)

Der `_connect()`-Kontextmanager in `app/database.py` vergleicht
`conn.total_changes` vor/nach dem Kontext. Wurden schreibende Statements
(INSERT/UPDATE/DELETE) ausgeführt, wird `mark_database_dirty()` aufgerufen.
Dadurch müssen die einzelnen Repository-Methoden nicht angepasst werden.

## Tests

`tests/test_storage.py` deckt ab:

1. GCS deaktiviert → kein GCS-Zugriff.
2. GCS-Objekt existiert nicht → Anwendung verwendet lokale DB.
3. GCS-Download → Testdatei wird korrekt als lokale SQLite-Datei hergestellt.
4. GCS-Upload → lokale SQLite-Datei wird korrekt hochgeladen.
5. Upload-Fehler → Anwendung läuft weiter, DB bleibt lokal, dirty bleibt gesetzt.
6. Startup-Reihenfolge → Download vor `init_db()`.
7. Dirty-Sync → DB-Änderung → dirty → Sync → Upload → dirty zurückgesetzt.
8. Shutdown → dirty DB → Upload wird versucht.
9. Keine parallelen Uploads → zwei Sync-Auslöser uploaden nicht gleichzeitig.

## Deployment-Hinweis

Der GCS-Zugriff erfolgt über **Application Default Credentials** (der
Cloud-Run-Service-Account). Es werden keine Secrets, Tokens oder Credentials
geloggt. Der Service-Account benötigt die Rolle **Storage Object Admin**
(Lesen + Schreiben) auf dem Bucket.
