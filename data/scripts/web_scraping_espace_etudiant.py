"""
Crawler complet du site esprit.tn pour constituer la base de connaissances
du projet ESPRIT AI Receptionist.

Ce script :
1. Parcourt une liste de pages "seed" couvrant toutes les sections utiles du site
2. Pour chaque page HTML, extrait le texte utile (titres + paragraphes),
   avec un traitement spécial pour la page FAQ (structure question/réponse)
3. Détecte automatiquement les liens vers des PDF sur chaque page,
   les télécharge et en extrait le texte page par page
4. Sauvegarde tout au même format JSON structuré, catégorisé par section

Installation :
    pip install requests beautifulsoup4 pdfplumber

Lancement :
    python esprit_scraper_final.py
"""

import os
import re
import json
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
import pdfplumber

BASE_DOMAIN = "esprit.tn"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ESPRIT-AI-Receptionist-Bot/1.0)"}
REQUEST_DELAY = 1.0  # secondes entre deux requêtes, pour rester poli avec le serveur

# Rend les chemins indépendants du dossier courant d'execution.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW_DIR = os.path.join(PROJECT_ROOT, "data", "raw_data")
PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data", "processed")
OUTPUT_PATH = os.path.join(PROCESSED_DIR, "site_esprit.json")

# ----------------------------------------------------------------------------
# 1. Liste des pages de départ, organisées par catégorie.
#    C'est la carte du site construite à partir du menu de navigation réel.
# ----------------------------------------------------------------------------
SEED_PAGES = {
    "FAQ": [
        "https://www.esprit.tn/admissions/foire-aux-questions/",
    ],
    "Admissions": [
        "https://www.esprit.tn/admissions/",
        "https://www.esprit.tn/admissions/informations-pratiques/",
        "https://www.esprit.tn/admissions/cours-du-jour/cours-du-jour-tunisiens/",
        "https://www.esprit.tn/admissions/cours-du-jour/cours-du-jour-internationaux/",
        "https://www.esprit.tn/admissions/cours-du-soir/",
        "https://www.esprit.tn/admissions/formation-en-alternance/",
        "https://www.esprit.tn/admissions/mobilite-internationale-a-esprit/",
        "https://www.esprit.tn/admissions/nos-conseillers-admission/",
    ],
    "Vie étudiante": [
        "https://www.esprit.tn/vie-estudiantine/reglement-interieur/",
        "https://www.esprit.tn/vie-estudiantine/visite-virtuelle/",
        "https://www.esprit.tn/vie-estudiantine/etudiants-internationaux/",
        "https://www.esprit.tn/vie-estudiantine/clubs-esprit/",
        "https://www.esprit.tn/vie-estudiantine/alumni-esprit/",
        "https://www.esprit.tn/vie-estudiantine/cellule-decoute/",
    ],
    "Programmes": [
        "https://www.esprit.tn/nos-programmes/programmes-dingenieur/",
        "https://www.esprit.tn/groupe-esprit/esprit-prepa/",
        "https://www.esprit.tn/nos-programmes/programmes-dingenieur/esprit-monastir/",
        "https://www.esprit.tn/nos-programmes/programme-executive-2/emba-esprit-tunis/",
        "https://www.esprit.tn/nos-programmes/classe-internationale-2/",
        "https://www.esprit.tn/nos-programmes/esprit-school-of-business/bac3-bachelor-esb/",
        "https://www.esprit.tn/nos-programmes/esprit-school-of-business/bac5-master/",
    ],
    "À propos": [
        "https://www.esprit.tn/a-propos-desprit/missions-et-valeurs/",
        "https://www.esprit.tn/a-propos-desprit/lhistoire-de-groupe-esprit/",
        "https://www.esprit.tn/a-propos-desprit/gouvernance/",
        "https://www.esprit.tn/a-propos-desprit/le-plus-de-la-formation-a-esprit/",
        "https://www.esprit.tn/a-propos-desprit/affiliation-et-accreditations/",
        "https://www.esprit.tn/a-propos-desprit/responsabilite-societale/",
        "https://www.esprit.tn/a-propos-desprit/fondation-esprit/",
    ],
    "Groupe ESPRIT": [
        "https://www.esprit.tn/groupe-esprit/esprit-school-of-business-esb/",
        "https://www.esprit.tn/groupe-esprit/esprit-monastir-esprim/",
        "https://www.esprit.tn/groupe-esprit/esprit-entreprise/",
        "https://www.esprit.tn/groupe-esprit/centre-de-langues-esprit/",
        "https://www.esprit.tn/groupe-esprit/centre-de-carriere/",
    ],
    "Recherche": [
        "https://www.esprit.tn/recherche/esprit-tech/esprit-tech-presentation-generale/",
        "https://www.esprit.tn/recherche/esprit-tech/equipe-de-recherche/",
        "https://www.esprit.tn/recherche/esprit-tech/axes-de-recherche/",
    ],
    "Stages et entreprises": [
        "https://www.esprit.tn/stages-et-entreprises/partenariats/",
        "https://www.esprit.tn/stages-et-entreprises/stages/",
    ],
    "Contact": [
        "https://www.esprit.tn/contact/",
    ],
}

