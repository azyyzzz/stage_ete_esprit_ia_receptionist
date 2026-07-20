"""
Verification semantique -- second garde-fou avant sauvegarde.

Compare le CONTENU d'une fiche candidate contre TOUTES les fiches deja
presentes dans la base (pas seulement celles de meme categorie/source), via
TF-IDF + similarite cosinus (scikit-learn). Si le score depasse
SIMILARITY_THRESHOLD (config.py), la fiche est consideree comme un doublon
et rejetee.

Limite assumee (voir README.md) : TF-IDF/cosinus est une mesure LEXICALE
(chevauchement de mots), pas une vraie comprehension semantique comme les
embeddings utilises par le RAG (modules/rag/embeddings.py) -- deux fiches
qui disent la meme chose avec des mots differents peuvent passer sous le
seuil et etre dupliquees quand meme.
"""

from __future__ import annotations

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from extraction_app.config import SIMILARITY_THRESHOLD


class SemanticDeduplicator:
    """Encapsule le vectoriseur TF-IDF fit sur le contenu d'une base de
    fiches existante. A recreer (fit a nouveau) apres chaque fusion, pour
    que les fiches tout juste ajoutees comptent aussi dans les verifications
    suivantes de la meme session d'extraction."""

    def __init__(self, existing_records: list[dict]):
        self._titles = [r.get("titre", "") for r in existing_records]
        contents = [r.get("contenu", "") for r in existing_records]
        self._vectorizer = None
        self._matrix = None
        if contents:
            self._vectorizer = TfidfVectorizer()
            self._matrix = self._vectorizer.fit_transform(contents)

    def check(self, contenu: str) -> tuple[bool, str | None, float]:
        """Retourne (est_doublon, titre_de_la_fiche_recoupee, score_max).
        Si la base existante est vide, il ne peut pas y avoir de doublon."""
        if self._vectorizer is None:
            return False, None, 0.0

        candidate_vector = self._vectorizer.transform([contenu])
        scores = cosine_similarity(candidate_vector, self._matrix)[0]
        best_index = scores.argmax()
        best_score = float(scores[best_index])

        if best_score > SIMILARITY_THRESHOLD:
            return True, self._titles[best_index], best_score
        return False, None, best_score
