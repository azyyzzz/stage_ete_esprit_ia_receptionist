"""
Orchestration : filtre de pertinence -> verification semantique -> dedup
par id -> fusion dans data/processed/site_esprit_clean.json (+ site_esprit.
json en miroir) -> journalisation dans data/historique.json.

merge_candidates() n'est appele qu'APRES approbation explicite d'un admin
sur /a-valider (voir approve_fiche/approve_batch) -- les deux garde-fous
etant deja passes a ce moment-la, la fiche est ecrite directement dans le
fichier que le RAG ingere reellement (CLEAN_KB_PATH), pas seulement dans un
fichier de staging intermediaire. Ne modifie jamais le schema des fiches
(id, categorie, titre, contenu, source -- rien de plus).

Note : ceci met a jour les fichiers JSON, pas l'index vectoriel ChromaDB --
`python -m modules.rag.ingest` reste necessaire pour que le contenu
approuve devienne cherchable par l'assistant.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from extraction_app.config import A_VALIDER_PATH, A_VERIFIER_PATH, CLEAN_KB_PATH, HISTORIQUE_PATH, KB_PATH
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
    """Source de verite pour la dedup (existing_ids + pool semantique) :
    CLEAN_KB_PATH, le fichier reellement ingere par le RAG -- pas
    KB_PATH (site_esprit.json), qui n'est qu'un miroir tenu synchronise en
    ecriture (voir merge_candidates) et pourrait sinon diverger."""
    return _load_json_list(CLEAN_KB_PATH)


def merge_candidates(candidates: list[dict]) -> dict:
    """Applique les deux garde-fous puis fusionne les fiches acceptees dans
    CLEAN_KB_PATH (site_esprit_clean.json, celui que le RAG ingere) ET
    KB_PATH (site_esprit.json, miroir de staging) pour rester coherent avec
    le reste du projet. Retourne un resume detaille (utilise pour la
    reponse UI et pour l'entree d'historique)."""
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
        _write_json_list(CLEAN_KB_PATH, kb)
        # Miroir de staging tenu synchronise -- lit son propre contenu
        # separement (pas juste `kb`) au cas ou il aurait deja legerement
        # diverge (ex. fiches ajoutees par un autre script hors extraction_app).
        mirror = _load_json_list(KB_PATH)
        mirror_ids = {r["id"] for r in mirror}
        mirror.extend(r for r in added if r["id"] not in mirror_ids)
        _write_json_list(KB_PATH, mirror)

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


def queue_for_validation(*, source: str, categorie: str, origin: str, candidates: list[dict]) -> str:
    """Depose un lot de fiches candidates en attente de validation admin --
    AUCUNE ecriture dans site_esprit.json a cet appel. Utilise pour les
    sources non supervisees (ex. scraping planifie, voir scheduler.py) ou
    la politique du projet exige un clic humain explicite avant toute
    modification de la base, contrairement aux sources declenchees
    directement par un admin (upload manuel = l'action humaine EST le
    declenchement). Voir approve_batch/reject_batch et routers/validation.py.
    Renvoie l'id du lot cree."""
    batches = _load_json_list(A_VALIDER_PATH)
    batch_id = uuid.uuid4().hex
    batches.append({
        "id": batch_id,
        "date": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "categorie": categorie,
        "origine": origin,
        "candidates": candidates,
    })
    _write_json_list(A_VALIDER_PATH, batches)
    return batch_id


def get_pending_batches() -> list[dict]:
    return list(reversed(_load_json_list(A_VALIDER_PATH)))


def approve_batch(batch_id: str) -> dict:
    """Approuve un lot en attente : applique EXACTEMENT le meme pipeline que
    les autres sources (merge_candidates -- filtre de pertinence + dedup
    semantique + ecriture directe dans site_esprit_clean.json), journalise
    dans l'historique, puis retire le lot de la file d'attente. Leve
    ValueError si le lot n'existe plus (deja traite, ou id invalide)."""
    batches = _load_json_list(A_VALIDER_PATH)
    batch = next((b for b in batches if b["id"] == batch_id), None)
    if batch is None:
        raise ValueError(f"Lot introuvable ou deja traite : {batch_id}")

    summary = merge_candidates(batch["candidates"])
    log_history(
        source=batch["source"],
        source_type="scraping_planifie",
        origin=batch["origine"],
        summary=summary,
    )

    remaining = [b for b in batches if b["id"] != batch_id]
    _write_json_list(A_VALIDER_PATH, remaining)
    return summary


