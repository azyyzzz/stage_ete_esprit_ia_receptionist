"""
Chargement, KPI et annotation manuelle des resultats du test qualite --
melange deux sources dans le meme fichier/les memes indicateurs :
- "test" : les 75 questions x 3 langues fournies par l'encadrant
  (scripts/run_quality_test.py) ;
- "live" : les questions reellement posees par des utilisateurs via
  l'app (backend/routers/rag.py, stt.py), journalisees automatiquement
  (voir append_live_result) au fil de l'eau.

Aucune reponse de reference n'est fournie par l'encadrant (et n'existe
evidemment pas pour du trafic reel) : "correct" ne peut donc pas etre
calcule automatiquement. Ce module calcule des indicateurs OBJECTIFS a la
place (taux d'echec, score de confiance, coherence multilingue par
rapport a la reponse francaise pour la meme question -- uniquement
calculable pour les entrees "test", qui seules garantissent une meme
question posee dans les 3 langues) et expose une annotation manuelle
(correct/incorrect) que l'admin remplit depuis /qualite -- le "% de
bonnes reponses" n'est alors calcule QUE sur les questions annotees,
jamais extrapole sur le reste.
"""

from __future__ import annotations

import statistics

import numpy as np

from modules.quality_log import QUALITY_LOG_PATH as QUALITY_TEST_RESULTS_PATH
from modules.quality_log import delete_result, load_results, set_annotation  # noqa: F401 -- reexportes pour /qualite
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

# Couleurs de statut (deja utilisees ailleurs dans l'appli -- extraction_app/
# static/style.css : --volt-500 pour "ok", #f0b429 pour "warning", --signal-500
# pour "erreur"/danger). Reprises ici pour les jauges : la couleur y encode
# une SEVERITE (bon/moyen/mauvais), pas une identite -- role different des
# LANGUE_COLORS categoriques ci-dessus, qui ne doivent jamais etre utilisees
# pour ca (voir competence dataviz : couleur categorique = identite, statut =
# etat, jamais les deux sur le meme canal).
STATUS_GOOD = "#22c1e0"
STATUS_WARNING = "#f0b429"
STATUS_DANGER = "#f0342a"


def _severity(value: float | None, good: float, warning: float, higher_is_better: bool) -> str:
    """Classe `value` en bon/moyen/mauvais pour la couleur de remplissage
    d'une jauge. `good`/`warning` sont les seuils ; le sens (plus haut =
    mieux, ex. score de confiance, ou plus bas = mieux, ex. taux d'echec)
    est explicite via `higher_is_better` plutot que devine depuis le nom de
    la metrique."""
    if value is None:
        return STATUS_WARNING
    if higher_is_better:
        if value >= good:
            return STATUS_GOOD
        if value >= warning:
            return STATUS_WARNING
        return STATUS_DANGER
    else:
        if value <= good:
            return STATUS_GOOD
        if value <= warning:
            return STATUS_WARNING
        return STATUS_DANGER


def _meter_series(values: list[tuple[str, float | None]], max_value: float, unit: str, good: float, warning: float, higher_is_better: bool) -> list[dict]:
    """Une jauge par langue pour une metrique qui est un RATIO contre une
    limite (%, ou score 0-1) -- job "single ratio against a limit" (voir
    competence dataviz, choosing-a-form.md). La couleur y encode une
    severite (bon/moyen/mauvais avec _severity), pas l'identite de la
    langue : le nom de la langue est porte par le label texte, pas la
    teinte -- une jauge se lit seule, pas par comparaison de teintes."""
    series = []
    for langue, valeur in values:
        if valeur is None:
            continue
        series.append({
            "langue": langue,
            "label": LANGUE_LABELS[langue],
            "valeur": valeur,
            "max": max_value,
            "unit": unit,
            "color": _severity(valeur, good, warning, higher_is_better),
        })
    return series


def build_chart_series(kpis: dict, consistency_avg: dict) -> dict[str, list[dict]]:
    """Donnees pretes a tracer pour le tableau de bord graphique de
    /qualite -- calculees ici plutot que dans le template pour garder le
    Jinja simple. Types varies selon le job de chaque metrique (voir
    competence dataviz) plutot qu'un seul type repete : jauges pour les 4
    metriques qui sont des ratios contre une limite (%, score 0-1), barres
    pour le temps de reponse (magnitude en secondes, sans limite naturelle,
    donc pas un ratio -- job "comparer une magnitude par identite")."""
    return {
        "pct_correct": _meter_series(
            [(l, kpis[l]["pct_correct"]) for l in LANGUES], 100, "%", good=80, warning=60, higher_is_better=True,
        ),
        "temps_moyen": [
            {"langue": l, "label": LANGUE_LABELS[l], "valeur": kpis[l]["temps_reponse"]["moyenne"], "color": LANGUE_COLORS[l]}
            for l in LANGUES if kpis[l]["temps_reponse"]["moyenne"] is not None
        ],
        "taux_fallback": _meter_series(
            [(l, kpis[l]["taux_fallback"]) for l in LANGUES], 100, "%", good=2, warning=8, higher_is_better=False,
        ),
        "score_confiance": _meter_series(
            [(l, kpis[l]["score_confiance_moyen"]) for l in LANGUES], 1, "", good=0.65, warning=0.5, higher_is_better=True,
        ),
        "coherence": _meter_series(
            [(l, consistency_avg.get(l)) for l in ("ar_fusha", "ar_tounsi")], 1, "", good=0.75, warning=0.6, higher_is_better=True,
        ),
    }


