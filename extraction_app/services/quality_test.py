"""
Chargement, KPI et annotation manuelle des resultats du test qualite
(scripts/run_quality_test.py -- 75 questions x 3 langues, voir /qualite).

Aucune reponse de reference n'est fournie par l'encadrant : "correct" ne
peut donc pas etre calcule automatiquement. Ce module calcule des
indicateurs OBJECTIFS a la place (taux d'echec, score de confiance,
coherence multilingue par rapport a la reponse francaise pour la meme
question) et expose une annotation manuelle (correct/incorrect) que
l'admin remplit depuis /qualite -- le "% de bonnes reponses" n'est alors
calcule QUE sur les questions annotees, jamais extrapole sur le reste.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import numpy as np

from extraction_app.config import QUALITY_TEST_RESULTS_PATH
from modules.rag.embeddings import embed

LANGUES = ("fr", "ar_fusha", "ar_tounsi")
LANGUE_LABELS = {"fr": "Français", "ar_fusha": "Arabe standard", "ar_tounsi": "Tunisien"}

# Palette categorique (identite = langue, fixe et jamais recyclee entre les
# graphiques) -- 3 premiers pas de la palette de reference validee CVD-safe
# (voir competence dataviz), verifiee au validateur contre la vraie couleur
# de fond de l'appli (--ink-950 #08090c) : tous les checks passent (bande de
# clarte, floor de chroma, separation CVD adjacente ΔE 9.4, floor vision
# normale ΔE 26.5, contraste >= 3:1).
LANGUE_COLORS = {"fr": "#3987e5", "ar_fusha": "#d95926", "ar_tounsi": "#199e70"}


def build_chart_series(kpis: dict, consistency_avg: dict) -> dict[str, list[dict]]:
    """Donnees pretes a tracer (une serie de barres par metrique), pour le
    tableau de bord graphique de /qualite -- calculees ici plutot que dans
    le template pour garder le Jinja simple (juste des rectangles SVG a
    partir de valeurs deja pretes)."""
    return {
        "pct_correct": [
            {"langue": l, "label": LANGUE_LABELS[l], "valeur": kpis[l]["pct_correct"], "color": LANGUE_COLORS[l]}
            for l in LANGUES if kpis[l]["pct_correct"] is not None
        ],
        "temps_moyen": [
            {"langue": l, "label": LANGUE_LABELS[l], "valeur": kpis[l]["temps_reponse"]["moyenne"], "color": LANGUE_COLORS[l]}
            for l in LANGUES if kpis[l]["temps_reponse"]["moyenne"] is not None
        ],
        "taux_fallback": [
            {"langue": l, "label": LANGUE_LABELS[l], "valeur": kpis[l]["taux_fallback"], "color": LANGUE_COLORS[l]}
            for l in LANGUES if kpis[l]["taux_fallback"] is not None
        ],
        "score_confiance": [
            {"langue": l, "label": LANGUE_LABELS[l], "valeur": kpis[l]["score_confiance_moyen"], "color": LANGUE_COLORS[l]}
            for l in LANGUES if kpis[l]["score_confiance_moyen"] is not None
        ],
        "coherence": [
            {"langue": l, "label": LANGUE_LABELS[l], "valeur": consistency_avg[l], "color": LANGUE_COLORS[l]}
            for l in ("ar_fusha", "ar_tounsi") if consistency_avg.get(l) is not None
        ],
    }


def load_results(path: Path = QUALITY_TEST_RESULTS_PATH) -> list[dict]:
    """Lit le fichier JSONL. Tolere une DERNIERE ligne malformee/tronquee :
    le test (scripts/run_quality_test.py) peut tourner en meme temps que
    cette page est consultee, et un flush() cote ecriture peut coincider
    avec une lecture au milieu de l'ecriture d'une ligne -- ce n'est jamais
    qu'un resultat pas encore complet, pas une corruption, donc on l'ignore
    plutot que de faire planter tout le dashboard pour ca."""
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


def _write_results(results: list[dict], path: Path = QUALITY_TEST_RESULTS_PATH) -> None:
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
            _write_results(results)
            return
    raise ValueError(f"Resultat introuvable : {result_id}")


def _percentile_stats(values: list[float]) -> dict:
    if not values:
        return {"moyenne": None, "mediane": None, "min": None, "max": None}
    return {
        "moyenne": round(statistics.mean(values), 1),
        "mediane": round(statistics.median(values), 1),
        "min": round(min(values), 1),
        "max": round(max(values), 1),
    }


def compute_kpis(results: list[dict]) -> dict:
    """KPI globaux + par langue. Le "% correct" n'est calcule que sur les
    questions annotees manuellement (jamais extrapole)."""

    def _for_subset(subset: list[dict]) -> dict:
        temps = [r["temps_reponse_s"] for r in subset if r.get("temps_reponse_s") is not None]
        scores = [r["score_principal"] for r in subset if r.get("score_principal") is not None]
        fallback_count = sum(1 for r in subset if r.get("used_fallback"))
        annotated = [r for r in subset if r.get("annotation") in ("correct", "incorrect")]
        correct = sum(1 for r in annotated if r["annotation"] == "correct")

        return {
            "total": len(subset),
            "temps_reponse": _percentile_stats(temps),
            "taux_fallback": round(100 * fallback_count / len(subset), 1) if subset else None,
            "score_confiance_moyen": round(statistics.mean(scores), 3) if scores else None,
            "nb_annote": len(annotated),
            "pct_correct": round(100 * correct / len(annotated), 1) if annotated else None,
        }

    kpis = {"global": _for_subset(results)}
    for langue in LANGUES:
        kpis[langue] = _for_subset([r for r in results if r["langue"] == langue])
    return kpis


_consistency_cache_key: int | None = None
_consistency_cache: dict[int, dict[str, float | None]] | None = None


def compute_multilingual_consistency(results: list[dict], path: Path = QUALITY_TEST_RESULTS_PATH) -> dict[int, dict[str, float | None]]:
    """Pour chaque numero de question, similarite semantique (embeddings,
    cosinus) entre la reponse arabe standard / tunisienne et la reponse
    francaise de la MEME question -- le proxy le plus proche d'une mesure
    d'exactitude sans reference humaine : si le francais est fiable
    (base de connaissances majoritairement francaise), une reponse arabe
    tres differente du francais est suspecte.

    Mis en cache par un hash du CONTENU des reponses (id + texte), pas par
    mtime du fichier : annoter une reponse (bouton Correct/Incorrect sur
    /qualite) reecrit le fichier de resultats sans jamais changer les
    reponses elles-memes -- un cache par mtime serait invalide a chaque
    annotation et relancerait inutilement les embeddings sur les 225
    reponses a chaque clic (constate en usage reel : chaque annotation
    devenait aussi lente que le tout premier chargement de la page)."""
    global _consistency_cache_key, _consistency_cache

    cache_key = hash(tuple((r["id"], r.get("reponse")) for r in results))
    if cache_key == _consistency_cache_key and _consistency_cache is not None:
        return _consistency_cache

    by_numero: dict[int, dict[str, dict]] = {}
    for r in results:
        by_numero.setdefault(r["numero"], {})[r["langue"]] = r

    texts: list[str] = []
    index: list[tuple[int, str]] = []
    for numero, par_langue in by_numero.items():
        fr = par_langue.get("fr")
        if not fr or not fr.get("reponse"):
            continue
        texts.append(fr["reponse"])
        index.append((numero, "fr"))
        for langue in ("ar_fusha", "ar_tounsi"):
            entry = par_langue.get(langue)
            if entry and entry.get("reponse"):
                texts.append(entry["reponse"])
                index.append((numero, langue))

    consistency: dict[int, dict[str, float | None]] = {
        numero: {"ar_fusha": None, "ar_tounsi": None} for numero in by_numero
    }

    if texts:
        vectors = np.array(embed(texts))
        fr_vector_by_numero: dict[int, np.ndarray] = {}
        for (numero, langue), vector in zip(index, vectors):
            if langue == "fr":
                fr_vector_by_numero[numero] = vector

        for (numero, langue), vector in zip(index, vectors):
            if langue == "fr" or numero not in fr_vector_by_numero:
                continue
            score = float(fr_vector_by_numero[numero] @ vector)
            consistency[numero][langue] = round(score, 3)

    _consistency_cache_key = cache_key
    _consistency_cache = consistency
    return consistency


def average_consistency(consistency: dict[int, dict[str, float | None]]) -> dict[str, float | None]:
    averages: dict[str, float | None] = {}
    for langue in ("ar_fusha", "ar_tounsi"):
        values = [v[langue] for v in consistency.values() if v.get(langue) is not None]
        averages[langue] = round(statistics.mean(values), 3) if values else None
    return averages
