"""
SQLite-Datenbankzugriff für den TrainingsPlanner.

Verwendet das eingebaute sqlite3-Modul. Die Datenbank liegt unter data/.

Alle fachlichen Daten (Events, Aktivitäten, Mahlzeiten) sind zwingend
einem Benutzer (user_id) zugeordnet. Die Repository-Methoden verlangen
user_id als Pflichtparameter – ein Vergessen der Filterung ist dadurch
praktisch unmöglich.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .models import (
    Activity,
    CalendarEvent,
    ConnectedAccount,
    EventType,
    Meal,
    OAuthState,
    Session,
    User,
)
from .timeutil import ensure_utc, utc_now, utc_to_local



logger = logging.getLogger(__name__)


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def get_database_path() -> Path:
    """Liefert den zentralen Pfad zur SQLite-Datenbank.

    Default: data/trainingsplanner.db
    """
    return DATA_DIR / "trainingsplanner.db"


DB_PATH = get_database_path()


# ---------------------------------------------------------------------------
# Dirty-Flag für die GCS-Synchronisation
# ---------------------------------------------------------------------------
# Wird gesetzt, wenn die Datenbank geschrieben wurde und noch nicht nach
# GCS synchronisiert wurde. Der Upload erfolgt gesammelt (periodisch bzw.
# beim Shutdown), nicht nach jedem einzelnen SQL-Statement.
_database_dirty = False
_dirty_lock = threading.Lock()


def mark_database_dirty() -> None:
    """Markiert die Datenbank als geändert (dirty)."""
    global _database_dirty
    with _dirty_lock:
        _database_dirty = True


def is_database_dirty() -> bool:
    """Liefert True, wenn die Datenbank geändert und noch nicht synchronisiert wurde."""
    with _dirty_lock:
        return _database_dirty


def clear_database_dirty() -> None:
    """Setzt das Dirty-Flag zurück (nach erfolgreichem Sync)."""
    global _database_dirty
    with _dirty_lock:
        _database_dirty = False


def sync_database_to_storage() -> bool:
    """Zentraler Einstiegspunkt für den Upload der Datenbank nach GCS.

    Lädt die Datenbank nur hoch, wenn sie als dirty markiert ist und GCS
    aktiviert ist. Setzt das Dirty-Flag nach erfolgreichem Upload zurück.
    """
    from . import storage

    if not storage.is_gcs_enabled():
        return False
    if not is_database_dirty():
        return False
    ok = storage.upload_database(DB_PATH)
    if ok:
        clear_database_dirty()
    return ok



@contextmanager
def _connect():
    """Öffnet eine Verbindung zur Datenbank und aktiviert Row-Factory.

    Markiert die Datenbank als dirty, wenn innerhalb des Kontexts
    schreibende Statements (INSERT/UPDATE/DELETE) ausgeführt wurden.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        before = conn.total_changes
        yield conn
        conn.commit()
        if conn.total_changes > before:
            mark_database_dirty()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()



