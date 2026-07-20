"""
Orchestration : filtre de pertinence -> verification semantique -> dedup
par id -> fusion dans data/processed/site_esprit.json -> journalisation
dans data/historique.json.

Ne modifie jamais site_esprit_clean.json (voir config.py et README.md) ni
le schema des fiches (id, categorie, titre, contenu, source -- rien de
plus).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from extraction_app.config import A_VERIFIER_PATH, HISTORIQUE_PATH, KB_PATH
from extraction_app.services.relevance_filter import is_relevant
from extraction_app.services.semantic_dedup import SemanticDeduplicator


def _load_json_list(path) -> list:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json_list(path, records: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def load_kb() -> list[dict]:
    return _load_json_list(KB_PATH)


def merge_candidates(candidates: list[dict]) -> dict:
    """Applique les deux garde-fous puis fusionne les fiches acceptees dans
    site_esprit.json. Retourne un resume detaille (utilise pour la reponse
    UI et pour l'entree d'historique)."""
    kb = load_kb()
    existing_ids = {r["id"] for r in kb}

    rejected_relevance: list[str] = []
    rejected_duplicate: list[dict] = []
    rejected_id: list[str] = []
    added: list[dict] = []

    dedup_pool = list(kb)
    deduper = SemanticDeduplicator(dedup_pool)

    for candidate in candidates:
        titre = candidate.get("titre", "")
        contenu = candidate.get("contenu", "")

        if not is_relevant(titre, contenu):
            rejected_relevance.append(titre)
            continue

        if candidate["id"] in existing_ids:
            rejected_id.append(candidate["id"])
            continue

        is_dup, matched_title, score = deduper.check(contenu)
        if is_dup:
            rejected_duplicate.append({"titre_candidat": titre, "titre_existant": matched_title, "score": round(score, 3)})
            continue

        added.append(candidate)
        existing_ids.add(candidate["id"])
        dedup_pool.append(candidate)
        deduper = SemanticDeduplicator(dedup_pool)

    if added:
        kb.extend(added)
        _write_json_list(KB_PATH, kb)

    return {
        "added": added,
        "rejected_relevance_count": len(rejected_relevance),
        "rejected_relevance_titles": rejected_relevance,
        "rejected_duplicate_count": len(rejected_duplicate),
        "rejected_duplicate_details": rejected_duplicate,
        "rejected_id_count": len(rejected_id),
        "rejected_id_values": rejected_id,
    }


def log_manual_review(item: dict) -> None:
    """Ajoute un item (ex. OCR de mauvaise qualite) au fichier de
    verification manuelle -- jamais fusionne automatiquement dans la KB."""
    items = _load_json_list(A_VERIFIER_PATH)
    item = dict(item)
    item["date"] = datetime.now(timezone.utc).isoformat()
    items.append(item)
    _write_json_list(A_VERIFIER_PATH, items)


def log_history(*, source: str, source_type: str, origin: str, summary: dict | None = None, error: str | None = None, manual_review: bool = False) -> None:
    """Ajoute une entree au journal d'extraction. `summary` est le retour de
    merge_candidates() (ou None si l'extraction a echoue avant la fusion)."""
    entries = _load_json_list(HISTORIQUE_PATH)
    entry = {
        "date": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "type": source_type,
        "origine": origin,  # "manuel" ou "planifie"
        "nb_ajoutees": len(summary["added"]) if summary else 0,
        "nb_rejetees_pertinence": summary["rejected_relevance_count"] if summary else 0,
        "nb_rejetees_doublon": summary["rejected_duplicate_count"] if summary else 0,
        "doublons_detail": summary["rejected_duplicate_details"] if summary else [],
        "a_verifier_manuellement": manual_review,
        "erreur": error,
    }
    entries.append(entry)
    _write_json_list(HISTORIQUE_PATH, entries)


def get_history() -> list[dict]:
    return list(reversed(_load_json_list(HISTORIQUE_PATH)))
