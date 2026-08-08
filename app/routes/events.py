"""
REST-Endpunkte für Ereignisse.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response

from ..auth import get_current_user_id
from ..database import (
    create_event,
    delete_event,
    get_event,
    get_events,
    update_event,
)
from ..models import CalendarEvent, NewCalendarEvent

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=list[CalendarEvent])
def list_events(user_id: str = Depends(get_current_user_id)) -> list[CalendarEvent]:
    """Liefert alle Ereignisse des aktuellen Benutzers."""
    return get_events(user_id)


@router.get("/{event_id}", response_model=CalendarEvent)
def get_single_event(
    event_id: str, user_id: str = Depends(get_current_user_id)
) -> CalendarEvent:
    """Liefert ein einzelnes Ereignis des aktuellen Benutzers."""
    event = get_event(user_id, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Ereignis nicht gefunden")
    return event


@router.post("", response_model=CalendarEvent, status_code=201)
def create_new_event(
    data: NewCalendarEvent, user_id: str = Depends(get_current_user_id)
) -> CalendarEvent:
    """Legt ein neues Ereignis an."""
    event = CalendarEvent(
        id=str(uuid.uuid4()),
        user_id=user_id,
        event_type=data.event_type,
        start=data.start,
        end=data.end,
        title=data.title,
        description=data.description,
        metadata=data.metadata,
    )
    return create_event(event)


@router.put("/{event_id}", response_model=CalendarEvent)
def update_existing_event(
    event_id: str, data: NewCalendarEvent, user_id: str = Depends(get_current_user_id)
) -> CalendarEvent:
    """Aktualisiert ein Ereignis."""
    event = CalendarEvent(
        id=event_id,
        user_id=user_id,
        event_type=data.event_type,
        start=data.start,
        end=data.end,
        title=data.title,
        description=data.description,
        metadata=data.metadata,
    )
    updated = update_event(event)
    if not updated:
        raise HTTPException(status_code=404, detail="Ereignis nicht gefunden")
    return updated


@router.delete("/{event_id}", status_code=204)
def delete_existing_event(
    event_id: str, user_id: str = Depends(get_current_user_id)
) -> Response:
    """Löscht ein Ereignis."""
    if not delete_event(user_id, event_id):
        raise HTTPException(status_code=404, detail="Ereignis nicht gefunden")
    return Response(status_code=204)
