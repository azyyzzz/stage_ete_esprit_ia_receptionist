"""
Route qui expose le pipeline RAG (modules/rag/) via HTTP.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.schemas import AskRequest, AskResponse
from modules.rag.pipeline import answer_question

router = APIRouter(prefix="/api", tags=["rag"])


@router.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    """
    Pose une question à la base de connaissances ESPRIT et renvoie une
    réponse générée, avec ses sources (ou un message de redirection si
    aucune information pertinente n'est trouvée).

    Note : fonction volontairement synchrone (pas de `async def`) car
    l'appel au LLM local est bloquant -- FastAPI l'exécute alors dans un
    thread séparé et n'empêche pas les autres requêtes d'être traitées.
    """
    result = answer_question(request.question)
    return AskResponse(**result)