def init_db() -> None:
    """Erstellt die Tabellen, falls sie nicht existieren."""
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                google_id TEXT UNIQUE NOT NULL,
                email TEXT NOT NULL,
                display_name TEXT,
                picture_url TEXT,
                created_at TEXT NOT NULL,
                last_login TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS connected_accounts (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                provider_user_id TEXT,
                access_token TEXT,
                refresh_token TEXT,
                expires_at INTEGER,
                UNIQUE(user_id, provider)
            );

            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                event_type TEXT NOT NULL,
                start TEXT NOT NULL,
                end TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                metadata TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS activities (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                strava_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                activity_type TEXT NOT NULL,
                start_date TEXT NOT NULL,
                distance_m REAL NOT NULL DEFAULT 0,
                moving_time_s INTEGER NOT NULL DEFAULT 0,
                elapsed_time_s INTEGER NOT NULL DEFAULT 0,
                total_elevation_gain_m REAL NOT NULL DEFAULT 0,
                average_speed_ms REAL NOT NULL DEFAULT 0,
                max_speed_ms REAL NOT NULL DEFAULT 0,
                average_heartrate REAL,
                max_heartrate REAL,
                calories REAL,
                kudos_count INTEGER NOT NULL DEFAULT 0,
                UNIQUE(user_id, strava_id)
            );

            CREATE TABLE IF NOT EXISTS meals (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                date TEXT NOT NULL,
                description TEXT NOT NULL,
                calories INTEGER NOT NULL,
                protein_g REAL,
                carbs_g REAL,
                fat_g REAL,
                provider TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS oauth_states (
                state TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                user_agent TEXT,
                ip TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_events_user_id ON events(user_id);
            CREATE INDEX IF NOT EXISTS idx_activities_user_id ON activities(user_id);
            CREATE INDEX IF NOT EXISTS idx_meals_user_id ON meals(user_id);
            CREATE INDEX IF NOT EXISTS idx_connected_accounts_user_id ON connected_accounts(user_id);
            CREATE INDEX IF NOT EXISTS idx_oauth_states_user_id ON oauth_states(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
            """
        )




# ============================================================
# Benutzer
# ============================================================

def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        google_id=row["google_id"],
        email=row["email"],
        display_name=row["display_name"],
        picture_url=row["picture_url"],
        created_at=datetime.fromisoformat(row["created_at"]),
        last_login=datetime.fromisoformat(row["last_login"]),
    )


def get_user_by_google_id(google_id: str) -> Optional[User]:
    """Liefert einen Benutzer anhand seiner Google-ID."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE google_id = ?", (google_id,)
        ).fetchone()
    return _row_to_user(row) if row else None


def get_user(user_id: str) -> Optional[User]:
    """Liefert einen Benutzer anhand seiner internen ID."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_user(row) if row else None


def create_user(user: User) -> User:
    """Legt einen neuen Benutzer an."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO users (id, google_id, email, display_name, picture_url, created_at, last_login)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user.id,
                user.google_id,
                user.email,
                user.display_name,
                user.picture_url,
                user.created_at.isoformat(),
                user.last_login.isoformat(),
            ),
        )
    return user


def update_user_last_login(user_id: str, last_login: datetime) -> None:
    """Aktualisiert den letzten Login-Zeitpunkt eines Benutzers."""
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (last_login.isoformat(), user_id),
        )


# ============================================================
# Verbundene Konten (ConnectedAccount)
# ============================================================

def _row_to_connected_account(row: sqlite3.Row) -> ConnectedAccount:
    return ConnectedAccount(
        id=row["id"],
        user_id=row["user_id"],
        provider=row["provider"],
        provider_user_id=row["provider_user_id"],
        access_token=row["access_token"],
        refresh_token=row["refresh_token"],
        expires_at=row["expires_at"],
    )


def get_connected_account(user_id: str, provider: str) -> Optional[ConnectedAccount]:
    """Liefert ein verbundenes Konto für einen Benutzer und Provider."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM connected_accounts WHERE user_id = ? AND provider = ?",
            (user_id, provider),
        ).fetchone()
    return _row_to_connected_account(row) if row else None


def get_connected_accounts(user_id: str) -> list[ConnectedAccount]:
    """Liefert alle verbundenen Konten eines Benutzers."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM connected_accounts WHERE user_id = ? ORDER BY provider",
            (user_id,),
        ).fetchall()
    return [_row_to_connected_account(r) for r in rows]


def upsert_connected_account(account: ConnectedAccount) -> ConnectedAccount:
    """Fügt ein verbundenes Konto ein oder aktualisiert es."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO connected_accounts (
                id, user_id, provider, provider_user_id, access_token, refresh_token, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, provider) DO UPDATE SET
                provider_user_id = excluded.provider_user_id,
                access_token = excluded.access_token,
                refresh_token = excluded.refresh_token,
                expires_at = excluded.expires_at
            """,
            (
                account.id,
                account.user_id,
                account.provider,
                account.provider_user_id,
                account.access_token,
                account.refresh_token,
                account.expires_at,
            ),
        )
    return account


