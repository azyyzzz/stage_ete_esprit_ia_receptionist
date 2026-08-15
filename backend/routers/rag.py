"""
Route qui expose le pipeline RAG (modules/rag/) via HTTP.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, BackgroundTasks

from backend.schemas import AskRequest, AskResponse, AskResponseStructured
from modules.quality_log import append_live_result
from modules.rag.pipeline import answer_question
from modules.rag.translate import detect_text_language

router = APIRouter(prefix="/api", tags=["rag"])


@router.post("/ask", response_model=AskResponse)
def ask(request: AskRequest, background_tasks: BackgroundTasks) -> AskResponseStructured:
    """
    Pose une question à la base de connaissances ESPRIT et renvoie une
    réponse générée, avec ses sources (ou un message de redirection si
    aucune information pertinente n'est trouvée).

    Note : fonction volontairement synchrone (pas de `async def`) car
    l'appel au LLM local est bloquant -- FastAPI l'exécute alors dans un
    thread séparé et n'empêche pas les autres requêtes d'être traitées.
    """
    t0 = time.time()
    # allow_clarification=True : le chat est un canal a plusieurs allers-
    # retours (contrairement au vocal telephonique d'un coup), donc le
    # modele peut demander une precision (ex. "Tunis, Monastir ou Prepa ?")
    # quand l'info differe selon le programme concerne, plutot que de
    # deviner ou de tout melanger -- voir dashboard/src/components/
    # ChatDemo.tsx, qui memorise la question d'origine et la recombine
    # avec la reponse de precision de l'utilisateur.
    result = answer_question(request.question, allow_clarification=True, structured=request.structured)
    elapsed = time.time() - t0

    # Journalise cette question reelle pour le dashboard qualite (voir
    # modules/quality_log.py) -- en tache de fond (BackgroundTasks) pour
    # que l'ecriture du journal n'ajoute aucune latence a la reponse
    # renvoyee a l'appelant. Ne journalise PAS un tour de demande de
    # precision (needs_clarification=True) : ce n'est pas une reponse a
    # evaluer, juste une question intermediaire -- seul le tour final
    # (question recombinee + vraie reponse) merite d'etre garde.
    if not result["needs_clarification"]:
        background_tasks.add_task(
            append_live_result,
            question=request.question,
            reponse=result["answer"],
            langue=detect_text_language(request.question),
            canal="texte",
            temps_reponse_s=elapsed,
            score_principal=result["sources"][0]["score"] if result.get("sources") else None,
            used_fallback=result["used_fallback"],
            sources=result.get("sources", []),
        )

    # If structured modules present, use the structured response model
    return AskResponseStructured(**result)
