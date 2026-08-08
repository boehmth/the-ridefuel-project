"""
Einstiegspunkt für den TrainingsPlanner.

Startet den FastAPI-Server mit uvicorn.
"""
from __future__ import annotations

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