def delete_connected_account(user_id: str, provider: str) -> bool:
    """Löscht ein verbundenes Konto."""
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM connected_accounts WHERE user_id = ? AND provider = ?",
            (user_id, provider),
        )
    return cur.rowcount > 0


# ============================================================
# OAuth-States (Nonce für OAuth-Flows)
# ============================================================

def _row_to_oauth_state(row: sqlite3.Row) -> OAuthState:
    return OAuthState(
        state=row["state"],
        user_id=row["user_id"],
        provider=row["provider"],
        created_at=datetime.fromisoformat(row["created_at"]),
        expires_at=datetime.fromisoformat(row["expires_at"]),
    )


def create_oauth_state(state: OAuthState) -> OAuthState:
    """Legt einen OAuth-State an und ordnet ihn einem Benutzer zu."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO oauth_states (state, user_id, provider, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                state.state,
                state.user_id,
                state.provider,
                state.created_at.isoformat(),
                state.expires_at.isoformat(),
            ),
        )
    return state


def get_oauth_state(state: str) -> Optional[OAuthState]:
    """Liefert einen OAuth-State anhand seines Werts."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM oauth_states WHERE state = ?", (state,)
        ).fetchone()
    return _row_to_oauth_state(row) if row else None


def consume_oauth_state(state: str) -> bool:
    """Löscht einen OAuth-State (einmalige Verwendung).

    Liefert True, wenn ein State gelöscht wurde, sonst False.
    """
    with _connect() as conn:
        cur = conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
    return cur.rowcount > 0


def delete_expired_oauth_states(now: datetime) -> int:
    """Löscht alle abgelaufenen OAuth-States.

    Liefert die Anzahl der gelöschten Zeilen.
    """
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM oauth_states WHERE expires_at <= ?", (now.isoformat(),)
        )
    return cur.rowcount


# ============================================================
# Sessions (serverseitige Login-Sessions)
# ============================================================

def _row_to_session(row: sqlite3.Row) -> Session:
    return Session(
        id=row["id"],
        user_id=row["user_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        expires_at=datetime.fromisoformat(row["expires_at"]),
        revoked_at=datetime.fromisoformat(row["revoked_at"]) if row["revoked_at"] else None,
        user_agent=row["user_agent"],
        ip=row["ip"],
    )


def create_session(session: Session) -> Session:
    """Legt eine neue Session an und ordnet sie einem Benutzer zu."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO sessions (id, user_id, created_at, expires_at, revoked_at, user_agent, ip)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.id,
                session.user_id,
                session.created_at.isoformat(),
                session.expires_at.isoformat(),
                session.revoked_at.isoformat() if session.revoked_at else None,
                session.user_agent,
                session.ip,
            ),
        )
    return session


def get_session(session_id: str) -> Optional[Session]:
    """Liefert eine Session anhand ihrer ID.

    Liefert nur dann eine Session zurück, wenn sie existiert, nicht
    widerrufen (revoked_at IS NULL) und noch nicht abgelaufen ist.
    """
    now = utc_now()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM sessions
            WHERE id = ? AND revoked_at IS NULL AND expires_at > ?
            """,
            (session_id, now.isoformat()),
        ).fetchone()
    return _row_to_session(row) if row else None



