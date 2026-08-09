"""
Page de validation des lots en attente (scraping automatique non supervise,
voir scheduler.py). C'est la SEULE route qui peut faire entrer dans la base
de connaissances du contenu produit sans qu'un admin ait directement
declenche l'action -- et seulement fiche par fiche, sur clic explicite
(Approuver), jamais automatiquement ni en bloc.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from extraction_app.auth import require_login
from extraction_app.config import APP_ROOT, STATIC_VERSION
from extraction_app.services import kb_merge, reindex
from extraction_app.services.semantic_dedup import get_cached_kb_deduper

router = APIRouter(tags=["validation"])
templates = Jinja2Templates(directory=str(APP_ROOT / "templates"))
templates.env.globals["static_version"] = STATIC_VERSION


@router.get("/a-valider", response_class=HTMLResponse)
def a_valider_page(request: Request, username: str = Depends(require_login)):
    batches = kb_merge.get_pending_batches()

    # Un seul deduper, construit une fois sur la base actuelle, reutilise
    # pour previsualiser TOUTES les fiches de TOUS les lots affiches -- mis
    # en cache tant que la base n'a pas change (voir get_cached_kb_deduper),
    # sinon reembedder ~800 fiches a chaque chargement de page prend ~65s.
    deduper = get_cached_kb_deduper(kb_merge.load_kb())

    # Un seul appel BATCHE au modele d'embeddings pour TOUTES les fiches de
    # TOUS les lots (au lieu d'un appel par fiche) -- avec un appel
    # individuel par fiche, charger cette page avec plusieurs centaines de
    # fiches en attente prenait plus d'une minute (mesure : ~95s). Batche,
    # la meme charge prend quelques secondes.
    all_candidates = [c for batch in batches for c in batch["candidates"]]
    previews = kb_merge.preview_batch_status(all_candidates, deduper)
    for candidate, preview in zip(all_candidates, previews):
        candidate["_preview"] = preview

    visible_batches = []
    for batch in batches:
        # Similarite maximale = 1 : doublon exact confirme avec une fiche
        # deja dans la base -- ne sert a rien de l'afficher, ca ne fait
        # qu'alourdir une liste deja tres longue pour un lot mensuel.
        # Reste approuvable/rejetable via "Tout approuver/rejeter" (le
        # filtre est uniquement d'affichage, rien n'est retire du lot).
        visible_candidates = [c for c in batch["candidates"] if c["_preview"]["score"] != 1]
        if not visible_candidates:
            continue
        batch["candidates"] = visible_candidates
        visible_batches.append(batch)

    context = {
        "batches": visible_batches,
        "index_stale": reindex.is_index_stale(),
        "last_reindex": reindex.get_last_result(),
    }
    return templates.TemplateResponse(request, "a_valider.html", context)


@router.post("/a-valider/reindexer")
def reindexer(username: str = Depends(require_login)):
    """Reconstruit l'index vectoriel ChromaDB (python -m modules.rag.ingest)
    -- bloquant le temps de la reconstruction complete (peut prendre de
    l'ordre de la minute), declenche uniquement sur clic explicite (jamais
    apres chaque approbation, voir services/reindex.py)."""
    reindex.run_ingest()
    return RedirectResponse(url="/a-valider", status_code=303)


@router.post("/a-valider/{batch_id}/fiche/{fiche_id}/approuver")
def approuver_fiche(batch_id: str, fiche_id: str, username: str = Depends(require_login)):
    kb_merge.approve_fiche(batch_id, fiche_id)
    return RedirectResponse(url="/a-valider", status_code=303)


@router.post("/a-valider/{batch_id}/fiche/{fiche_id}/rejeter")
def rejeter_fiche(batch_id: str, fiche_id: str, username: str = Depends(require_login)):
    kb_merge.reject_fiche(batch_id, fiche_id)
    return RedirectResponse(url="/a-valider", status_code=303)


@router.post("/a-valider/{batch_id}/approuver-tout")
def approuver_tout(batch_id: str, username: str = Depends(require_login)):
    kb_merge.approve_batch(batch_id)
    return RedirectResponse(url="/a-valider", status_code=303)


@router.post("/a-valider/{batch_id}/rejeter-tout")
def rejeter_tout(batch_id: str, username: str = Depends(require_login)):
    kb_merge.reject_batch(batch_id)
    return RedirectResponse(url="/a-valider", status_code=303)