def reject_batch(batch_id: str) -> None:
    """Rejette un lot en attente : le retire simplement de la file, sans
    aucune ecriture dans la base de connaissances."""
    batches = _load_json_list(A_VALIDER_PATH)
    remaining = [b for b in batches if b["id"] != batch_id]
    _write_json_list(A_VALIDER_PATH, remaining)


def _find_batch_and_fiche(batches: list[dict], batch_id: str, fiche_id: str) -> tuple[dict, dict]:
    batch = next((b for b in batches if b["id"] == batch_id), None)
    if batch is None:
        raise ValueError(f"Lot introuvable ou deja traite : {batch_id}")
    fiche = next((c for c in batch["candidates"] if c["id"] == fiche_id), None)
    if fiche is None:
        raise ValueError(f"Fiche introuvable dans ce lot : {fiche_id}")
    return batch, fiche


def _remove_fiche_from_batch(batches: list[dict], batch_id: str, fiche_id: str) -> None:
    """Retire une fiche de son lot ; si c'etait la derniere, retire le lot
    entier. Ecrit le resultat dans A_VALIDER_PATH."""
    updated = []
    for b in batches:
        if b["id"] != batch_id:
            updated.append(b)
            continue
        remaining_candidates = [c for c in b["candidates"] if c["id"] != fiche_id]
        if remaining_candidates:
            b = dict(b, candidates=remaining_candidates)
            updated.append(b)
        # sinon : lot vide, on ne le reajoute pas (equivalent a le retirer)
    _write_json_list(A_VALIDER_PATH, updated)


def approve_fiche(batch_id: str, fiche_id: str) -> dict:
    """Approuve UNE SEULE fiche d'un lot en attente (pas le lot entier) --
    meme pipeline que merge_candidates (pertinence + dedup semantique).
    Les autres fiches du lot restent en attente."""
    batches = _load_json_list(A_VALIDER_PATH)
    batch, fiche = _find_batch_and_fiche(batches, batch_id, fiche_id)

    summary = merge_candidates([fiche])
    log_history(source=batch["source"], source_type="scraping_planifie", origin=batch["origine"], summary=summary)

    _remove_fiche_from_batch(batches, batch_id, fiche_id)
    return summary


def reject_fiche(batch_id: str, fiche_id: str) -> None:
    """Rejette UNE SEULE fiche d'un lot en attente : la retire simplement,
    sans aucune ecriture dans la base. Les autres fiches du lot restent en
    attente."""
    batches = _load_json_list(A_VALIDER_PATH)
    _find_batch_and_fiche(batches, batch_id, fiche_id)  # leve si introuvable
    _remove_fiche_from_batch(batches, batch_id, fiche_id)


def preview_fiche_status(candidate: dict, deduper: SemanticDeduplicator) -> dict:
    """Calcule, SANS RIEN ECRIRE, si cette fiche candidate passerait les 2
    garde-fous de merge_candidates si elle etait approuvee maintenant --
    affiche sur /a-valider pour que l'admin sache si une fiche ressemble
    deja a du contenu existant AVANT de decider. `deduper` doit etre
    construit une seule fois par la base actuelle et reutilise pour toutes
    les fiches d'un meme lot (cout du fit TF-IDF)."""
    titre = candidate.get("titre", "")
    contenu = candidate.get("contenu", "")

    if not is_relevant(titre, contenu):
        return {"statut": "hors_sujet", "titre_existant": None, "score": None}

    is_dup, matched_title, score = deduper.check(contenu)
    if is_dup:
        return {"statut": "doublon", "titre_existant": matched_title, "score": round(score, 3)}

    return {"statut": "nouveau", "titre_existant": None, "score": round(score, 3)}


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
