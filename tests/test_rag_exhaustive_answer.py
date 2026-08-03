"""Tests unitaires pour la réponse exhaustive du pipeline RAG."""

from modules.rag.pipeline import _build_exhaustive_answer
from modules.rag.retriever import RetrievedChunk


def test_build_exhaustive_answer_lists_every_panier():
    chunks = [
        RetrievedChunk(
            content=(
                "Dans le programme d'étude de la classe 3B, l'unité d'enseignement (panier) « Panier A » "
                "comprend les matières suivantes : Matière 1 (15h, 1 ECTS) ; Matière 2 (21h, 2 ECTS). "
                "Total ECTS de ce panier : 3."
            ),
            metadata={"titre": "Programme d'étude — 3B — Panier A", "source": "Plan d'étude 3B.pdf"},
            score=0.91,
        ),
        RetrievedChunk(
            content=(
                "Dans le programme d'étude de la classe 3B, l'unité d'enseignement (panier) « Panier B » "
                "comprend les matières suivantes : Matière 3 (42h, 3 ECTS). Total ECTS de ce panier : 3."
            ),
            metadata={"titre": "Programme d'étude — 3B — Panier B", "source": "Plan d'étude 3B.pdf"},
            score=0.89,
        ),
    ]

    answer = _build_exhaustive_answer("3B", chunks)

    assert "Panier A" in answer
    assert "Panier B" in answer
    assert "Matière 1" in answer
    assert "Matière 2" in answer
    assert "Matière 3" in answer