"""
Tests für den sicheren, usergebundenen Strava-OAuth-State-Mechanismus.

Abgedeckte Fälle:
1. User A startet Strava OAuth → Callback mit gültigem State → Verbindung wird User A zugeordnet.
2. User B startet Strava OAuth → Callback mit gültigem State → Verbindung wird User B zugeordnet.
3. User A's State wird bei User B verwendet → Callback muss abgelehnt werden.
4. unbekannter State → Callback muss abgelehnt werden.
5. abgelaufener State → Callback muss abgelehnt werden.
6. bereits verwendeter State → Callback muss abgelehnt werden.
7. Nach erfolgreicher Verbindung darf User B ausschließlich seinen eigenen Strava Access Token verwenden.
8. User B ohne Strava-Verbindung darf niemals User A's Strava-Verbindung verwenden.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest

from app import database, strava
from app.models import OAuthState, User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """Verwendet eine temporäre SQLite-Datenbank für jeden Test.

    Setzt außerdem die Strava-Client-Credentials, damit get_client_id()
    und get_client_secret() funktionieren (der Token-Austausch wird in
    den Tests gemockt, die echten Werte sind daher irrelevant).
    """
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(database, "DB_PATH", db_file)
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setenv("STRAVA_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("STRAVA_CLIENT_SECRET", "test-client-secret")
    database.init_db()
    yield db_file
    # Hinweis: Die temporäre Datei wird von pytest (tmp_path) automatisch
    # aufgeräumt. Kein manuelles unlink, um Windows-File-Lock-Probleme zu vermeiden.



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


def _mock_token_exchange(monkeypatch, athlete_id="12345"):
    """Mockt den Strava-Token-Austausch (POST an STRAVA_TOKEN_URL)."""
    def fake_post(url, data=None, timeout=None, **kwargs):
        if url == strava.STRAVA_TOKEN_URL:
            resp = mock.Mock()
            resp.status_code = 200
            resp.json.return_value = {
                "access_token": f"access-token-{data.get('code', 'unknown')}",
                "refresh_token": f"refresh-token-{data.get('code', 'unknown')}",
                "expires_at": 9999999999,
                "athlete": {"id": athlete_id},
            }
            return resp
        raise AssertionError(f"Unerwartete URL: {url}")

    monkeypatch.setattr(strava.requests, "post", fake_post)


def _create_state(user_id: str, *, expires_in: int = 600) -> str:
    """Erzeugt einen gültigen OAuth-State für einen Benutzer."""
    now = datetime.now(timezone.utc)
    oauth_state = OAuthState(
        state=f"state-{user_id}-{now.timestamp()}",
        user_id=user_id,
        provider=strava.PROVIDER,
        created_at=now,
        expires_at=now + timedelta(seconds=expires_in),
    )
    database.create_oauth_state(oauth_state)
    return oauth_state.state


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_user_a_gets_connection_with_valid_state(users, monkeypatch):
    """Fall 1: User A startet OAuth → Callback mit gültigem State → Verbindung für User A."""
    _mock_token_exchange(monkeypatch)
    state = _create_state("user-a")

    result = strava.handle_callback("code-a", state, session_user_id="user-a")

    assert result == "user-a"
    account = database.get_connected_account("user-a", strava.PROVIDER)
    assert account is not None
    assert account.access_token == "access-token-code-a"
    # State wurde verbraucht (einmalige Verwendung)
    assert database.get_oauth_state(state) is None


def test_user_b_gets_connection_with_valid_state(users, monkeypatch):
    """Fall 2: User B startet OAuth → Callback mit gültigem State → Verbindung für User B."""
    _mock_token_exchange(monkeypatch)
    state = _create_state("user-b")

    result = strava.handle_callback("code-b", state, session_user_id="user-b")

    assert result == "user-b"
    account = database.get_connected_account("user-b", strava.PROVIDER)
    assert account is not None
    assert account.access_token == "access-token-code-b"
    # User A hat keine Verbindung
    assert database.get_connected_account("user-a", strava.PROVIDER) is None


def test_user_a_state_rejected_for_user_b(users, monkeypatch):
    """Fall 3: User A's State wird bei User B verwendet → Callback muss abgelehnt werden.

    Der State ist fest an User A gebunden. Ein Callback, der diesen State
    mit einem Code von User B einreicht, wird abgelehnt (CSRF-Schutz) –
    es wird weder für User B noch für User A eine Verbindung angelegt.
    """
    _mock_token_exchange(monkeypatch)
    state_a = _create_state("user-a")

    # User B (Session) versucht, User A's State zu verwenden
    result = strava.handle_callback("code-b", state_a, session_user_id="user-b")

    assert result is None
    # Keine Verbindung für User B angelegt
    assert database.get_connected_account("user-b", strava.PROVIDER) is None
    # Keine Verbindung für User A angelegt (State wurde nicht verbraucht,
    # da der CSRF-Check vor dem Token-Tausch fehlschlägt)
    assert database.get_connected_account("user-a", strava.PROVIDER) is None
    # Der State bleibt erhalten (wurde nicht verbraucht)
    assert database.get_oauth_state(state_a) is not None


def test_unknown_state_rejected(users, monkeypatch):
    """Fall 4: unbekannter State → Callback muss abgelehnt werden."""
    _mock_token_exchange(monkeypatch)

    result = strava.handle_callback("code-a", "state-does-not-exist", session_user_id="user-a")

    assert result is None
    assert database.get_connected_account("user-a", strava.PROVIDER) is None


def test_expired_state_rejected(users, monkeypatch):
    """Fall 5: abgelaufener State → Callback muss abgelehnt werden."""
    _mock_token_exchange(monkeypatch)
    # State mit negativer Gültigkeit (bereits abgelaufen)
    state = _create_state("user-a", expires_in=-10)

    result = strava.handle_callback("code-a", state, session_user_id="user-a")

    assert result is None
    assert database.get_connected_account("user-a", strava.PROVIDER) is None


def test_already_used_state_rejected(users, monkeypatch):
    """Fall 6: bereits verwendeter State → Callback muss abgelehnt werden."""
    _mock_token_exchange(monkeypatch)
    state = _create_state("user-a")

    # Erste Verwendung erfolgreich
    first = strava.handle_callback("code-a", state, session_user_id="user-a")
    assert first == "user-a"

    # Zweite Verwendung desselben States muss abgelehnt werden
    second = strava.handle_callback("code-a-again", state, session_user_id="user-a")
    assert second is None


def test_user_b_uses_only_own_token(users, monkeypatch):
    """Fall 7: Nach erfolgreicher Verbindung darf User B nur seinen eigenen Token verwenden."""
    _mock_token_exchange(monkeypatch)

    # User A verbindet
    state_a = _create_state("user-a")
    strava.handle_callback("code-a", state_a, session_user_id="user-a")

    # User B verbindet
    state_b = _create_state("user-b")
    strava.handle_callback("code-b", state_b, session_user_id="user-b")

    # User B's Token ist sein eigener, nicht User A's
    token_b = strava._get_access_token("user-b")
    assert token_b == "access-token-code-b"
    assert token_b != "access-token-code-a"

    # User A's Token ist sein eigener
    token_a = strava._get_access_token("user-a")
    assert token_a == "access-token-code-a"


def test_user_b_without_connection_never_uses_user_a(users, monkeypatch):
    """Fall 8: User B ohne Strava-Verbindung darf niemals User A's Verbindung verwenden."""
    _mock_token_exchange(monkeypatch)

    # Nur User A verbindet
    state_a = _create_state("user-a")
    strava.handle_callback("code-a", state_a, session_user_id="user-a")

    # User B hat keine Verbindung → kein Token
    assert database.get_connected_account("user-b", strava.PROVIDER) is None
    assert strava._get_access_token("user-b") is None

    # User B's Token ist NICHT User A's Token
    assert strava._get_access_token("user-b") != strava._get_access_token("user-a")



def test_auth_url_contains_random_state_not_user_id(users, monkeypatch):
    """Der State in der Auth-URL ist ein zufälliger Nonce, NICHT die rohe user_id."""
    url = strava.get_auth_url("user-a")
    assert "state=" in url
    # Die rohe user_id darf nicht als State erscheinen
    assert "state=user-a" not in url
    # Der State ist serverseitig gespeichert und dem User zugeordnet
    state_value = url.split("state=")[1]
    assert database.get_oauth_state(state_value) is not None
    assert database.get_oauth_state(state_value).user_id == "user-a"


def test_auth_url_states_are_unique(users):
    """Zwei Auth-URLs für denselben User erzeugen unterschiedliche States."""
    url1 = strava.get_auth_url("user-a")
    url2 = strava.get_auth_url("user-a")
    state1 = url1.split("state=")[1]
    state2 = url2.split("state=")[1]
    assert state1 != state2
