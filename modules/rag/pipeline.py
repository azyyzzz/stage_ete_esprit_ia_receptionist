"""
Point d'entrée unique du module RAG : reçoit une question, renvoie une
réponse. C'est cette fonction que les futurs modules (API REST, module de
compréhension) appelleront.
"""

from __future__ import annotations

from modules.rag.config import PROGRAMME_AMBIGUITY_MARGIN, SCORE_THRESHOLD
from modules.rag.fallback import get_fallback_message
from modules.rag.generator import generate_answer
from modules.rag.programmes import mentioned_programme, programme_label
from modules.rag.retriever import retrieve


TOP_N_FOR_CONSENSUS = 3


def _ambiguous_programmes(chunks: list) -> set[str]:
    """Programmes distincts (cours du jour, EMBA...) representes parmi les
    fiches aussi pertinentes que la meilleure (a la marge pres) -- si plus
    d'un, la question est ambigue (ne precise pas de quel programme il
    s'agit).

    Ne se declenche que si une MAJORITE des meilleurs resultats (pas
    seulement le tout premier) sont deja specifiques a un programme : se fier
    au seul chunks[0] est fragile, un ecart de score de 0.001 entre deux
    fiches (bruit d'embedding) suffit a faire basculer un cas non-ambigu
    (ex. question generale sur un service -- stages, carriere...) en fausse
    alerte. Le consensus sur le top N est plus robuste a ce bruit."""
    top = chunks[:TOP_N_FOR_CONSENSUS]
    labels_per_chunk = [programme_label(c.metadata.get("source", "")) for c in top]
    if sum(1 for label in labels_per_chunk if label) < len(top) // 2 + 1:
        return set()

    best_score = chunks[0].score
    labels = set()
    for chunk in chunks:
        if chunk.score < best_score - PROGRAMME_AMBIGUITY_MARGIN:
            continue
        label = programme_label(chunk.metadata.get("source", ""))
        if label:
            labels.add(label)
    return labels


def answer_question(question: str) -> dict:
    chunks = retrieve(question)
    best_score = chunks[0].score if chunks else 0.0

    if not chunks or best_score < SCORE_THRESHOLD:
        return {
            "answer": get_fallback_message(question),
            "sources": [],
            "used_fallback": True,
            "needs_clarification": False,
        }

    programmes = _ambiguous_programmes(chunks)
    if len(programmes) >= 2 and not mentioned_programme(question, programmes):
        options = ", ".join(sorted(programmes))
        return {
            "answer": (
                "Cette information dépend du programme concerné. "
                f"Pouvez-vous préciser lequel vous intéresse : {options} ?"
            ),
            "sources": [],
            "used_fallback": False,
            "needs_clarification": True,
        }

    answer = generate_answer(question, chunks)
    return {
        "answer": answer,
        "sources": [
            {"titre": c.metadata.get("titre", ""), "source": c.metadata.get("source", ""), "score": round(c.score, 3)}
            for c in chunks
        ],
        "used_fallback": False,
        "needs_clarification": False,
    }
