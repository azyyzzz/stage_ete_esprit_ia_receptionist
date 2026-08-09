"""
Point d'entrée de l'API REST ESPRIT AI Receptionist.

Lancement (depuis la racine du projet) :
    uvicorn backend.main:app --reload

Documentation interactive (testable dans le navigateur, aucune commande à
taper) une fois lancé :
    http://127.0.0.1:8000/docs
"""

import sys

# Windows demarre Python avec un encodage de console par defaut (cp1252),
# incapable d'encoder l'arabe -- tout print()/log qui y touche (y compris
# a l'interieur d'une dependance comme le client ollama) plante avec une
# UnicodeEncodeError. Sans ce correctif, ce plantage silencieux peut etre
# rattrape par un `except Exception` en aval (ex. modules/rag/translate.py)
# et se traduire par un comportement errone plutot qu'une erreur visible --
# constate en usage reel : la traduction arabe -> francais avant recherche
# echouait silencieusement uniquement quand servie via ce process serveur.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import rag, stt, tts

app = FastAPI(
    title="ESPRIT AI Receptionist API",
    description="API reliant les modules de l'assistant vocal ESPRIT (RAG, et futurs modules voix).",
    version="0.1.0",
)

# Autorise le frontend de demo (dashboard/, voir dashboard/README.md) a
# appeler cette API directement depuis le navigateur (fetch/XHR cross-
# origin) -- ports par defaut de Vite en dev (5173) et de son apercu de
# build (4173). N'affecte pas extraction_app (app separee, port 8001, pas
# de CORS necessaire : le frontend s'y contente d'un lien/navigation
# classique, jamais d'appel fetch cross-origin -- voir dashboard/src/pages
# /Admin.tsx).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "http://127.0.0.1:4173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rag.router)
app.include_router(stt.router)
app.include_router(tts.router)


@app.get("/api/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}
