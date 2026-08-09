"""
Datenmodelle des TrainingsPlanners.

Enthält die Pydantic-Modelle für Ereignisse, Aktivitäten und Mahlzeiten.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from .timeutil import utc_now



class EventType(str, Enum):
    """Die unterstützten Ereignistypen."""

    TRAINING = "training"
    NUTRITION = "nutrition"
    SLEEP = "sleep"
    WEIGHT = "weight"
    BODY = "body"
    REGENERATION = "regeneration"
    ILLNESS = "illness"
    APPOINTMENT = "appointment"
    MEDICATION = "medication"
    NOTE = "note"


class User(BaseModel):
    """Ein registrierter Benutzer (Identität über Google)."""

    id: str
    google_id: str
    email: str
    display_name: Optional[str] = None
    picture_url: Optional[str] = None
    created_at: datetime
    last_login: datetime


class ConnectedAccount(BaseModel):
    """Eine externe Datenquelle, die ein Benutzer verbunden hat (z. B. Strava)."""

    id: str
    user_id: str
    provider: str  # z. B. "STRAVA", später "GARMIN", "ZWIFT", ...
    provider_user_id: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_at: Optional[int] = None


class OAuthState(BaseModel):
    """Ein serverseitig gespeicherter OAuth-State (Nonce) für einen OAuth-Flow.

    Der State wird beim Start des OAuth-Flows erzeugt, dem aktuellen User
    zugeordnet und serverseitig gespeichert. Beim Callback wird er validiert
    und nach erfolgreicher Verwendung gelöscht (einmalige Verwendung).
    """

    state: str
    user_id: str
    provider: str  # z. B. "STRAVA"
    created_at: datetime
    expires_at: datetime


class Session(BaseModel):
    """Eine serverseitig gespeicherte Login-Session.

    Die Session-ID ist ein kryptographisch zufälliger, opaker Wert, der
    ausschließlich als HttpOnly-Cookie an den Browser gegeben wird. Der
    Server löst die Session-ID bei jedem authentifizierten Request gegen
    die Datenbank auf und bezieht die user_id ausschließlich aus der
    serverseitig validierten Session.
    """

    id: str  # kryptographisch zufällige Session-ID (opaque)
    user_id: str
    created_at: datetime
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    user_agent: Optional[str] = None
    ip: Optional[str] = None




class CalendarEvent(BaseModel):
    """Ein Ereignis im Kalender."""

    id: str
    user_id: str
    event_type: EventType
    start: datetime
    end: datetime
    title: str
    description: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)



class NewCalendarEvent(BaseModel):
    """Eingabedaten zum Anlegen eines neuen Ereignisses."""

    event_type: EventType
    start: datetime
    end: datetime
    title: str
    description: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Activity(BaseModel):
    """Eine Strava-Aktivität."""

    id: str
    user_id: str
    strava_id: int
    name: str
    activity_type: str
    start_date: datetime
    distance_m: float
    moving_time_s: int
    elapsed_time_s: int
    total_elevation_gain_m: float
    average_speed_ms: float
    max_speed_ms: float
    average_heartrate: Optional[float] = None
    max_heartrate: Optional[float] = None
    calories: Optional[float] = None
    kudos_count: int = 0


class Meal(BaseModel):
    """Eine Mahlzeit mit KI-berechneten Kalorien."""

    id: str
    user_id: str
    date: datetime
    description: str
    calories: int
    protein_g: Optional[float] = None
    carbs_g: Optional[float] = None
    fat_g: Optional[float] = None
    provider: str = "deepseek"  # welcher KI-Provider die Schätzung gemacht hat
    created_at: datetime = Field(default_factory=utc_now)




class NewMeal(BaseModel):
    """Eingabedaten für eine neue Mahlzeit (Freitext)."""

    date: datetime
    description: str


class MealEstimate(BaseModel):
    """KI-Schätzung für eine Mahlzeit."""

    description: str
    calories: int
    protein_g: Optional[float] = None
    carbs_g: Optional[float] = None
    fat_g: Optional[float] = None
    provider: str
    time: Optional[str] = None  # Uhrzeit der Mahlzeit (HH:MM), falls gefunden
    valid: bool = True  # False, wenn die Eingabe keinen Sinn ergibt
    correction_message: Optional[str] = None  # Hinweis für Eingabekorrektur