# Domaines à ne jamais suivre : portails privés (connexion requise), réseaux sociaux
EXCLUDE_DOMAINS = ["arp.esprit.tn", "esprit-tn.com", "facebook.com", "instagram.com",
                   "x.com", "youtube.com", "linkedin.com", "google.com"]

# FAQ : sélecteurs CSS possibles pour les blocs question/réponse (Elementor).
# À vérifier/ajuster en inspectant la page réelle dans le navigateur si besoin.
FAQ_TITLE_SELECTORS = ".elementor-tab-title, .e-n-accordion-item-title, .elementor-toggle-title"
FAQ_CONTENT_SELECTORS = ".elementor-tab-content, .e-n-accordion-item-content, .elementor-toggle-content"


def safe_get(url: str) -> requests.Response | None:
    """Récupère une URL en gérant proprement les erreurs, sans arrêter tout le script."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        time.sleep(REQUEST_DELAY)
        return response
    except requests.RequestException as e:
        print(f"  [erreur] impossible de récupérer {url} : {e}")
        return None


def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    return text.strip("_")[:60]


def extract_faq(soup: BeautifulSoup, url: str) -> list[dict]:
    """Traitement spécial de la page FAQ : structure question/réponse."""
    titles = soup.select(FAQ_TITLE_SELECTORS)
    contents = soup.select(FAQ_CONTENT_SELECTORS)

    if not titles or len(titles) != len(contents):
        print("  [attention] structure FAQ inattendue, bascule sur extraction générique.")
        return extract_generic_page(soup, url, "FAQ")

    records = []
    for i, (title_el, content_el) in enumerate(zip(titles, contents), start=1):
        question = title_el.get_text(strip=True)
        question = question.replace("Ouvrir la visibilité du contenu :", "").strip()
        answer = content_el.get_text(" ", strip=True)
        if question and answer:
            records.append({
                "id": f"faq_{i:04d}",
                "categorie": "FAQ",
                "titre": question,
                "contenu": answer,
                "source": url,
                "type": "page",
            })
    return records


def extract_generic_page(soup: BeautifulSoup, url: str, categorie: str) -> list[dict]:
    """
    Extraction générique pour une page HTML classique :
    on découpe le contenu par section (chaque titre h2/h3 démarre une nouvelle fiche).
    """
    # On retire les éléments qui ne sont pas du contenu utile
    for tag in soup.select("header, footer, nav, script, style, form, .elementor-location-header, .elementor-location-footer"):
        tag.decompose()

    page_title_el = soup.find("h1")
    page_title = page_title_el.get_text(strip=True) if page_title_el else url

    body = soup.find("body") or soup

    records = []
    current_heading = page_title
    current_text = []
    section_index = 1
    slug = slugify(page_title)

    def flush_section():
        nonlocal section_index
        text = " ".join(current_text).strip()
        text = re.sub(r"\s+", " ", text)
        if text and len(text) > 40:  # ignore les sections trop courtes / vides
            records.append({
                "id": f"{categorie.lower().replace(' ', '_')}_{slug}_{section_index:03d}",
                "categorie": categorie,
                "titre": current_heading,
                "contenu": text,
                "source": url,
                "type": "page",
            })
            section_index += 1

    for el in body.find_all(["h1", "h2", "h3", "p", "li"]):
        if el.name in ("h1", "h2", "h3"):
            flush_section()
            current_heading = el.get_text(strip=True) or page_title
            current_text = []
        else:
            text = el.get_text(" ", strip=True)
            if text:
                current_text.append(text)
    flush_section()

    return records


def find_pdf_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Trouve tous les liens vers des fichiers PDF présents sur une page."""
    pdf_links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        if href.lower().endswith(".pdf") and BASE_DOMAIN in urlparse(href).netloc:
            pdf_links.append(href)
    return list(dict.fromkeys(pdf_links))  # dédoublonne en gardant l'ordre


