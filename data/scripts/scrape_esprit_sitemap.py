"""
Scraping systematique de l'ensemble des pages "statiques" du site esprit.tn
(pas les articles/actualites, voir exclusions ci-dessous), via le sitemap
WordPress officiel (page-sitemap.xml) plutot qu'une liste d'URLs choisie a
la main (comme data/scripts/esprit_scraper_final.py) -- garantit de ne
rater aucune page connue de WordPress (70 pages au moment de l'ecriture).

Reutilise le meme extracteur que l'upload manuel d'URL dans extraction_app
(services/web_extractor.py::extract_url) -- structure FAQ-accordeon dediee
pour esprit.tn, repli generique par sections h2/h3 sinon.

Chaque page produit un LOT DISTINCT depose dans la file d'attente de
validation (extraction_app/data/a_valider.json, voir services/kb_merge.py
::queue_for_validation) -- AUCUNE ecriture automatique dans la base. Meme
politique que le scraping mensuel des options (scrape_esprit_tunis_
options.py) : decision explicite avec l'utilisateur de ne jamais laisser
un scraping non supervise modifier site_esprit.json sans validation admin
fiche par fiche sur /a-valider.

Exclusions volontaires :
- post-sitemap.xml (actualites/evenements) : contenu transitoire (annonces
  d'evenements passes), pas des "connaissances" utiles a un assistant de
  reception -- meme mecanisme si besoin de changer d'avis, juste une autre
  URL de sitemap a ajouter a SITEMAP_URLS.
- Les 4 pages de specialites ESPRIT Tunis (deja couvertes par un parsing
  dedie beaucoup plus precis, voir scrape_esprit_tunis_options.py) : le
  scraper generique de ce script-ci ne saurait pas lire les accordeons
  d'options et produirait des fiches degradees en double emploi.
- Pages utilitaires sans contenu informatif (404, confirmation d'abonnement
  newsletter).

Installation :
    pip install requests beautifulsoup4

Lancement (depuis la racine du projet) :
    python data/scripts/scrape_esprit_sitemap.py
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

# Rend "extraction_app" importable meme lance en mode script direct
# (python data/scripts/scrape_esprit_sitemap.py) -- dans ce mode, Python
# n'ajoute que le dossier du script (data/scripts/) a sys.path, pas la
# racine du projet, contrairement au mode `-m`. Insere en position 0
# (avant les entrees existantes) pour primer sur d'autres "data" installes.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import requests

from extraction_app.services.kb_merge import queue_for_validation
from extraction_app.services.web_extractor import extract_url

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ESPRIT-AI-Receptionist-SitemapBot/1.0)"}
SITEMAP_URL = "https://www.esprit.tn/page-sitemap.xml"
REQUEST_DELAY = 1.0

EXCLUDE_URLS = {
    "https://www.esprit.tn/nos-programmes/programmes-dingenieur/esprit-tunis/ingenieur-en-genie-civil/",
    "https://www.esprit.tn/nos-programmes/programmes-dingenieur/esprit-tunis/ingenieur-en-genie-des-telecommunications/",
    "https://www.esprit.tn/nos-programmes/programmes-dingenieur/esprit-tunis/ingenieur-en-genie-electromecanique/",
    "https://www.esprit.tn/nos-programmes/programmes-dingenieur/esprit-tunis/ingenieur-en-genie-informatique/",
}

EXCLUDE_PATH_SUFFIXES = ("/404-error/", "/abonnement-confirme/")

# Segment d'URL le plus specifique -> categorie (meme style que
# data/scripts/esprit_scraper_final.py, pour rester coherent avec le reste
# de la base). Le PREMIER prefixe qui matche gagne.
CATEGORY_BY_PATH_PREFIX: list[tuple[str, str]] = [
    ("/admissions/foire-aux-questions/", "FAQ"),
    ("/admissions/", "Admissions"),
    ("/a-propos-desprit/", "À propos"),
    ("/groupe-esprit/", "Groupe ESPRIT"),
    ("/nos-programmes/", "Programmes"),
    ("/recherche/", "Recherche"),
    ("/stages-et-entreprises/", "Stages et entreprises"),
    ("/vie-estudiantine/", "Vie étudiante"),
    ("/contact/", "Contact"),
]


def categorize(url: str) -> str:
    path = url.replace("https://www.esprit.tn", "")
    for prefix, categorie in CATEGORY_BY_PATH_PREFIX:
        if path.startswith(prefix):
            return categorie
    return "Accueil"


def discover_pages() -> list[str]:
    resp = requests.get(SITEMAP_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    urls = re.findall(r"<loc>(.*?)</loc>", resp.text)
    return [u for u in urls if u not in EXCLUDE_URLS and not u.endswith(EXCLUDE_PATH_SUFFIXES)]


def main() -> None:
    urls = discover_pages()
    print(f"{len(urls)} pages decouvertes via {SITEMAP_URL} (apres exclusions)")

    total_queued = 0
    total_skipped = 0
    for url in urls:
        categorie = categorize(url)
        print(f"[{categorie}] {url}")
        candidates, warning = extract_url(url, categorie)
        if warning is not None:
            print(f"  [ignore] {warning}")
            total_skipped += 1
        elif candidates:
            batch_id = queue_for_validation(
                source=url, categorie=categorie, origin="scraping_site_complet", candidates=candidates,
            )
            print(f"  -> {len(candidates)} fiches deposees en attente (lot {batch_id})")
            total_queued += len(candidates)
        else:
            print("  [ignore] aucune fiche extraite")
            total_skipped += 1
        time.sleep(REQUEST_DELAY)

    print(f"\nTermine : {total_queued} fiches deposees en attente sur /a-valider, {total_skipped} page(s) ignoree(s).")
    print("Rien n'a ete ecrit dans site_esprit.json -- valide chaque fiche sur /a-valider pour l'ajouter reellement.")


if __name__ == "__main__":
    main()