def build_comparison(kpis_avant: dict | None, kpis_apres: dict, consistency_avant: dict | None, consistency_apres: dict) -> list[dict]:
    """Donnees avant/apres corrections, une ligne par (metrique, langue),
    pretes pour un graphique dumbbell (voir competence dataviz,
    choosing-a-form.md : job "avant -> apres par item" = dumbbell, jamais
    une paire de barres). None si aucun run "avant" n'est disponible
    (premiere execution du test, pas encore de point de comparaison)."""
    if kpis_avant is None:
        return []

    metriques = [
        ("taux_fallback", "Taux d'échec", "%", False, LANGUES),
        ("score_confiance_moyen", "Score de confiance", "", True, LANGUES),
    ]
    comparaison = []
    for cle, label, unit, higher_is_better, langues in metriques:
        lignes = []
        for l in langues:
            avant = kpis_avant[l][cle]
            apres = kpis_apres[l][cle]
            if avant is None or apres is None:
                continue
            # None = pas de changement (avant == apres) -- distinct de "pire"
            # (False), sinon une metrique stable s'affiche en rouge comme si
            # elle avait regresse.
            ameliore = None if apres == avant else ((apres > avant) if higher_is_better else (apres < avant))
            lignes.append({
                "langue": l, "label": LANGUE_LABELS[l], "color": LANGUE_COLORS[l],
                "avant": avant, "apres": apres, "unit": unit, "ameliore": ameliore,
            })
        if lignes:
            comparaison.append({"metrique": label, "lignes": lignes})

    if consistency_avant:
        lignes = []
        for l in ("ar_fusha", "ar_tounsi"):
            avant = consistency_avant.get(l)
            apres = consistency_apres.get(l)
            if avant is None or apres is None:
                continue
            lignes.append({
                "langue": l, "label": LANGUE_LABELS[l], "color": LANGUE_COLORS[l],
                "avant": avant, "apres": apres, "unit": "",
                "ameliore": None if apres == avant else apres > avant,
            })
        if lignes:
            comparaison.append({"metrique": "Cohérence avec le français", "lignes": lignes})

    return comparaison


def build_stat_tiles(kpis_apres: dict, kpis_avant: dict | None) -> list[dict]:
    """Les quelques chiffres qu'un dashboard doit mener avec (voir
    competence dataviz, choosing-a-form.md : "une poignee de chiffres-cles"
    -> une rangee de stat tiles, jamais un graphique). Le delta vs le run
    "avant corrections" est signe et sa couleur depend du sens attendu
    (baisse du taux d'echec = bon, hausse du score de confiance = bon)."""
    g = kpis_apres["global"]

    def _delta(cle: str, higher_is_better: bool) -> dict | None:
        if kpis_avant is None:
            return None
        avant = kpis_avant["global"][cle]
        apres = kpis_apres["global"][cle]
        if avant is None or apres is None:
            return None
        ecart = round(apres - avant, 3)
        if ecart == 0:
            return None
        return {"valeur": ecart, "bon": (ecart > 0) == higher_is_better}

    tiles = [
        {"key": "total", "label": "Tests exécutés", "valeur": g["total"], "unit": "", "delta": None},
        {"key": "taux_fallback", "label": "Taux d'échec global", "valeur": g["taux_fallback"], "unit": "%", "delta": _delta("taux_fallback", False)},
        {"key": "score_confiance", "label": "Score de confiance moyen", "valeur": g["score_confiance_moyen"], "unit": "", "delta": _delta("score_confiance_moyen", True)},
        {
            "key": "pct_correct",
            "label": "% correct (annotés)",
            "valeur": g["pct_correct"],
            "unit": "%",
            "delta": None,
            "note": f"{g['nb_annote']} annotées" if g["nb_annote"] else "aucune annotation",
        },
    ]
    return tiles


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


# Cache indexe par un hash de contenu (pas mono-slot) : la page /qualite
# calcule desormais la coherence pour DEUX jeux de resultats a chaque
# chargement (le run courant + le snapshot "avant corrections" fige pour la
# comparaison, voir routers/quality.py::_load_avant_kpis) -- un seul slot
# global se ferait ecraser en permanence par l'un ou l'autre et perdrait
# tout interet (constate en concevant cette fonction : c'est exactement le
# bug de performance deja corrige une fois pour l'annotation, qui reviendrait
# sous une autre forme). Grandit tres lentement (une entree par contenu de
# reponses distinct jamais vu -- un nouveau run complet, essentiellement) :
# pas d'eviction, un processus admin de duree de vie courte n'en accumule
# jamais assez pour que ca compte.
_consistency_cache: dict[int, dict[int, dict[str, float | None]]] = {}


def compute_multilingual_consistency(results: list[dict]) -> dict[int, dict[str, float | None]]:
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
    cache_key = hash(tuple((r["id"], r.get("reponse")) for r in results))
    if cache_key in _consistency_cache:
        return _consistency_cache[cache_key]

    by_numero: dict[int, dict[str, dict]] = {}
    for r in results:
        # Une entree "live" (trafic reel, voir append_live_result) n'a pas
        # de numero -- elle n'a donc pas d'equivalent connu dans les 2
        # autres langues, contrairement aux questions du test fournies
        # dans les 3 langues a la fois. Sans ce garde-fou, toutes les
        # entrees live sans numero (numero=None) se regrouperaient a tort
        # sous une seule cle et seraient comparees entre elles comme si
        # c'etait la MEME question traduite -- alors que ce sont des
        # questions reelles totalement independantes.
        if r.get("numero") is None:
            continue
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

    _consistency_cache[cache_key] = consistency
    return consistency


def average_consistency(consistency: dict[int, dict[str, float | None]]) -> dict[str, float | None]:
    averages: dict[str, float | None] = {}
    for langue in ("ar_fusha", "ar_tounsi"):
        values = [v[langue] for v in consistency.values() if v.get(langue) is not None]
        averages[langue] = round(statistics.mean(values), 3) if values else None
    return averages
