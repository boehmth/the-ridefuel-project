"""
KI-Service für die Kalorien-Schätzung von Mahlzeiten.

Nimmt einen Freitext (z. B. "2 Scheiben Vollkornbrot mit Käse um 12:30") und lässt
eine KI (DeepSeek oder Gemini) die Kalorien schätzen und die Uhrzeit extrahieren.
"""
from __future__ import annotations

import os
import re
from typing import Any

from .ai import deepseek, gemini
from .models import MealEstimate

# System-Prompt für die Kalorien-Schätzung
SYSTEM_PROMPT = """
Du bist ein Ernährungsexperte. Du erhältst eine Beschreibung einer Mahlzeit
in Freitextform. Schätze die Nährwerte realistisch ein.

Die Beschreibung kann eine Uhrzeit enthalten (z. B. "um 12:30", "12:30 Uhr",
"mittags", "abends"). Extrahiere die Uhrzeit, falls vorhanden.

Antworte ausschließlich als JSON-Objekt mit folgenden Feldern:
{
  "calories": <ganze Zahl, geschätzte Kilokalorien>,
  "protein_g": <Gramm Protein, optional>,
  "carbs_g": <Gramm Kohlenhydrate, optional>,
  "fat_g": <Gramm Fett, optional>,
  "time": <Uhrzeit im Format HH:MM, oder null wenn keine Uhrzeit gefunden>,
  "valid": <true oder false>,
  "correction_message": <String mit Hinweis zur Eingabekorrektur, oder null>
}

Regeln:
- Wenn die Beschreibung eine Uhrzeit enthält, extrahiere sie im Format HH:MM.
- Wenn die Beschreibung keinen Sinn ergibt (z. B. "asdf", "xyz", leere Eingabe),
  setze valid auf false und gib eine verständliche correction_message an.
- Wenn die Beschreibung sinnvoll ist, aber keine Uhrzeit enthält, setze valid auf
  true, time auf null und correction_message auf null.
- Wenn die Beschreibung sinnvoll ist und eine Uhrzeit enthält, setze valid auf true,
  time auf die Uhrzeit und correction_message auf null.
"""


def _get_provider() -> str:
    """Liefert den konfigurierten KI-Provider (deepseek oder gemini)."""
    return os.getenv("MEAL_AI_PROVIDER", "deepseek").lower()


def estimate_meal(description: str) -> MealEstimate:
    """
    Schätzt die Kalorien einer Mahlzeit per KI und extrahiert die Uhrzeit.

    Args:
        description: Freitext-Beschreibung der Mahlzeit.

    Returns:
        MealEstimate mit Kalorien, Makronährstoffen, Uhrzeit und Validierungsstatus.
    """
    provider = _get_provider()

    if provider == "gemini":
        result = gemini.call_llm(SYSTEM_PROMPT, description)
        provider_name = "gemini"
    else:
        result = deepseek.call_llm(SYSTEM_PROMPT, description)
        provider_name = "deepseek"

    # Fehlerbehandlung
    if "error" in result:
        raise RuntimeError(f"KI-Fehler: {result.get('error')}")

    # Validierung
    valid = result.get("valid", True)
    correction_message = result.get("correction_message")

    # Wenn die Eingabe keinen Sinn ergibt, Fehler werfen
    if not valid:
        msg = correction_message or "Die Eingabe konnte nicht verstanden werden. Bitte beschreibe die Mahlzeit genauer."
        raise ValueError(msg)

    # Werte extrahieren (mit Fallbacks)
    calories = int(result.get("calories", 0))
    protein = _to_float(result.get("protein_g"))
    carbs = _to_float(result.get("carbs_g"))
    fat = _to_float(result.get("fat_g"))
    time_str = result.get("time")

    # Uhrzeit validieren und normalisieren
    if time_str:
        time_str = _normalize_time(time_str)

    return MealEstimate(
        description=description,
        calories=calories,
        protein_g=protein,
        carbs_g=carbs,
        fat_g=fat,
        provider=provider_name,
        time=time_str,
        valid=True,
        correction_message=None,
    )


def _to_float(value: Any) -> float | None:
    """Wandelt einen Wert in float um (oder None bei Fehler)."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_time(time_str: str) -> str | None:
    """Normalisiert eine Uhrzeit auf das Format HH:MM."""
    # Formate: "12:30", "12:30 Uhr", "12.30", "12 Uhr", "12h30"
    match = re.search(r"(\d{1,2})[:.](\d{2})", time_str)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"

    # Nur Stunde: "12 Uhr", "12h"
    match = re.search(r"(\d{1,2})\s*(?:Uhr|h)", time_str, re.IGNORECASE)
    if match:
        hour = int(match.group(1))
        if 0 <= hour <= 23:
            return f"{hour:02d}:00"

    return None