def get_session_raw(session_id: str) -> Optional[Session]:
    """Liefert eine Session anhand ihrer ID, ohne Gültigkeitsprüfung.

    Wird für Tests und für die Logout-Revocation benötigt, um auch
    bereits abgelaufene oder widerrufene Sessions zu sehen.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    return _row_to_session(row) if row else None


def revoke_session(session_id: str) -> bool:
    """Widerruft eine Session (setzt revoked_at).

    Liefert True, wenn eine Session widerrufen wurde, sonst False.
    """
    now = utc_now()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
            (now.isoformat(), session_id),
        )
    return cur.rowcount > 0



def delete_expired_sessions(now: datetime) -> int:
    """Löscht alle abgelaufenen oder widerrufenen Sessions.

    Liefert die Anzahl der gelöschten Zeilen.
    """
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM sessions WHERE expires_at <= ? OR revoked_at IS NOT NULL",
            (now.isoformat(),),
        )
    return cur.rowcount


# ============================================================
# Ereignisse
# ============================================================



def _row_to_event(row: sqlite3.Row) -> CalendarEvent:
    return CalendarEvent(
        id=row["id"],
        user_id=row["user_id"],
        event_type=EventType(row["event_type"]),
        start=datetime.fromisoformat(row["start"]),
        end=datetime.fromisoformat(row["end"]),
        title=row["title"],
        description=row["description"],
        metadata=json.loads(row["metadata"]),
    )


def get_events(user_id: str) -> list[CalendarEvent]:
    """Liefert alle Ereignisse eines Benutzers."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE user_id = ? ORDER BY start", (user_id,)
        ).fetchall()
    return [_row_to_event(r) for r in rows]


def get_event(user_id: str, event_id: str) -> Optional[CalendarEvent]:
    """Liefert ein einzelnes Ereignis eines Benutzers."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM events WHERE id = ? AND user_id = ?", (event_id, user_id)
        ).fetchone()
    return _row_to_event(row) if row else None


def create_event(event: CalendarEvent) -> CalendarEvent:
    """Legt ein neues Ereignis an."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO events (id, user_id, event_type, start, end, title, description, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.user_id,
                event.event_type.value,
                event.start.isoformat(),
                event.end.isoformat(),
                event.title,
                event.description,
                json.dumps(event.metadata),
            ),
        )
    return event


def update_event(event: CalendarEvent) -> Optional[CalendarEvent]:
    """Aktualisiert ein Ereignis."""
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE events
            SET event_type = ?, start = ?, end = ?, title = ?, description = ?, metadata = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                event.event_type.value,
                event.start.isoformat(),
                event.end.isoformat(),
                event.title,
                event.description,
                json.dumps(event.metadata),
                event.id,
                event.user_id,
            ),
        )
        if cur.rowcount == 0:
            return None
    return event


def delete_event(user_id: str, event_id: str) -> bool:
    """Löscht ein Ereignis."""
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM events WHERE id = ? AND user_id = ?", (event_id, user_id)
        )
    return cur.rowcount > 0


# ============================================================
# Aktivitäten (Strava)
# ============================================================

def _row_to_activity(row: sqlite3.Row) -> Activity:
    return Activity(
        id=row["id"],
        user_id=row["user_id"],
        strava_id=row["strava_id"],
        name=row["name"],
        activity_type=row["activity_type"],
        start_date=ensure_utc(datetime.fromisoformat(row["start_date"])),
        distance_m=row["distance_m"],

        moving_time_s=row["moving_time_s"],
        elapsed_time_s=row["elapsed_time_s"],
        total_elevation_gain_m=row["total_elevation_gain_m"],
        average_speed_ms=row["average_speed_ms"],
        max_speed_ms=row["max_speed_ms"],
        average_heartrate=row["average_heartrate"],
        max_heartrate=row["max_heartrate"],
        calories=row["calories"],
        kudos_count=row["kudos_count"],
    )


