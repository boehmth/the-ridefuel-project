"""
Debug-Tool: Inhalt der SQLite-Datenbank anzeigen.

Gibt den Inhalt aller Tabellen (oder einer ausgewählten Tabelle) als
lesbare Tabelle auf der Konsole aus. Nützlich zum Debuggen von
Trainings, Mahlzeiten, Benutzern usw.

Verwendung:
    python db_dump.py                 # alle Tabellen
    python db_dump.py meals           # nur die Tabelle "meals"
    python db_dump.py users events    # mehrere Tabellen

Sensible Spalten (z. B. access_token, refresh_token) werden maskiert.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from app.database import get_database_path

# Spalten, deren Inhalt aus Sicherheitsgründen maskiert wird
SENSITIVE_COLUMNS = {"access_token", "refresh_token", "google_id"}

# Tabellen, die standardmäßig angezeigt werden (in sinnvoller Reihenfolge)
DEFAULT_TABLES = [
    "users",
    "connected_accounts",
    "events",
    "activities",
    "meals",
    "sessions",
    "oauth_states",
]


def _mask(value: str) -> str:
    """Maskiert einen sensiblen Wert (zeigt nur die ersten 6 Zeichen)."""
    if value is None:
        return "NULL"
    s = str(value)
    if len(s) <= 6:
        return "***"
    return f"{s[:6]}…"


def _format_value(value, column: str) -> str:
    """Formatiert einen Zellenwert für die Ausgabe."""
    if value is None:
        return "NULL"
    if column in SENSITIVE_COLUMNS:
        return _mask(value)
    return str(value)


def _print_table(conn: sqlite3.Connection, table: str) -> None:
    """Gibt den Inhalt einer Tabelle als Tabelle aus."""
    try:
        cur = conn.execute(f"SELECT * FROM {table}")
    except sqlite3.OperationalError as e:
        print(f"  ⚠️  Tabelle '{table}' konnte nicht gelesen werden: {e}")
        return

    rows = cur.fetchall()
    columns = [d[0] for d in cur.description]

    print(f"\n=== {table} ({len(rows)} Zeilen) ===")
    if not rows:
        print("  (leer)")
        return

    # Zellen formatieren
    formatted = [
        [_format_value(r[col], col) for col in columns]
        for r in rows
    ]

    # Spaltenbreiten berechnen
    widths = [
        max(len(col), *(len(row[i]) for row in formatted))
        for i, col in enumerate(columns)
    ]

    # Kopfzeile
    header = " | ".join(col.ljust(widths[i]) for i, col in enumerate(columns))
    print("  " + header)
    print("  " + "-" * len(header))

    # Zeilen
    for row in formatted:
        line = " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))
        print("  " + line)


def main() -> None:
    db_path = get_database_path()

    if not db_path.exists():
        print(f"Datenbank nicht gefunden: {db_path}")
        print("Die Datenbank wird beim ersten Start der Anwendung angelegt.")
        sys.exit(1)

    # Tabellen auswählen
    tables = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_TABLES

    print(f"Datenbank: {db_path}\n")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        for table in tables:
            _print_table(conn, table)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
