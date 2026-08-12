"""
Dashboard qualite (/qualite) : affiche les resultats du test de 75
questions x 3 langues (scripts/run_quality_test.py) et permet a l'admin
d'annoter chaque reponse comme correcte/incorrecte (aucune reference
fournie par l'encadrant -- voir services/quality_test.py pour le detail
des KPI et pourquoi le "% correct" ne porte que sur les questions
annotees).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from extraction_app.auth import require_login
from extraction_app.config import APP_ROOT, STATIC_VERSION
from extraction_app.services import quality_test

router = APIRouter(tags=["quality"])
templates = Jinja2Templates(directory=str(APP_ROOT / "templates"))
templates.env.globals["static_version"] = STATIC_VERSION


@router.get("/qualite", response_class=HTMLResponse)
def qualite_page(request: Request, username: str = Depends(require_login)):
    results = quality_test.load_results()
    kpis = quality_test.compute_kpis(results)
    consistency = quality_test.compute_multilingual_consistency(results)
    consistency_avg = quality_test.average_consistency(consistency)
    charts = quality_test.build_chart_series(kpis, consistency_avg)

    # Regroupe par numero pour l'affichage (une ligne = une question, les
    # 3 langues cote a cote) plutot que 225 lignes plates.
    by_numero: dict[int, dict[str, dict]] = {}
    for r in results:
        by_numero.setdefault(r["numero"], {})[r["langue"]] = r
    rows = []
    for numero in sorted(by_numero):
        par_langue = by_numero[numero]
        rows.append({
            "numero": numero,
            "par_langue": par_langue,
            "consistency": consistency.get(numero, {}),
        })

    context = {
        "kpis": kpis,
        "consistency_avg": consistency_avg,
        "charts": charts,
        "rows": rows,
        "langues": quality_test.LANGUES,
        "langue_labels": quality_test.LANGUE_LABELS,
        "total_attendu": 75 * 3,
    }
    return templates.TemplateResponse(request, "qualite.html", context)


@router.post("/qualite/{result_id}/annoter")
def annoter(result_id: str, annotation: str = Form(...), username: str = Depends(require_login)):
    quality_test.set_annotation(result_id, annotation if annotation != "reset" else None)
    return RedirectResponse(url="/qualite", status_code=303)
