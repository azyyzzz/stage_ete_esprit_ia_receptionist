"""
Planificateur : relance chaque jour l'extraction pour les sources de type
"site web" deja enregistrees (jamais pour PDF/Excel/image uploades
manuellement -- ceux-ci ne sont pas re-executables sans le fichier original).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from extraction_app.config import URL_SOURCES_PATH
from extraction_app.services import kb_merge

DAILY_HOUR = 3  # 03h00, heure creuse

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
    quotidienne. Idempotent -- une meme URL n'est jamais dupliquee."""
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


def run_daily_rescrape() -> None:
    """Rejoue extraction -> filtres -> fusion pour chaque source web
    enregistree. Import differe de web_extractor pour eviter tout cout au
    demarrage de l'app si le job n'est jamais declenche."""
    from extraction_app.services.web_extractor import extract_url

    sources = _load_sources()
    for source in sources:
        url = source["url"]
        categorie = source["categorie"]
        error = None
        summary = None
        try:
            candidates, warning = extract_url(url, categorie)
            if warning is not None:
                error = warning
            else:
                summary = kb_merge.merge_candidates(candidates)
        except Exception as exc:
            error = str(exc)

        kb_merge.log_history(
            source=url,
            source_type="url",
            origin="planifie",
            summary=summary,
            error=error,
        )
        source["last_run"] = datetime.now(timezone.utc).isoformat()

    _write_sources(sources)


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(run_daily_rescrape, CronTrigger(hour=DAILY_HOUR, minute=0), id="daily_rescrape")
    _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