def get_activities(user_id: str) -> list[Activity]:
    """Liefert alle Aktivitäten eines Benutzers."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM activities WHERE user_id = ? ORDER BY start_date DESC",
            (user_id,),
        ).fetchall()
    return [_row_to_activity(r) for r in rows]


def upsert_activity(activity: Activity) -> Activity:
    """Fügt eine Aktivität ein oder aktualisiert sie (basierend auf strava_id)."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO activities (
                id, user_id, strava_id, name, activity_type, start_date, distance_m,
                moving_time_s, elapsed_time_s, total_elevation_gain_m,
                average_speed_ms, max_speed_ms, average_heartrate,
                max_heartrate, calories, kudos_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, strava_id) DO UPDATE SET
                name = excluded.name,
                activity_type = excluded.activity_type,
                start_date = excluded.start_date,
                distance_m = excluded.distance_m,
                moving_time_s = excluded.moving_time_s,
                elapsed_time_s = excluded.elapsed_time_s,
                total_elevation_gain_m = excluded.total_elevation_gain_m,
                average_speed_ms = excluded.average_speed_ms,
                max_speed_ms = excluded.max_speed_ms,
                average_heartrate = excluded.average_heartrate,
                max_heartrate = excluded.max_heartrate,
                calories = excluded.calories,
                kudos_count = excluded.kudos_count
            """,
            (
                activity.id,
                activity.user_id,
                activity.strava_id,
                activity.name,
                activity.activity_type,
                activity.start_date.isoformat(),
                activity.distance_m,
                activity.moving_time_s,
                activity.elapsed_time_s,
                activity.total_elevation_gain_m,
                activity.average_speed_ms,
                activity.max_speed_ms,
                activity.average_heartrate,
                activity.max_heartrate,
                activity.calories,
                activity.kudos_count,
            ),
        )
    return activity


# ============================================================
# Mahlzeiten
# ============================================================

def _row_to_meal(row: sqlite3.Row) -> Meal:
    return Meal(
        id=row["id"],
        user_id=row["user_id"],
        date=ensure_utc(datetime.fromisoformat(row["date"])),
        description=row["description"],
        calories=row["calories"],
        protein_g=row["protein_g"],
        carbs_g=row["carbs_g"],
        fat_g=row["fat_g"],
        provider=row["provider"],
        created_at=ensure_utc(datetime.fromisoformat(row["created_at"])),
    )



def get_meals(user_id: str) -> list[Meal]:
    """Liefert alle Mahlzeiten eines Benutzers."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM meals WHERE user_id = ? ORDER BY date DESC", (user_id,)
        ).fetchall()
    return [_row_to_meal(r) for r in rows]


def get_meals_for_date(user_id: str, date: datetime) -> list[Meal]:
    """Liefert alle Mahlzeiten eines Benutzers für einen bestimmten Tag.

    Der übergebene Zeitpunkt ist UTC (Mitternacht des lokalen Tages, nach
    UTC konvertiert). Es werden alle Mahlzeiten geliefert, deren lokales
    Europe/Berlin-Datum dem lokalen Tag des angefragten Zeitpunkts entspricht.
    """
    # Alle Mahlzeiten des Benutzers laden und in Python filtern,
    # um Zeitzonen korrekt zu behandeln
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM meals WHERE user_id = ?", (user_id,)
        ).fetchall()
    meals = [_row_to_meal(r) for r in rows]

    # Lokales Datum des angefragten Tages (Europe/Berlin)
    target_date = utc_to_local(date).date()

    # Mahlzeiten filtern, deren lokales Datum dem angefragten Tag entspricht
    result = []
    for meal in meals:
        # Mahlzeit (UTC) in lokale Europe/Berlin-Zeit umwandeln
        meal_local = utc_to_local(meal.date)
        if meal_local.date() == target_date:
            result.append(meal)

    # Nach Datum sortieren
    result.sort(key=lambda m: m.date)
    return result



def create_meal(meal: Meal) -> Meal:
    """Legt eine neue Mahlzeit an.

    Der Zeitpunkt wird als UTC, timezone-aware gespeichert.
    """
    # Sicherstellen, dass der Zeitpunkt UTC ist (naive Werte als UTC interpretieren)
    meal.date = ensure_utc(meal.date)
    meal.created_at = ensure_utc(meal.created_at)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO meals (id, user_id, date, description, calories, protein_g, carbs_g, fat_g, provider, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                meal.id,
                meal.user_id,
                meal.date.isoformat(),
                meal.description,
                meal.calories,
                meal.protein_g,
                meal.carbs_g,
                meal.fat_g,
                meal.provider,
                meal.created_at.isoformat(),
            ),
        )
    return meal



def delete_meal(user_id: str, meal_id: str) -> bool:
    """Löscht eine Mahlzeit."""
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM meals WHERE id = ? AND user_id = ?", (meal_id, user_id)
        )
    return cur.rowcount > 0
