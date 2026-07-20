"""
Page d'upload et point d'entree POST /extract, routes par type de source
vers le bon service d'extraction (services/pdf_extractor.py,
excel_extractor.py, image_extractor.py, docx_extractor.py,
web_extractor.py), puis vers services/kb_merge.py pour le
filtrage/dedup/fusion/journalisation.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from extraction_app.auth import require_login
from extraction_app.config import APP_ROOT, UPLOADS_DIR
from extraction_app.services import kb_merge
from extraction_app.services.docx_extractor import extract_docx
from extraction_app.services.excel_extractor import extract_excel
from extraction_app.services.image_extractor import extract_image
from extraction_app.services.pdf_extractor import extract_pdf
from extraction_app.services.web_extractor import extract_url
from extraction_app.scheduler import register_url_source

router = APIRouter(tags=["extraction"])
templates = Jinja2Templates(directory=str(APP_ROOT / "templates"))

CATEGORIES = [
    "FAQ", "Admissions", "Paiements", "Règlements", "Calendrier",
    "Vie étudiante", "Stages", "Programmes", "Contacts",
]


def _save_upload(file: UploadFile) -> Path:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "").suffix
    dest = UPLOADS_DIR / f"{uuid.uuid4().hex}{suffix}"
    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out)
    return dest


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, username: str = Depends(require_login)):
    return templates.TemplateResponse(request, "dashboard.html", {"categories": CATEGORIES, "result": None})


@router.post("/extract", response_class=HTMLResponse)
def extract(
    request: Request,
    source_type: str = Form(...),
    categorie: str = Form(...),
    url: str = Form(""),
    file: UploadFile | None = File(None),
    username: str = Depends(require_login),
):
    context = {"categories": CATEGORIES, "result": None}
    error = None
    manual_review = False
    summary = None
    source_label = url.strip() if source_type == "url" else (file.filename if file else "")

    # Derive de l'id des fiches a partir du nom de fichier ORIGINAL (pas du
    # chemin temporaire, aleatoire) pour que la dedup par id (kb_merge.py)
    # detecte bien un re-upload du meme fichier.
    id_slug = Path(file.filename).stem if file and file.filename else None

    try:
        if source_type == "pdf":
            if not file:
                raise ValueError("Aucun fichier PDF fourni.")
            path = _save_upload(file)
            candidates = extract_pdf(path, categorie, source_label, id_slug=id_slug)
            summary = kb_merge.merge_candidates(candidates)

        elif source_type == "docx":
            if not file:
                raise ValueError("Aucun fichier Word fourni.")
            path = _save_upload(file)
            candidates = extract_docx(path, categorie, source_label, id_slug=id_slug)
            summary = kb_merge.merge_candidates(candidates)

        elif source_type == "excel":
            if not file:
                raise ValueError("Aucun fichier Excel fourni.")
            path = _save_upload(file)
            candidates = extract_excel(path, categorie, source_label, id_slug=id_slug)
            summary = kb_merge.merge_candidates(candidates)

        elif source_type == "image":
            if not file:
                raise ValueError("Aucune image fournie.")
            path = _save_upload(file)
            candidates, review_item = extract_image(path, categorie, source_label, id_slug=id_slug)
            if review_item is not None:
                kb_merge.log_manual_review(review_item)
                manual_review = True
            else:
                summary = kb_merge.merge_candidates(candidates)

        elif source_type == "url":
            if not url.strip():
                raise ValueError("Aucune URL fournie.")
            candidates, warning = extract_url(url.strip(), categorie)
            if warning is not None:
                error = warning
            else:
                summary = kb_merge.merge_candidates(candidates)
                register_url_source(url.strip(), categorie)

        else:
            raise ValueError(f"Type de source inconnu : {source_type}")

    except Exception as exc:  # remonte une erreur claire, ne plante jamais l'app
        error = str(exc)

    kb_merge.log_history(
        source=source_label or "(inconnu)",
        source_type=source_type,
        origin="manuel",
        summary=summary,
        error=error,
        manual_review=manual_review,
    )

    context["result"] = {
        "source": source_label,
        "error": error,
        "manual_review": manual_review,
        "summary": summary,
    }
    return templates.TemplateResponse(request, "dashboard.html", context)
