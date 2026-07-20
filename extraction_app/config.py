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
# Base de connaissances -- extraction_app ecrit UNIQUEMENT dans le fichier
# brut. site_esprit_clean.json (celui que le RAG ingere) n'est jamais
# modifie ici : voir README.md, section "Rappel important".
# -----------------------------------------------------------------------
KB_PATH = PROJECT_ROOT / "data" / "processed" / "site_esprit.json"

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

UPLOADS_DIR = APP_ROOT / "uploads"

# -----------------------------------------------------------------------
# Seuil de similarite semantique (TF-IDF + cosinus) au-dessus duquel une
# fiche candidate est consideree comme deja presente dans la base et donc
# rejetee. Volontairement isole ici, en haut du fichier, pour rester
# facile a re-calibrer sans devoir fouiller le code du service.
# -----------------------------------------------------------------------
SIMILARITY_THRESHOLD = 0.85

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
