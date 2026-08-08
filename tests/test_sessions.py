"""
Tests für die serverseitigen Login-Sessions.

Abgedeckte Fälle:
1. Login erzeugt eine Session und setzt das tp_session-Cookie.
2. Ein authentifizierter Request mit gültigem Cookie liefert die richtige user_id.
3. Logout widerruft die Session serverseitig; ein altes Cookie liefert 401.
4. User-Wechsel: A → Logout → B → Request liefert user_id == B.
5. Session-Isolation: A darf keine Daten von B lesen und umgekehrt.
6. Mehrere Sessions desselben Users: Logout einer Session invalidiert nur diese.
7. Eine abgelaufene Session liefert 401.
8. Strava-Isolation: A und B haben getrennte Strava-Konten.
9. Strava nach User-Wechsel: B's Verbindung gehört B, A's bleibt unverändert.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
from fastapi import HTTPException
from fastapi.responses import Response

from app import auth, database, strava
from app.models import CalendarEvent, ConnectedAccount, Session, User



# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """Verwendet eine temporäre SQLite-Datenbank für jeden Test."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(database, "DB_PATH", db_file)
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setenv("STRAVA_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("STRAVA_CLIENT_SECRET", "test-client-secret")
    database.init_db()
    yield db_file


@pytest.fixture()
def users(temp_db):
    """Legt zwei Test-Benutzer (A und B) an."""
    now = datetime.now(timezone.utc)
    user_a = User(
        id="user-a",
        google_id="google-a",
        email="a@example.com",
        display_name="User A",
        created_at=now,
        last_login=now,
    )
    user_b = User(
        id="user-b",
        google_id="google-b",
        email="b@example.com",
        display_name="User B",
        created_at=now,
        last_login=now,
    )
    database.create_user(user_a)
    database.create_user(user_b)
    return {"a": user_a, "b": user_b}


def _make_request(session_id: str | None = None):
    """Erzeugt ein Mock-Request-Objekt mit optionalem tp_session-Cookie."""
    req = mock.Mock()
    req.headers = {"user-agent": "pytest"}
    req.client = mock.Mock()
    req.client.host = "127.0.0.1"
    cookies = {}
    if session_id:
        cookies[auth.SESSION_COOKIE] = session_id
    req.cookies = cookies
    return req


def _login(user_id: str, request=None) -> str:
    """Simuliert einen Login: erzeugt eine Session und liefert die Session-ID."""
    response = Response()
    auth.set_session_cookie(response, user_id, request)
    # Session-ID aus dem gesetzten Cookie extrahieren
    set_cookie = response.headers.get("set-cookie", "")
    # Format: tp_session=<id>; ...
    return set_cookie.split("=", 1)[1].split(";", 1)[0]


# ---------------------------------------------------------------------------
# Test 1 – Login erzeugt Session
# ---------------------------------------------------------------------------

def test_login_creates_session(users):
    """Login erzeugt eine Session mit richtiger user_id und setzt das Cookie."""
    request = _make_request()
    session_id = _login("user-a", request)

    # Cookie wurde gesetzt
    assert session_id

    # Session existiert serverseitig und gehört zu User A
    session = database.get_session_raw(session_id)
    assert session is not None
    assert session.user_id == "user-a"
    assert session.revoked_at is None

    # Session-ID ist opak und enthält keine User-Informationen
    assert "user-a" not in session_id
    assert "a@example.com" not in session_id


# ---------------------------------------------------------------------------
# Test 2 – Authentifizierter Request
# ---------------------------------------------------------------------------

def test_authenticated_request_returns_user_id(users):
    """Ein gültiges tp_session-Cookie liefert die richtige user_id."""
    session_id = _login("user-a")

    request = _make_request(session_id)
    user = auth.get_current_user(request)
    assert user.id == "user-a"

    # get_current_user_id liefert dieselbe ID
    assert auth.get_current_user_id(user) == "user-a"


def test_missing_cookie_returns_401(users):
    """Ohne Cookie liefert get_current_user 401."""
    request = _make_request(None)
    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(request)
    assert exc.value.status_code == 401


def test_unknown_session_returns_401(users):
    """Ein unbekanntes Cookie liefert 401."""
    request = _make_request("does-not-exist")
    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(request)
    assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# Test 3 – Logout (wichtigster Regressionstest)
# ---------------------------------------------------------------------------

def test_logout_revokes_session(users):
    """Nach Logout ist die Session revoked; ein altes Cookie liefert 401."""
    session_id = _login("user-a")

    # Vor Logout: gültig
    assert auth.get_current_user(_make_request(session_id)).id == "user-a"

    # Logout: Session serverseitig widerrufen
    revoked = auth.revoke_current_session(_make_request(session_id))
    assert revoked is True

    # Session ist jetzt revoked
    session = database.get_session_raw(session_id)
    assert session.revoked_at is not None

    # Altes Cookie liefert 401
    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(_make_request(session_id))
    assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# Test 4 – User-Wechsel
# ---------------------------------------------------------------------------

def test_user_switch_a_to_b(users):
    """A → Logout → B → Request liefert user_id == B."""
    session_a = _login("user-a")

    # A ist angemeldet
    assert auth.get_current_user(_make_request(session_a)).id == "user-a"

    # A loggt aus
    auth.revoke_current_session(_make_request(session_a))

    # B loggt ein (neue Session)
    session_b = _login("user-b")

    # B's Request liefert B
    assert auth.get_current_user(_make_request(session_b)).id == "user-b"

    # A's alte Session ist ungültig
    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(_make_request(session_a))
    assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# Test 5 – Session-Isolation
# ---------------------------------------------------------------------------

def test_session_isolation(users):
    """A darf keine Daten von B lesen und umgekehrt."""
    session_a = _login("user-a")
    session_b = _login("user-b")

    # Daten für A anlegen
    database.create_event(
        CalendarEvent(
            id="event-a",
            user_id="user-a",
            event_type="training",
            start=datetime.now(timezone.utc),
            end=datetime.now(timezone.utc) + timedelta(hours=1),
            title="A's Training",
        )
    )
    database.create_event(
        CalendarEvent(
            id="event-b",
            user_id="user-b",
            event_type="training",
            start=datetime.now(timezone.utc),
            end=datetime.now(timezone.utc) + timedelta(hours=1),
            title="B's Training",
        )
    )


    # A sieht nur A's Events
    user_a = auth.get_current_user(_make_request(session_a))
    events_a = database.get_events(user_a.id)
    assert [e.id for e in events_a] == ["event-a"]

    # B sieht nur B's Events
    user_b = auth.get_current_user(_make_request(session_b))
    events_b = database.get_events(user_b.id)
    assert [e.id for e in events_b] == ["event-b"]


# ---------------------------------------------------------------------------
# Test 6 – Mehrere Sessions desselben Users
# ---------------------------------------------------------------------------

def test_multiple_sessions_same_user(users):
    """Logout einer Session invalidiert nur diese, nicht die anderen."""
    session_a1 = _login("user-a")
    session_a2 = _login("user-a")

    # Beide Sessions sind gültig
    assert auth.get_current_user(_make_request(session_a1)).id == "user-a"
    assert auth.get_current_user(_make_request(session_a2)).id == "user-a"

    # Nur A1 wird widerrufen
    auth.revoke_current_session(_make_request(session_a1))

    # A1 ungültig
    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(_make_request(session_a1))
    assert exc.value.status_code == 401

    # A2 weiterhin gültig
    assert auth.get_current_user(_make_request(session_a2)).id == "user-a"


# ---------------------------------------------------------------------------
# Test 7 – Ablauf
# ---------------------------------------------------------------------------

def test_expired_session_returns_401(users):
    """Eine abgelaufene Session liefert 401."""
    now = datetime.now(timezone.utc)
    session = Session(
        id="expired-session",
        user_id="user-a",
        created_at=now - timedelta(days=8),
        expires_at=now - timedelta(days=1),  # bereits abgelaufen
    )
    database.create_session(session)

    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(_make_request("expired-session"))
    assert exc.value.status_code == 401


def test_delete_expired_sessions(users):
    """delete_expired_sessions entfernt abgelaufene/widerrufene Sessions."""
    now = datetime.now(timezone.utc)
    expired = Session(
        id="expired",
        user_id="user-a",
        created_at=now - timedelta(days=8),
        expires_at=now - timedelta(days=1),
    )
    active = Session(
        id="active",
        user_id="user-a",
        created_at=now,
        expires_at=now + timedelta(days=7),
    )
    database.create_session(expired)
    database.create_session(active)

    deleted = database.delete_expired_sessions(now)
    assert deleted == 1
    assert database.get_session_raw("expired") is None
    assert database.get_session_raw("active") is not None


# ---------------------------------------------------------------------------
# Test 8 – Strava-Isolation
# ---------------------------------------------------------------------------

def test_strava_isolation(users):
    """A und B haben getrennte Strava-Konten; Sync liefert nur eigene Daten."""
    # Verbundene Konten für A und B anlegen
    database.upsert_connected_account(
        ConnectedAccount(
            id="ca-a",
            user_id="user-a",
            provider=strava.PROVIDER,
            access_token="token-a",
            refresh_token="refresh-a",
            expires_at=9999999999,
        )
    )
    database.upsert_connected_account(
        ConnectedAccount(
            id="ca-b",
            user_id="user-b",
            provider=strava.PROVIDER,
            access_token="token-b",
            refresh_token="refresh-b",
            expires_at=9999999999,
        )
    )

    # A's Konto liefert nur A's Token
    account_a = database.get_connected_account("user-a", strava.PROVIDER)
    assert account_a.access_token == "token-a"

    # B's Konto liefert nur B's Token
    account_b = database.get_connected_account("user-b", strava.PROVIDER)
    assert account_b.access_token == "token-b"

    # Kein Cross-User-Zugriff: B's Token ist nie in A's Konto
    assert account_a.access_token != account_b.access_token


# ---------------------------------------------------------------------------
# Test 9 – Strava nach User-Wechsel
# ---------------------------------------------------------------------------

def test_strava_after_user_switch(users, monkeypatch):
    """Nach A → Logout → B gehört B's Strava-Verbindung B, A's bleibt unverändert."""
    # A hat bereits eine Strava-Verbindung
    database.upsert_connected_account(
        ConnectedAccount(
            id="ca-a",
            user_id="user-a",
            provider=strava.PROVIDER,
            access_token="token-a",
            refresh_token="refresh-a",
            expires_at=9999999999,
        )
    )

    # A loggt aus
    session_a = _login("user-a")
    auth.revoke_current_session(_make_request(session_a))

    # B loggt ein und verbindet Strava
    session_b = _login("user-b")
    user_b = auth.get_current_user(_make_request(session_b))
    assert user_b.id == "user-b"

    # B's Strava-Verbindung anlegen (simuliert den OAuth-Callback für B)
    database.upsert_connected_account(
        ConnectedAccount(
            id="ca-b",
            user_id="user-b",
            provider=strava.PROVIDER,
            access_token="token-b",
            refresh_token="refresh-b",
            expires_at=9999999999,
        )
    )

    # B's Verbindung gehört B
    account_b = database.get_connected_account("user-b", strava.PROVIDER)
    assert account_b.access_token == "token-b"

    # A's Verbindung bleibt unverändert
    account_a = database.get_connected_account("user-a", strava.PROVIDER)
    assert account_a.access_token == "token-a"
