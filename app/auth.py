"""
Authentifizierung und Session-Verwaltung.

Implementiert serverseitige Sessions: Die Session-ID ist ein
kryptographisch zufälliger, opaker Wert, der ausschließlich als
HttpOnly-Cookie an den Browser gegeben wird. Der Server löst die
Session-ID bei jedem authentifizierten Request gegen die Datenbank auf
und bezieht die user_id ausschließlich aus der serverseitig validierten
Session – nie aus Client-Parametern.

Der Benutzer wird ausschließlich über Google OAuth 2.0 / OpenID Connect
authentifiziert. Ein Logout widerruft die Session serverseitig (revoked_at),
sodass ein altes Cookie danach nicht mehr funktioniert.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import Response

from .database import (
    create_session,
    get_session,
    get_user,
    revoke_session,
)
from .models import Session, User


# Cookie-Name
SESSION_COOKIE = "tp_session"

# Gültigkeitsdauer einer Session in Sekunden (7 Tage)
SESSION_TTL_SECONDS = 7 * 24 * 3600


def _new_session_id() -> str:
    """Erzeugt eine kryptographisch zufällige, opake Session-ID.

    Die Session-ID enthält keine User-ID, E-Mail-Adresse oder sonstige
    Informationen.
    """
    return secrets.token_urlsafe(32)


def create_session_token(user_id: str) -> str:
    """Erstellt eine neue serverseitige Session und liefert deren ID.

    Hinweis: Der Name bleibt aus Kompatibilität erhalten, erzeugt aber
    keine JWT mehr, sondern eine serverseitige Session.
    """
    now = datetime.now(timezone.utc)
    session = Session(
        id=_new_session_id(),
        user_id=user_id,
        created_at=now,
        expires_at=now + timedelta(seconds=SESSION_TTL_SECONDS),
    )
    create_session(session)
    return session.id


def set_session_cookie(
    response: Response,
    user_id: str,
    request: Optional[Request] = None,
) -> None:
    """Erzeugt eine neue Session und setzt das Session-Cookie.

    Die Session wird serverseitig gespeichert und dem Benutzer zugeordnet.
    Das Cookie enthält ausschließlich die zufällige Session-ID.
    """
    now = datetime.now(timezone.utc)
    session = Session(
        id=_new_session_id(),
        user_id=user_id,
        created_at=now,
        expires_at=now + timedelta(seconds=SESSION_TTL_SECONDS),
        user_agent=request.headers.get("user-agent") if request else None,
        ip=request.client.host if request and request.client else None,
    )
    create_session(session)

    response.set_cookie(
        key=SESSION_COOKIE,
        value=session.id,
        httponly=True,
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Löscht das Session-Cookie im Browser."""
    response.delete_cookie(key=SESSION_COOKIE, path="/")


def revoke_current_session(request: Request) -> bool:
    """Widerruft die aktuelle Session serverseitig (revoked_at).

    Identifiziert die Session anhand des tp_session-Cookies und setzt
    revoked_at. Liefert True, wenn eine Session widerrufen wurde.
    """
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        return False
    return revoke_session(session_id)


def _get_session_user_id(request: Request) -> Optional[str]:
    """Löst die Session-ID aus dem Cookie gegen die Datenbank auf.

    Liefert die user_id nur, wenn die Session existiert, nicht widerrufen
    und noch nicht abgelaufen ist. Sonst None.
    """
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        return None
    session = get_session(session_id)
    if not session:
        return None
    return session.user_id


def get_current_user(request: Request) -> User:
    """FastAPI-Dependency: Liest den aktuellen Benutzer aus der Session.

    Wirft 401, wenn keine gültige Session vorhanden ist.
    """
    user_id = _get_session_user_id(request)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nicht angemeldet",
        )

    user = get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Benutzer nicht gefunden",
        )

    return user


def get_current_user_id(user: User = Depends(get_current_user)) -> str:
    """FastAPI-Dependency: Liefert nur die userId des aktuellen Benutzers."""
    return user.id
