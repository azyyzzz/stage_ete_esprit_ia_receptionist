"""
Dashboard qualite (/qualite) : affiche les resultats du test de 75
questions x 3 langues (scripts/run_quality_test.py) et permet a l'admin
d'annoter chaque reponse comme correcte/incorrecte (aucune reference
fournie par l'encadrant -- voir services/quality_test.py pour le detail
des KPI et pourquoi le "% correct" ne porte que sur les questions
annotees).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from extraction_app.auth import require_login
from extraction_app.config import APP_ROOT, DATA_DIR, STATIC_VERSION
from extraction_app.services import quality_test

router = APIRouter(tags=["quality"])
templates = Jinja2Templates(directory=str(APP_ROOT / "templates"))
templates.env.globals["static_version"] = STATIC_VERSION


def _load_avant_kpis() -> tuple[dict | None, dict | None]:
    """KPI du dernier run "avant corrections" sauvegarde (voir
    `extraction_app/data/quality_test_results_avant_corrections_*.jsonl`),
    pour le graphique de comparaison avant/apres -- None si aucune
    sauvegarde n'existe (cas normal avant la premiere serie de
    corrections)."""
    snapshots = sorted(DATA_DIR.glob("quality_test_results_avant_corrections_*.jsonl"))
    if not snapshots:
        return None, None
    avant_results = quality_test.load_results(path=snapshots[-1])
    if not avant_results:
        return None, None
    kpis_avant = quality_test.compute_kpis(avant_results)
    consistency_avant = quality_test.compute_multilingual_consistency(avant_results)
    return kpis_avant, quality_test.average_consistency(consistency_avant)


@router.get("/qualite", response_class=HTMLResponse)
def qualite_page(request: Request, username: str = Depends(require_login)):
    results = quality_test.load_results()
    kpis = quality_test.compute_kpis(results)
    consistency = quality_test.compute_multilingual_consistency(results)
    consistency_avg = quality_test.average_consistency(consistency)
    charts = quality_test.build_chart_series(kpis, consistency_avg)

    kpis_avant, consistency_avg_avant = _load_avant_kpis()
    stat_tiles = quality_test.build_stat_tiles(kpis, kpis_avant)
    comparaison = quality_test.build_comparison(kpis_avant, kpis, consistency_avg_avant, consistency_avg)

    # Liste unique, melangeant les questions du test (75 x 3 langues) ET
    # le trafic reel journalise en direct (voir modules/quality_log.py) --
    # les KPI/graphiques ci-dessus melangent deja les deux (compute_kpis
    # etc. ne distinguent pas la source), l'affichage detaille suit la
    # meme logique plutot que de separer visuellement un "test" d'un
    # "reel". Plus recent en premier : le trafic reel arrive au fil de
    # l'eau, une liste chronologique se lit comme un journal.
    entries = sorted(results, key=lambda r: r.get("date") or "", reverse=True)
    for r in entries:
        numero = r.get("numero")
        r["coherence_fr"] = consistency.get(numero, {}).get(r["langue"]) if numero is not None else None

    context = {
        "kpis": kpis,
        "consistency_avg": consistency_avg,
        "charts": charts,
        "stat_tiles": stat_tiles,
        "comparaison": comparaison,
        "entries": entries,
        "langues": quality_test.LANGUES,
        "langue_labels": quality_test.LANGUE_LABELS,
        "total_attendu": 75 * 3,
    }
    return templates.TemplateResponse(request, "qualite.html", context)


def _dashboard_payload() -> dict:
    """KPI/jauges/tuiles recalcules a partir de l'etat courant du journal --
    payload JSON partage par annoter() et supprimer() (voir qualite.html,
    applyRealtimeUpdate()) pour que les deux actions mettent a jour le
    dashboard en direct sans recharger la page. N'inclut PAS `comparaison`
    (avant/apres) : elle compare a un snapshot fige, une annotation ou une
    suppression ne la fait jamais changer, pas la peine de la recalculer
    ni de la renvoyer a chaque fois."""
    results = quality_test.load_results()
    kpis = quality_test.compute_kpis(results)
    consistency_avg = quality_test.average_consistency(quality_test.compute_multilingual_consistency(results))
    charts = quality_test.build_chart_series(kpis, consistency_avg)
    kpis_avant, _ = _load_avant_kpis()
    stat_tiles = quality_test.build_stat_tiles(kpis, kpis_avant)
    return {"kpis": kpis, "consistency_avg": consistency_avg, "stat_tiles": stat_tiles, "charts": charts}


@router.post("/qualite/{result_id}/annoter")
def annoter(request: Request, result_id: str, annotation: str = Form(...), username: str = Depends(require_login)):
    valeur = None if annotation == "reset" else annotation
    try:
        quality_test.set_annotation(result_id, valeur)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Appel AJAX (fetch, voir qualite.html) : renvoie le nouvel etat ET les
    # KPI/jauges recalcules, sans recharger toute la page -- un formulaire
    # classique rechargerait /qualite et ramenerait le scroll en haut,
    # rendant l'annotation de 225+ reponses une par une extremement
    # penible.
    if request.headers.get("x-requested-with") == "fetch":
        return JSONResponse({"id": result_id, "annotation": valeur, **_dashboard_payload()})

    return RedirectResponse(url="/qualite", status_code=303)


@router.post("/qualite/{result_id}/supprimer")
def supprimer(request: Request, result_id: str, username: str = Depends(require_login)):
    try:
        quality_test.delete_result(result_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if request.headers.get("x-requested-with") == "fetch":
        return JSONResponse({"id": result_id, "deleted": True, **_dashboard_payload()})

    return RedirectResponse(url="/qualite", status_code=303)
