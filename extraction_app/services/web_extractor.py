"""
Extraction web generique -- adapte de
data/scripts/web_scraping_espace_etudiant.py.

Si le domaine est esprit.tn, tente d'abord la structure FAQ-accordeon
(Elementor) ; sinon (ou en repli si la structure FAQ n'est pas trouvee),
extraction generique par sections h2/h3, en ignorant nav/header/footer/
script/form.

Limite assumee et non masquee (contrainte explicite de l'utilisateur) : un
scraper requests+BeautifulSoup ne peut pas executer de JavaScript ni
contourner un blocage anti-bot. Si le contenu recupere est vide ou
anormalement court, on ne sauvegarde AUCUNE fiche trompeuse -- un
avertissement clair est retourne a la place.
"""

from __future__ import annotations

import re
import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from extraction_app.config import MIN_SCRAPE_CHARS

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ESPRIT-AI-Receptionist-ExtractionApp/1.0)"}
REQUEST_DELAY = 1.0
REQUEST_TIMEOUT = 20

FAQ_TITLE_SELECTORS = ".elementor-tab-title, .e-n-accordion-item-title, .elementor-toggle-title"
FAQ_CONTENT_SELECTORS = ".elementor-tab-content, .e-n-accordion-item-content, .elementor-toggle-content"

ACCORDION_LABEL_PATTERN = re.compile(r"^(Ouvrir|Fermer) la visibilité du contenu\s*:?\s*", re.IGNORECASE)

SCRAPE_FAILED_WARNING = (
    "Ce site n'a pas pu être scrapé complètement, son contenu est peut-être chargé dynamiquement."
)


def _slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    return text.strip("_")[:60]


def _strip_accordion_label(text: str) -> str:
    return ACCORDION_LABEL_PATTERN.sub("", text).strip()


def _safe_get(url: str) -> requests.Response | None:
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        time.sleep(REQUEST_DELAY)
        return response
    except requests.RequestException:
        return None


def _extract_faq(soup: BeautifulSoup, url: str, categorie: str) -> list[dict]:
    titles = soup.select(FAQ_TITLE_SELECTORS)
    contents = soup.select(FAQ_CONTENT_SELECTORS)
    if not titles or len(titles) != len(contents):
        return _extract_generic(soup, url, categorie)

    records = []
    for i, (title_el, content_el) in enumerate(zip(titles, contents), start=1):
        question = _strip_accordion_label(title_el.get_text(strip=True))
        answer = content_el.get_text(" ", strip=True)
        if question and answer:
            records.append(
                {
                    "id": f"upload_url_faq_{_slugify(url)}_{i:03d}",
                    "categorie": categorie,
                    "titre": question,
                    "contenu": answer,
                    "source": url,
                }
            )
    return records


def _extract_generic(soup: BeautifulSoup, url: str, categorie: str) -> list[dict]:
    for tag in soup.select("header, footer, nav, script, style, form"):
        tag.decompose()

    page_title_el = soup.find("h1")
    page_title = _strip_accordion_label(page_title_el.get_text(strip=True)) if page_title_el else url

    body = soup.find("body") or soup
    slug = _slugify(url)

    records: list[dict] = []
    current_heading = page_title
    current_text: list[str] = []
    section_index = 1

    def flush_section() -> None:
        nonlocal section_index
        text = " ".join(current_text).strip()
        text = re.sub(r"\s+", " ", text)
        if text and len(text) > 40:
            records.append(
                {
                    "id": f"upload_url_{slug}_{section_index:03d}",
                    "categorie": categorie,
                    "titre": current_heading,
                    "contenu": text,
                    "source": url,
                }
            )
            section_index += 1

    for el in body.find_all(["h1", "h2", "h3", "p", "li"]):
        if el.name in ("h1", "h2", "h3"):
            flush_section()
            current_heading = _strip_accordion_label(el.get_text(strip=True)) or page_title
            current_text = []
        else:
            text = el.get_text(" ", strip=True)
            if text:
                current_text.append(text)
    flush_section()

    return records


def extract_url(url: str, categorie: str) -> tuple[list[dict], str | None]:
    """Retourne (fiches, avertissement). avertissement est None si le
    scraping a produit un contenu suffisant ; sinon fiches est vide et
    avertissement explique pourquoi (jamais de fiche vide/trompeuse)."""
    response = _safe_get(url)
    if response is None:
        return [], f"Impossible de récupérer {url} (erreur réseau, timeout, ou statut HTTP d'erreur)."

    soup = BeautifulSoup(response.text, "html.parser")
    is_esprit = "esprit.tn" in urlparse(url).netloc.lower()

    if is_esprit:
        records = _extract_faq(soup, url, categorie)
    else:
        records = _extract_generic(soup, url, categorie)

    total_chars = sum(len(r["contenu"]) for r in records)
    if not records or total_chars < MIN_SCRAPE_CHARS:
        return [], SCRAPE_FAILED_WARNING

    return records, None
