"""
Konfiguration der Ereignistypen für die Darstellung.

Jeder Ereignistyp besitzt eine Farbe, ein Symbol und einen Anzeigenamen.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import EventType


@dataclass(frozen=True)
class EventTypeConfig:
    """Darstellungskonfiguration eines Ereignistyps."""

    label: str
    color: str
    symbol: str


# Zentrale Konfiguration aller Ereignistypen
EVENT_TYPE_CONFIG: dict[EventType, EventTypeConfig] = {
    EventType.TRAINING: EventTypeConfig("Training", "#e74c3c", "🏃"),
    EventType.NUTRITION: EventTypeConfig("Ernährung", "#27ae60", "🍽️"),
    EventType.SLEEP: EventTypeConfig("Schlaf", "#8e44ad", "😴"),
    EventType.WEIGHT: EventTypeConfig("Gewicht", "#f39c12", "⚖️"),
    EventType.BODY: EventTypeConfig("Körperwerte", "#16a085", "📏"),
    EventType.REGENERATION: EventTypeConfig("Regeneration", "#2980b9", "💆"),
    EventType.ILLNESS: EventTypeConfig("Krankheit", "#c0392b", "🤒"),
    EventType.APPOINTMENT: EventTypeConfig("Termin", "#2c3e50", "📅"),
    EventType.MEDICATION: EventTypeConfig("Medikamente", "#7f8c8d", "💊"),
    EventType.NOTE: EventTypeConfig("Notiz", "#95a5a6", "📝"),
}


def get_event_type_config(event_type: EventType) -> EventTypeConfig:
    """Liefert die Konfiguration für einen Ereignistyp."""
    return EVENT_TYPE_CONFIG[event_type]
