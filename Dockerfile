# === RideFuel / TrainingsPlanner — Produktions-Image ===
# Basis: schlankes Python 3.12
FROM python:3.12-slim

# Python-Verhalten im Container optimieren:
# - keine .pyc-Dateien schreiben
# - stdout/stderr sofort ausgeben (wichtig für Container-Logs)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Arbeitsverzeichnis im Container
WORKDIR /app

# Zuerst nur requirements.txt kopieren und installieren.
# Das nutzt den Docker-Layer-Cache: requirements ändern sich selten,
# der teure pip-Install-Schritt wird nur bei Bedarf wiederholt.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Anwendungscode und statische Dateien kopieren.
# run.py wird NICHT kopiert: Der Container startet direkt über uvicorn
# (kein reload, PORT aus der Umgebung). run.py ist nur für die lokale
# Entwicklung ohne Docker gedacht.
COPY app ./app
COPY static ./static

# Nicht als root laufen (Sicherheit).
# Die App legt ihre SQLite-Datenbank zur Laufzeit unter /app/data an
# (app/database.py -> DATA_DIR.mkdir). Daher muss das Verzeichnis existieren
# und dem appuser gehören, sonst schlägt init_db() mit PermissionError fehl.
RUN useradd --create-home appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser


# Cloud Run setzt PORT (Default 8080). Der Container lauscht auf 0.0.0.0.
# reload=True wird bewusst NICHT verwendet (Produktion).
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
