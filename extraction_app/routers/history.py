"""Page de suivi/historique des extractions (lecture seule)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from extraction_app.auth import require_login
from extraction_app.config import APP_ROOT
from extraction_app.services.kb_merge import get_history

router = APIRouter(tags=["history"])
templates = Jinja2Templates(directory=str(APP_ROOT / "templates"))


@router.get("/history", response_class=HTMLResponse)
def history_page(request: Request, username: str = Depends(require_login)):
    return templates.TemplateResponse(request, "history.html", {"entries": get_history()})
