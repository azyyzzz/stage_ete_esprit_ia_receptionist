"""
Point d'entrée de l'API REST ESPRIT AI Receptionist.

Lancement (depuis la racine du projet) :
    uvicorn backend.main:app --reload

Documentation interactive (testable dans le navigateur, aucune commande à
taper) une fois lancé :
    http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI

from backend.routers import rag, stt, tts

app = FastAPI(
    title="ESPRIT AI Receptionist API",
    description="API reliant les modules de l'assistant vocal ESPRIT (RAG, et futurs modules voix).",
    version="0.1.0",
)

app.include_router(rag.router)
app.include_router(stt.router)
app.include_router(tts.router)


@app.get("/api/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}
