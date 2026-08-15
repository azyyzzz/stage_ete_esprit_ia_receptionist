"""
Configuration centrale de extraction_app.

Chemins vers la base de connaissances (partagee avec le reste du projet,
data/processed/) et parametres ajustables du pipeline d'extraction.
"""

from __future__ import annotations

from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = APP_ROOT.parent

# -----------------------------------------------------------------------
# Base de connaissances. Une fiche n'atteint l'un ou l'autre de ces
# fichiers QUE via kb_merge.merge_candidates() -- appele uniquement apres
# approbation explicite d'un admin sur /a-valider (voir services/kb_merge.py
# ::approve_fiche/approve_batch) : les deux garde-fous (pertinence + dedup
# semantique) sont deja passes a ce moment-la, donc la fiche est ecrite
# directement dans CLEAN_KB_PATH (celui que le RAG ingere reellement via
# modules/rag/ingest.py, voir modules/rag/config.py::KNOWLEDGE_BASE_PATH)
# -- pas seulement dans le fichier "brut" de staging, qui reste ecrit en
# parallele pour rester coherent avec les autres scripts du projet
# (data/scripts/merge_programmes_etude.py, scrape_esprit_tunis_options.py)
# qui ecrivent aussi dans les deux. Un `python -m modules.rag.ingest` reste
# necessaire pour que le contenu approuve devienne cherchable par
# l'assistant (reconstruction de l'index vectoriel, pas fait ici).
# -----------------------------------------------------------------------
KB_PATH = PROJECT_ROOT / "data" / "processed" / "site_esprit.json"
CLEAN_KB_PATH = PROJECT_ROOT / "data" / "processed" / "site_esprit_clean.json"

# -----------------------------------------------------------------------
# Donnees propres a extraction_app (journal, registre des sources web,
# items a verifier manuellement, identifiants). Ne touchent jamais au
# schema des fiches de la base de connaissances.
# -----------------------------------------------------------------------
DATA_DIR = APP_ROOT / "data"
HISTORIQUE_PATH = DATA_DIR / "historique.json"
URL_SOURCES_PATH = DATA_DIR / "url_sources.json"
A_VERIFIER_PATH = DATA_DIR / "a_verifier.json"
CONFIG_LOCAL_PATH = DATA_DIR / "config_local.json"

# File d'attente des lots issus d'un scraping NON supervise (ex. scraping
# mensuel planifie des options ESPRIT Tunis, voir scheduler.py) -- distinct
# de A_VERIFIER_PATH (qualite OCR douteuse) : ici le contenu est fiable,
# mais la politique du projet exige une validation humaine explicite avant
# toute ecriture dans la base pour les sources sans supervision directe.
# Un lot n'est fusionne dans site_esprit.json (via merge_candidates, memes
# garde-fous que toutes les autres sources) que si l'admin clique
# "Approuver" sur /a-valider -- voir services/kb_merge.py.
A_VALIDER_PATH = DATA_DIR / "a_valider.json"

# Resultats du test qualite + journal du trafic reel (voir /qualite) --
# chemin defini une seule fois dans modules/quality_log.py (partage avec
# `backend`, qui y ecrit le trafic reel sans dependre de extraction_app),
# re-expose ici pour ne pas casser le code existant qui l'importe depuis
# ce module de config.
from modules.quality_log import QUALITY_LOG_PATH as QUALITY_TEST_RESULTS_PATH  # noqa: E402

UPLOADS_DIR = APP_ROOT / "uploads"

# -----------------------------------------------------------------------
# Cache-busting pour static/style.css : le navigateur peut mettre en cache
# le CSS agressivement (pas de Cache-Control explicite envoye par
# StaticFiles) et ne pas detecter une modification sans rechargement forme.
# En suffixant le lien vers le CSS par ?v=<horodatage du fichier> (voir
# templates/base.html, login.html), l'URL change des que le fichier change
# -> le navigateur le retelecharge automatiquement, sans jamais avoir a
# faire de Ctrl+F5 manuel.
# -----------------------------------------------------------------------
def _compute_static_version() -> str:
    style_path = APP_ROOT / "static" / "style.css"
    return str(int(style_path.stat().st_mtime)) if style_path.exists() else "0"


STATIC_VERSION = _compute_static_version()

# -----------------------------------------------------------------------
# Seuil de similarite semantique (embeddings multilingues + cosinus, voir
# services/semantic_dedup.py) au-dessus duquel une fiche candidate est
# consideree comme deja presente dans la base et donc rejetee. Volontairement
# isole ici, en haut du fichier, pour rester facile a re-calibrer sans devoir
# fouiller le code du service.
#
# Calibre empiriquement sur la base reelle (site_esprit_clean.json, ~780
# fiches) : des paires de fiches SANS AUCUN rapport atteignent deja jusqu'a
# ~0.85 de similarite d'embedding (le sujet commun "ESPRIT" suffit a faire
# monter le score), alors qu'une meme fiche re-scrapee avec du bruit de
# mise en forme (espaces, ponctuation) ou legerement reformulee reste
# au-dessus de 0.99. 0.92 laisse une marge large des deux cotes.
# -----------------------------------------------------------------------
SIMILARITY_THRESHOLD = 0.92

# -----------------------------------------------------------------------
# Filtrage de pertinence : une fiche candidate doit contenir au moins un
# mot-cle d'un des domaines couverts par l'assistant ESPRIT, sinon elle
# est rejetee avant meme la verification semantique.
# -----------------------------------------------------------------------
RELEVANCE_KEYWORDS: dict[str, list[str]] = {
    "admissions": ["admission", "inscription", "candidature", "concours", "bac", "dossier"],
    "scolarite": ["scolarite", "cours", "semestre", "credit", "cursus", "diplome", "note"],
    "reglements": ["reglement", "discipline", "sanction", "assiduite", "regime"],
    "examens": ["examen", "rattrapage", "redoublement", "controle", "session", "evaluation"],
    "calendrier": ["calendrier", "rentree", "vacances", "planning", "date limite", "echeance"],
    "paiements": ["paiement", "frais", "tarif", "tranche", "facture", "reduction", "bourse", "tnd", "dinar"],
    "vie_etudiante": ["vie etudiante", "club", "association", "campus", "logement", "activite"],
    "stages": ["stage", "entreprise", "pfe", "alternance", "stagiaire"],
    "programmes": ["programme", "filiere", "specialite", "master", "ingenieur", "mba", "bachelor"],
    "contacts_services": ["contact", "service", "bureau", "email", "telephone", "adresse", "responsable"],
}

# -----------------------------------------------------------------------
# Divers
# -----------------------------------------------------------------------
PORT = 8001
SESSION_COOKIE_NAME = "extraction_app_session"
MIN_OCR_CHARS = 40
MIN_SCRAPE_CHARS = 100
MAX_CHARS = 2000  # taille max d'une fiche avant decoupage (memes regles que reextract_reglements.py)
