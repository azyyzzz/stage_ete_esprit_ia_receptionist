"""
Rejoue les 76 questions de test (fournies par l'encadrant) dans les 3
langues -- francais (data/questions_test/base_de_questions.txt), arabe
standard (questions_arabe_fusha.txt) et tunisien (questions_tounsi.txt) --
a travers le pipeline RAG reel (modules.rag.pipeline.answer_question), et
enregistre chaque resultat au fur et a mesure dans
extraction_app/data/quality_test_results.jsonl pour que le dashboard
qualite (/qualite dans extraction_app) puisse les afficher, y compris en
cours d'execution (fichier ecrit ligne par ligne, jamais d'etat "a moitie
ecrit" invalide).

Duree attendue : plusieurs dizaines de minutes a quelques heures (228
questions, chacune une inference LLM complete sur ce materiel). Pensé pour
tourner en arriere-plan -- relancable sans risque (ecrase le fichier de
resultats precedent au demarrage, ecriture strictement incrementale
ensuite).

Lancement (depuis la racine du projet) :
    python -m scripts.run_quality_test
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from modules.rag.pipeline import answer_question

PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUESTIONS_DIR = PROJECT_ROOT / "data" / "questions_test"
RESULTS_PATH = PROJECT_ROOT / "extraction_app" / "data" / "quality_test_results.jsonl"
LOCK_PATH = RESULTS_PATH.with_suffix(".lock")

FILES_BY_LANGUE = {
    "fr": QUESTIONS_DIR / "base_de_questions.txt",
    "ar_fusha": QUESTIONS_DIR / "questions_arabe_fusha.txt",
    "ar_tounsi": QUESTIONS_DIR / "questions_tounsi.txt",
}

# Numero suivi de "." ou "/" (les 3 fichiers melangent les deux), puis le
# texte de la question -- un seul numero par ligne dans les 3 fichiers
# (verifie manuellement), pas besoin de gerer un retour a la ligne au
# milieu d'une question.
_LINE_RE = re.compile(r"^\s*(\d{1,3})\s*[./]\s*(.+?)\s*$")


def parse_questions(path: Path) -> dict[int, str]:
    """Renvoie {numero: texte_question}. Leve une erreur si un numero est
    duplique ou si le texte est vide -- mieux vaut echouer tout de suite
    qu'a moitie a travers un test de plusieurs heures."""
    questions: dict[int, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        match = _LINE_RE.match(raw_line)
        if not match:
            continue
        numero = int(match.group(1))
        texte = match.group(2).strip().strip('"').strip()
        if not texte:
            continue
        if numero in questions:
            raise ValueError(f"{path.name} : numero {numero} en double (deja : {questions[numero]!r}, nouveau : {texte!r})")
        questions[numero] = texte
    return questions


def load_all_questions() -> dict[str, dict[int, str]]:
    by_langue = {langue: parse_questions(path) for langue, path in FILES_BY_LANGUE.items()}

    ref_numeros = set(by_langue["fr"])
    for langue, questions in by_langue.items():
        numeros = set(questions)
        if numeros != ref_numeros:
            missing = ref_numeros - numeros
            extra = numeros - ref_numeros
            raise ValueError(
                f"Incoherence de numerotation pour {langue} -- "
                f"manquants : {sorted(missing)}, en trop : {sorted(extra)}"
            )
    return by_langue


def run_one(numero: int, langue: str, question: str) -> dict:
    t0 = time.time()
    try:
        result = answer_question(question, allow_clarification=False)
        error = None
    except Exception as exc:
        result = {"answer": "", "sources": [], "used_fallback": True, "needs_clarification": False}
        error = str(exc)
    elapsed = round(time.time() - t0, 1)

    return {
        "id": f"{numero}_{langue}",
        "numero": numero,
        "langue": langue,
        "question": question,
        "reponse": result["answer"],
        "temps_reponse_s": elapsed,
        "used_fallback": result["used_fallback"],
        "needs_clarification": result["needs_clarification"],
        "sources": [
            {"titre": s.get("titre", ""), "score": s.get("score")}
            for s in result.get("sources", [])[:3]
        ],
        "score_principal": result["sources"][0]["score"] if result.get("sources") else None,
        "erreur": error,
        "date": datetime.now(timezone.utc).isoformat(),
        "annotation": None,  # rempli plus tard depuis /qualite : "correct" | "incorrect" | None
    }


def _acquire_lock() -> None:
    """Empeche deux executions simultanees d'ecrire dans le meme fichier
    en meme temps -- constate en usage reel : deux lancements accidentels
    du script ont entrelace leurs ecritures ligne par ligne, produisant des
    lignes JSON fusionnees illisibles (2 objets JSON colles sur une seule
    ligne) dans quality_test_results.jsonl."""
    if LOCK_PATH.exists():
        pid = LOCK_PATH.read_text(encoding="utf-8").strip()
        sys.exit(
            f"Un autre run_quality_test.py semble deja en cours (verrou {LOCK_PATH}, "
            f"pid indique : {pid}). Si ce n'est pas le cas (verrou laisse par un plantage), "
            f"supprime {LOCK_PATH} et relance."
        )
    LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")


def main() -> None:
    _acquire_lock()
    try:
        _run()
    finally:
        LOCK_PATH.unlink(missing_ok=True)


def _run() -> None:
    by_langue = load_all_questions()
    total = sum(len(q) for q in by_langue.values())
    print(f"{len(by_langue['fr'])} questions x {len(by_langue)} langues = {total} tests a executer.")
    print(f"Resultats ecrits au fur et a mesure dans : {RESULTS_PATH}")

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    done = 0
    t_start = time.time()

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        for numero in sorted(by_langue["fr"]):
            for langue in ("fr", "ar_fusha", "ar_tounsi"):
                question = by_langue[langue][numero]
                entry = run_one(numero, langue, question)
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                f.flush()
                done += 1
                elapsed_total = time.time() - t_start
                eta_min = (elapsed_total / done) * (total - done) / 60
                print(
                    f"[{done}/{total}] #{numero} ({langue}) -- {entry['temps_reponse_s']}s "
                    f"-- fallback={entry['used_fallback']} -- ETA ~{eta_min:.0f} min",
                    flush=True,
                )

    print(f"Termine : {done} resultats dans {RESULTS_PATH}")


if __name__ == "__main__":
    main()
