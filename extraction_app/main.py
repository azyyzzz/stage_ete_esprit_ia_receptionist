"""
Point d'entree de extraction_app -- appli separee du reste du projet
(voir README.md), dediee a l'ajout controle de nouvelles fiches dans la
base de connaissances (PDF, Excel, image, URL).

Lancement (depuis la racine du projet) :
    uvicorn extraction_app.main:app --reload --port 8001

Interface : http://127.0.0.1:8001/
(le backend principal du projet reste sur le port 8000, inchange)
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# Windows demarre Python avec un encodage de console par defaut (cp1252),
# incapable d'encoder l'arabe -- tout print()/log qui y touche plante avec
# une UnicodeEncodeError, potentiellement rattrapee silencieusement par un
# `except Exception` en aval (voir backend/main.py pour le cas constate en
# usage reel sur le backend principal). Meme correctif preventif ici, vu le
# contenu scrappe (site esprit.tn) peut contenir de l'arabe.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from extraction_app.auth import register_auth_exception_handler
from extraction_app.auth import router as auth_router
from extraction_app.bootstrap_credentials import ensure_credentials
from extraction_app.config import APP_ROOT
from extraction_app.routers import extraction, history, quality, validation
from extraction_app.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_credentials()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Extraction KB ESPRIT",
    description="Ajout controle (filtrage + dedup semantique) de nouvelles fiches dans la base de connaissances ESPRIT AI Receptionist.",
    version="0.1.0",
    lifespan=lifespan,
)

register_auth_exception_handler(app)
app.mount("/static", StaticFiles(directory=str(APP_ROOT / "static")), name="static")

app.include_router(auth_router)
app.include_router(extraction.router)
app.include_router(history.router)
app.include_router(validation.router)
app.include_router(quality.router)