def process_pdf(pdf_url: str, categorie: str) -> list[dict]:
    """Télécharge un PDF et extrait son texte, page par page."""
    response = safe_get(pdf_url)
    if response is None:
        return []

    filename = os.path.basename(urlparse(pdf_url).path) or f"{slugify(pdf_url)}.pdf"
    raw_path = os.path.join(RAW_DIR, slugify(categorie), filename)
    os.makedirs(os.path.dirname(raw_path), exist_ok=True)
    with open(raw_path, "wb") as f:
        f.write(response.content)

    records = []
    try:
        with pdfplumber.open(raw_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = (page.extract_text() or "").strip()
                text = re.sub(r"\s+", " ", text)
                if text:
                    records.append({
                        "id": f"{slugify(categorie)}_{slugify(filename)}_p{page_num:03d}",
                        "categorie": categorie,
                        "titre": f"{filename} - page {page_num}",
                        "contenu": text,
                        "source": pdf_url,
                        "type": "pdf",
                    })
    except Exception as e:
        print(f"  [erreur] lecture PDF {pdf_url} : {e}")
    return records


def process_page(url: str, categorie: str) -> list[dict]:
    print(f"[{categorie}] {url}")
    response = safe_get(url)
    if response is None:
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    # Sauvegarde du HTML brut pour traçabilité / débogage
    raw_path = os.path.join(RAW_DIR, slugify(categorie), f"{slugify(url)}.html")
    os.makedirs(os.path.dirname(raw_path), exist_ok=True)
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(response.text)

    if categorie == "FAQ":
        records = extract_faq(soup, url)
    else:
        records = extract_generic_page(soup, url, categorie)

    # Détection et traitement des PDF trouvés sur cette page
    pdf_links = find_pdf_links(soup, url)
    for pdf_url in pdf_links:
        print(f"  -> PDF trouvé : {pdf_url}")
        records.extend(process_pdf(pdf_url, categorie))

    return records


def crawl() -> list[dict]:
    all_records = []
    seen_urls = set()

    for categorie, urls in SEED_PAGES.items():
        for url in urls:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            if any(domain in url for domain in EXCLUDE_DOMAINS):
                continue
            records = process_page(url, categorie)
            all_records.extend(records)
            print(f"  -> {len(records)} fiches extraites")

    return all_records


if __name__ == "__main__":
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    records = crawl()

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"\nTerminé : {len(records)} fiches sauvegardées dans {OUTPUT_PATH}")

    # Petit résumé par catégorie
    counts = {}
    for r in records:
        counts[r["categorie"]] = counts.get(r["categorie"], 0) + 1
    for cat, count in counts.items():
        print(f"  {cat} : {count} fiches")