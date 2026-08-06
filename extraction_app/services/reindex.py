"""
Reconstruction de l'index vectoriel ChromaDB (modules/rag/ingest.py) --
declenchee a la demande depuis /a-valider (bouton "Reindexer maintenant"),
JAMAIS automatiquement apres chaque approbation : ingest.py reconstruit
l'index EN ENTIER (tout re-embedde), de l'ordre de la minute pour la base
actuelle -- inacceptable comme effet de bord d'un simple clic "Approuver".

Lance le script en SOUS-PROCESSUS plutot que d'importer modules.rag.ingest
directement : evite de charger sentence-transformers/torch dans le process
extraction_app (couteux en memoire/demarrage) pour une action ponctuelle et
peu frequente.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLEAN_KB_PATH = PROJECT_ROOT / "data" / "processed" / "site_esprit_clean.json"
VECTOR_STORE_DB = PROJECT_ROOT / "vector_store" / "chroma.sqlite3"

_last_result: dict | None = None


def is_index_stale() -> bool:
    """True si site_esprit_clean.json a ete modifie APRES le dernier
    `python -m modules.rag.ingest` reussi -- typiquement une ou plusieurs
    fiches approuvees sur /a-valider qui ne sont pas encore cherchables par
    l'assistant tant que l'index n'est pas reconstruit."""
    if not CLEAN_KB_PATH.exists():
        return False
    if not VECTOR_STORE_DB.exists():
        return True
    return CLEAN_KB_PATH.stat().st_mtime > VECTOR_STORE_DB.stat().st_mtime


def get_last_result() -> dict | None:
    """Resultat de la derniere reindexation declenchee depuis cette appli
    (memoire du process -- reinitialise a chaque redemarrage d'extraction_app,
    ce qui est sans consequence : is_index_stale() reste la source de
    verite pour savoir si une reindexation est necessaire)."""
    return _last_result


def run_ingest(timeout: int = 600) -> dict:
    """Lance `python -m modules.rag.ingest` avec le meme interpreteur que
    celui qui execute extraction_app (meme venv, memes dependances) et
    attend sa fin. Renvoie {success, output, date}."""
    global _last_result
    try:
        result = subprocess.run(
            [sys.executable, "-m", "modules.rag.ingest"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        success = result.returncode == 0
        output = ((result.stdout or "") + (result.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        success = False
        output = f"Timeout apres {timeout}s -- la reindexation est peut-etre toujours en cours en arriere-plan."
    except Exception as exc:
        success = False
        output = str(exc)

    _last_result = {
        "success": success,
        "output": output[-3000:],  # tronque une sortie trop longue pour l'affichage
        "date": datetime.now(timezone.utc).isoformat(),
    }
    return _last_result
