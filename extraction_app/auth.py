"""
Authentification simple a compte unique.

Session cote serveur (dictionnaire en memoire token -> nom d'utilisateur) +
cookie HttpOnly contenant le token. Suffisant pour un outil interne
mono-utilisateur, mono-processus -- pas concu pour un usage multi-utilisateur
ni pour survivre a un redemarrage (une reconnexion suffit dans ce cas).
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from extraction_app.bootstrap_credentials import verify_password
from extraction_app.config import APP_ROOT, SESSION_COOKIE_NAME, STATIC_VERSION

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory=str(APP_ROOT / "templates"))
templates.env.globals["static_version"] = STATIC_VERSION

# token de session -> nom d'utilisateur
_ACTIVE_SESSIONS: dict[str, str] = {}


class LoginRequired(Exception):
    """Levee par require_login quand la session est absente/invalide.
    Interceptee par le handler enregistre dans main.py pour rediriger
    proprement vers /login (voir register_auth_exception_handler)."""


def require_login(request: Request) -> str:
    """Dependance FastAPI : renvoie le nom d'utilisateur si la session est
    valide, sinon leve LoginRequired (transforme en redirection par le
    handler d'exception global)."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    username = _ACTIVE_SESSIONS.get(token) if token else None
    if username is None:
        raise LoginRequired()
    return username


def register_auth_exception_handler(app) -> None:
    @app.exception_handler(LoginRequired)
    def _handle_login_required(request: Request, exc: LoginRequired):
        return RedirectResponse(url="/login", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
def login_submit(request: Request, username: str = Form(""), password: str = Form("")):
    if not verify_password(username, password):
        return templates.TemplateResponse(
            request, "login.html", {"error": "Identifiants incorrects."}, status_code=401
        )
    token = secrets.token_urlsafe(32)
    _ACTIVE_SESSIONS[token] = username
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(SESSION_COOKIE_NAME, token, httponly=True, samesite="lax")
    return response


@router.get("/logout")
def logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    _ACTIVE_SESSIONS.pop(token, None)
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response
