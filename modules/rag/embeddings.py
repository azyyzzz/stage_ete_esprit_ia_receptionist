"""
Encapsule le modèle d'embeddings multilingue.

Le modèle est chargé une seule fois (au premier appel) et réutilisé, car son
chargement prend plusieurs secondes.
"""

from __future__ import annotations

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from modules.rag.config import EMBEDDING_MODEL_NAME


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def embed(texts: list[str]) -> list[list[float]]:
    """Encode une liste de textes en vecteurs d'embedding normalises (norme 1),
    necessaire pour que la distance cosinus de ChromaDB soit correcte."""
    model = get_model()
    vectors = model.encode(
        texts, show_progress_bar=False, convert_to_numpy=True, normalize_embeddings=True
    )
    return vectors.tolist()
