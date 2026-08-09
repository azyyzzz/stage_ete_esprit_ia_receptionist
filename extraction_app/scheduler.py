"""
Planificateur : relance une fois par mois (1er du mois) l'extraction pour
les sources de type "site web" deja enregistrees (jamais pour PDF/Excel/
image uploades manuellement -- ceux-ci ne sont pas re-executables sans le
fichier original).

Lance aussi, le meme jour a une heure differente, le scraping des options
de specialisation ESPRIT Tunis (data/scripts/scrape_esprit_tunis_options.py).

AUCUN de ces jobs ne fusionne directement dans site_esprit.json : les
fiches candidates sont toujours deposees dans la file d'attente de
validation (kb_merge.queue_for_validation) et n'entrent dans la base que
si un admin clique "Approuver" sur /a-valider (voir routers/validation.py)
-- decision explicite de l'utilisateur, valable pour TOUT scraping non
supervise en direct par un humain, planifie ou non (voir aussi
routers/extraction.py pour les uploads manuels, qui suivent la meme regle).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from extraction_app.config import URL_SOURCES_PATH
from extraction_app.services import kb_merge

URL_RESCRAPE_HOUR = 3  # 03h00, heure creuse
MONTHLY_DAY = 1  # 1er du mois
OPTIONS_SCRAPE_HOUR = 4  # 04h00, heure creuse (decalee du re-scraping des URLs)

_scheduler: BackgroundScheduler | None = None


def _load_sources() -> list[dict]:
    if not URL_SOURCES_PATH.exists():
        return []
    with open(URL_SOURCES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_sources(sources: list[dict]) -> None:
    URL_SOURCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(URL_SOURCES_PATH, "w", encoding="utf-8") as f:
        json.dump(sources, f, ensure_ascii=False, indent=2)


def register_url_source(url: str, categorie: str) -> None:
    """Enregistre (ou met a jour) une source URL pour la re-extraction
    mensuelle. Idempotent -- une meme URL n'est jamais dupliquee."""
    sources = _load_sources()
    for source in sources:
        if source["url"] == url:
            source["categorie"] = categorie
            _write_sources(sources)
            return
    sources.append(
        {
            "url": url,
            "categorie": categorie,
            "added_date": datetime.now(timezone.utc).isoformat(),
            "last_run": None,
        }
    )
    _write_sources(sources)


def run_monthly_url_rescrape() -> None:
    """Rejoue extraction -> filtres -> depot en attente pour chaque source
    web enregistree -- AUCUNE fusion directe (voir docstring du module).
    Import differe de web_extractor pour eviter tout cout au demarrage de
    l'app si le job n'est jamais declenche."""
    from extraction_app.services.web_extractor import extract_url

    sources = _load_sources()
    for source in sources:
        url = source["url"]
        categorie = source["categorie"]
        error = None
        batch_id = None
        try:
            candidates, warning = extract_url(url, categorie)
            if warning is not None:
                error = warning
            elif candidates:
                batch_id = kb_merge.queue_for_validation(
                    source=url, categorie=categorie, origin="planifie", candidates=candidates,
                )
        except Exception as exc:
            error = str(exc)

        kb_merge.log_history(
            source=url,
            source_type="url",
            origin="planifie",
            summary=None,
            error=error,
            manual_review=batch_id is not None,
        )
        source["last_run"] = datetime.now(timezone.utc).isoformat()

    _write_sources(sources)


def run_monthly_options_scrape() -> None:
    """Scrape les options de specialisation ESPRIT Tunis et depose le lot
    dans la file d'attente de validation -- AUCUNE ecriture directe dans
    site_esprit.json (voir docstring du module). Reutilise le parsing HTML
    deja teste/valide du script (extract_options/scrape_all/to_kb_record),
    seul le point d'integration change par rapport a un lancement manuel du
    script en CLI (qui, lui, ecrit directement -- usage volontaire par un
    humain qui execute la commande lui-meme et inspecte le resultat)."""
    from data.scripts.scrape_esprit_tunis_options import scrape_all, to_kb_record

    error = None
    batch_id = None
    try:
        raw_data = scrape_all()
        candidates = [to_kb_record(e) for e in raw_data]
        if not candidates:
            error = "Aucune option extraite (structure de la page probablement changee)."
        else:
            batch_id = kb_merge.queue_for_validation(
                source="Scraping automatique - Options ESPRIT Tunis",
                categorie="Options",
                origin="planifie_options",
                candidates=candidates,
            )
    except Exception as exc:
        error = str(exc)

    kb_merge.log_history(
        source="Scraping automatique - Options ESPRIT Tunis",
        source_type="scraping_planifie",
        origin="planifie_options",
        summary=None,
        error=error,
        manual_review=batch_id is not None,
    )


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        run_monthly_url_rescrape,
        CronTrigger(day=MONTHLY_DAY, hour=URL_RESCRAPE_HOUR, minute=0),
        id="monthly_url_rescrape",
    )
    _scheduler.add_job(
        run_monthly_options_scrape,
        CronTrigger(day=MONTHLY_DAY, hour=OPTIONS_SCRAPE_HOUR, minute=0),
        id="monthly_options_scrape",
    )
    _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
