"""
Verification semantique -- second garde-fou avant sauvegarde.

Compare le CONTENU d'une fiche candidate contre TOUTES les fiches deja
presentes dans la base (pas seulement celles de meme categorie/source), via
les MEMES embeddings multilingues que le RAG (modules/rag/embeddings.py,
paraphrase-multilingual-mpnet-base-v2) + similarite cosinus -- comparaison
par le SENS, pas par simple chevauchement de mots. Si le score depasse
SIMILARITY_THRESHOLD (config.py), la fiche est consideree comme un doublon
et rejetee.

Remplace l'ancienne version TF-IDF (lexicale) : deux fiches qui disent la
meme chose avec des mots differents scoraient parfois trop bas pour etre
detectees. Le seuil a ete recalibre pour les embeddings (distribution tres
differente de TF-IDF -- des paires de fiches SANS rapport peuvent deja
depasser 0.8 en similarite d'embedding, contrairement au TF-IDF ou un score
eleve implique presque toujours un vrai chevauchement lexical)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from extraction_app.config import CLEAN_KB_PATH, SIMILARITY_THRESHOLD
from modules.rag.embeddings import embed


class SemanticDeduplicator:
    """Encapsule les embeddings des fiches existantes. A recreer apres
    chaque fusion, pour que les fiches tout juste ajoutees comptent aussi
    dans les verifications suivantes de la meme session d'extraction."""

    def __init__(self, existing_records: list[dict]):
        self._titles = [r.get("titre", "") for r in existing_records]
        self._contents = [r.get("contenu", "") for r in existing_records]
        self._matrix: np.ndarray | None = None
        if self._contents:
            self._matrix = np.array(embed(self._contents))

    def check(self, contenu: str) -> tuple[bool, str | None, str | None, float]:
        """Retourne (est_doublon, titre_de_la_fiche_recoupee,
        contenu_de_la_fiche_recoupee, score_max). Si la base existante est
        vide, il ne peut pas y avoir de doublon."""
        return self.check_many([contenu])[0]

    def check_many(self, contenus: list[str]) -> list[tuple[bool, str | None, str | None, float]]:
        """Version vectorisee de check() pour plusieurs contenus a la fois :
        UN SEUL appel au modele d'embeddings pour toute la liste, au lieu
        d'un appel par fiche -- evite au moins l'overhead repete d'un appel
        par fiche. Insuffisant a soi seul pour de bonnes performances sur
        /a-valider : le cout reel vient du volume de texte a embedder sur ce
        CPU (mesure : ~550 fiches ~= 30s), voir get_cached_kb_deduper() plus
        bas pour la vraie optimisation (cache des embeddings de la base)."""
        if not contenus:
            return []
        if self._matrix is None:
            return [(False, None, None, 0.0) for _ in contenus]

        vectors = np.array(embed(contenus))  # (N, D)
        # Embeddings deja normalises (norme 1, voir modules/rag/embeddings.py)
        # -> le produit matriciel EST directement la similarite cosinus.
        all_scores = vectors @ self._matrix.T  # (N, M)

        results = []
        for row in all_scores:
            best_index = int(row.argmax())
            best_score = float(row[best_index])
            is_dup = best_score > SIMILARITY_THRESHOLD
            results.append((is_dup, self._titles[best_index], self._contents[best_index], best_score))
        return results


# Cache du DERNIER deduper construit sur la base COMPLETE et INCHANGEE
# (CLEAN_KB_PATH), invalide des que le fichier est modifie (mtime). Reserve
# a la page de LECTURE /a-valider, qui reconstruit un deduper sur la meme
# base brute a chaque chargement -- reembedder ~800 fiches a chaque visite
# prenait ~65s, mesure. NE JAMAIS utiliser ce cache pour merge_candidates
# (kb_merge.py) : la, le pool de comparaison grandit dynamiquement PENDANT
# la boucle d'approbation (fiches tout juste ajoutees comprises), un cache
# base sur le mtime du fichier renverrait alors un etat perime.
_cache_mtime: float | None = None
_cache_deduper: SemanticDeduplicator | None = None


def get_cached_kb_deduper(kb_records: list[dict], kb_path: Path = CLEAN_KB_PATH) -> SemanticDeduplicator:
    global _cache_mtime, _cache_deduper
    mtime = kb_path.stat().st_mtime if kb_path.exists() else None

    if mtime is not None and mtime == _cache_mtime and _cache_deduper is not None:
        return _cache_deduper

    deduper = SemanticDeduplicator(kb_records)
    if mtime is not None:
        _cache_mtime = mtime
        _cache_deduper = deduper
    return deduper
