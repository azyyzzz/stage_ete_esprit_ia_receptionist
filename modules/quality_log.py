"""
Journal partage des questions/reponses du pipeline RAG.

Utilise a la fois par :
- `backend` (routers/rag.py, routers/stt.py) : enregistre automatiquement
  chaque question REELLEMENT posee via l'app (texte ou vocal), avec sa
  reponse, sa langue detectee, ses mesures ;
- `extraction_app` (services/quality_test.py, /qualite) : lit ce meme
  fichier pour l'affichage, les KPI et l'annotation manuelle
  correct/incorrect, en le melangeant avec les resultats du test des 75
  questions fournies par l'encadrant (scripts/run_quality_test.py).

Vit dans `modules/` (et non `extraction_app/`) precisement pour que
`backend` -- qui doit rester independant de `extraction_app`, l'appli
d'administration -- puisse journaliser sans en dependre. Seules les
primitives de lecture/ecriture du fichier sont ici ; la logique
d'affichage (KPI, graphiques) reste dans extraction_app/services/
quality_test.py, qui importe ce module plutot que de dupliquer ces
fonctions.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUALITY_LOG_PATH = PROJECT_ROOT / "extraction_app" / "data" / "quality_test_results.jsonl"

# Protege TOUTE ecriture dans le fichier -- a la fois la reecriture
# complete (annotation, voir write_results) et l'ajout au fil de l'eau du
# trafic reel (append_live_result). Plusieurs vraies questions peuvent
# arriver en meme temps (contrairement a scripts/run_quality_test.py, qui
# ecrit sequentiellement une question apres l'autre) : sans verrou commun,
# une annotation qui reecrit tout le fichier pendant qu'une requete reelle
# l'agrandit perdrait silencieusement cette derniere (ecrasee par
# l'ancienne version chargee juste avant). Un simple threading.Lock
# suffit ICI (protege backend et extraction_app chacun dans leur propre
# processus uvicorn, tous deux lances sans --workers) -- il ne protege
# PAS contre un run complet de scripts/run_quality_test.py (processus
# separe) qui coinciderait avec du trafic reel : ce script tronque et
# reecrit tout le fichier des son lancement par conception (voir son
# docstring), un cas deja assume comme une action admin ponctuelle et
# consciente, pas du trafic concurrent ordinaire.
_file_lock = threading.Lock()


def load_results(path: Path = QUALITY_LOG_PATH) -> list[dict]:
    """Lit le fichier JSONL. Tolere une DERNIERE ligne malformee/tronquee :
    une ecriture (test en cours, ou requete reelle en cours de traitement)
    peut coincider avec une lecture au milieu de l'ecriture d'une ligne --
    ce n'est jamais qu'un resultat pas encore complet, pas une corruption,
    donc on l'ignore plutot que de faire planter tout le dashboard pour
    ca."""
    if not path.exists():
        return []
    results = []
    with open(path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    for i, line in enumerate(lines):
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError:
            if i != len(lines) - 1:
                raise  # une ligne malformee AILLEURS qu'en fin de fichier est une vraie anomalie
    return results


def write_results(results: list[dict], path: Path = QUALITY_LOG_PATH) -> None:
    with _file_lock:
        with open(path, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


def set_annotation(result_id: str, annotation: str | None) -> None:
    """`annotation` : "correct" | "incorrect" | None (reinitialise). Leve
    ValueError si l'id n'existe pas."""
    results = load_results()
    for r in results:
        if r["id"] == result_id:
            r["annotation"] = annotation
            write_results(results)
            return
    raise ValueError(f"Resultat introuvable : {result_id}")


def append_live_result(
    question: str,
    reponse: str,
    langue: str,
    canal: str,
    temps_reponse_s: float,
    score_principal: float | None,
    used_fallback: bool,
    sources: list[dict],
) -> dict:
    """Journalise une question REELLEMENT posee via l'app (pas le test des
    75 questions) -- appelee depuis backend/routers/rag.py (canal="texte")
    et backend/routers/stt.py (canal="vocal"). `numero` est absent (None) :
    contrairement au test, une question reelle n'a pas d'equivalent connu
    dans les 2 autres langues, donc pas de regroupement possible par
    numero (voir extraction_app/services/quality_test.py::
    compute_multilingual_consistency, qui exclut ces entrees de son calcul
    pour cette meme raison)."""
    entry = {
        "id": f"live_{uuid.uuid4().hex[:12]}",
        "numero": None,
        "source": "live",
        "canal": canal,
        "langue": langue,
        "question": question,
        "reponse": reponse,
        "temps_reponse_s": round(temps_reponse_s, 1),
        "used_fallback": used_fallback,
        "needs_clarification": False,
        "sources": [
            {"titre": s.get("titre", ""), "score": s.get("score")}
            for s in (sources or [])[:3]
        ],
        "score_principal": score_principal,
        "erreur": None,
        "date": datetime.now(timezone.utc).isoformat(),
        "annotation": None,
    }
    with _file_lock:
        with open(QUALITY_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry
