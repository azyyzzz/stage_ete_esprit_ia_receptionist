"""
Extraction PDF -- adapte de data/scripts/reextract_reglements.py.

Strategie a TROIS niveaux :
1. Programme d'etude (paniers/UE, matieres, heures, periode, ECTS) -- voir
   services/programme_etude_extractor.py, qui reutilise la logique deja
   validee de data/scripts/extract_programmes_etude.py. Essaye en premier
   car sa detection est specifique (necessite un vrai tableau UE/ECTS) ;
   si rien n'est detecte, le PDF n'est probablement pas de ce type et on
   continue avec les niveaux suivants.
2. Si le PDF a une vraie structure "Article N : ..." (>= 2 occurrences),
   une fiche par article, avec retrait du sommaire et decoupage des
   articles trop longs.
3. Sinon (documents uploades arbitraires, sans structure reconnue), repli
   sur une fiche par page -- meme logique de secours que
   data/scripts/extract_local_documents_reglements.py. Si une page n'a
   AUCUN texte natif (PDF genere depuis une image/capture d'ecran, tableau
   scanne...), bascule sur l'OCR (page rendue en image, pytesseract) avec
   le meme controle qualite que services/image_extractor.py -- sans quoi
   ce type de page etait auparavant silencieusement ignore, sans aucun
   message explicatif pour l'admin (constate en usage reel : 0 fiche
   ajoutee, 0 rejetee, aucune erreur affichee).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pdfplumber

from extraction_app.config import MAX_CHARS, MIN_OCR_CHARS
from extraction_app.services.programme_etude_extractor import extract_programme_etude

ARTICLE_PATTERN = re.compile(r"(Article\s*\d+\s*:.*?)(?=Article\s*\d+\s*:|\Z)", re.DOTALL)
TITLE_FROM_ARTICLE = re.compile(r"(Article\s*\d+\s*:\s*[^\n]*)")
TOC_LINE_PATTERN = re.compile(r"^.*[.…]{5,}\s*\d+\s*$", re.MULTILINE)

# Controle qualite OCR -- partage avec services/image_extractor.py (qui
# importe _quality_ok d'ici plutot que de le dupliquer). Caracteres
# consideres "propres" : lettres (accentuees incluses), chiffres, espaces
# et ponctuation courante ; un OCR de mauvaise qualite produit beaucoup de
# symboles hors de cet ensemble.
_CLEAN_CHAR_PATTERN = re.compile(r"[a-zA-ZÀ-ÿ0-9\s.,;:!?()\-'\"%€]")
MIN_CLEAN_RATIO = 0.85


def _quality_ok(text: str) -> tuple[bool, str]:
    stripped = text.strip()
    if len(stripped) < MIN_OCR_CHARS:
        return False, f"texte reconnu trop court ({len(stripped)} caracteres, minimum {MIN_OCR_CHARS})"

    clean_chars = len(_CLEAN_CHAR_PATTERN.findall(stripped))
    ratio = clean_chars / len(stripped) if stripped else 0.0
    if ratio < MIN_CLEAN_RATIO:
        return False, f"trop de caracteres non reconnus ({ratio:.0%} de caracteres propres, minimum {MIN_CLEAN_RATIO:.0%})"

    return True, ""


# Emplacement standard de l'installeur Windows officiel (winget/UB-Mannheim) --
# repli si le binaire n'est pas trouve sur le PATH du process courant (ex.
# installe apres le demarrage du serveur, ou PATH systeme pas encore
# propage a ce process -- cas frequent juste apres une install winget, un
# nouveau process est necessaire pour le voir sans ce repli explicite).
_TESSERACT_DEFAULT_PATH = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")

# Pack de langue francaise (tessdata/fra.traineddata) : PAS installe par
# defaut par l'installeur Windows (seul l'anglais l'est). Stocke dans le
# projet plutot que dans le dossier d'installation Tesseract (qui exige des
# droits admin en ecriture) -- voir scripts/install_tesseract.ps1 pour le
# telechargement. Repertoire gitignore (fichier volumineux, retelechargeable).
_PROJECT_TESSDATA_DIR = Path(__file__).resolve().parents[2] / "tessdata"

_tesseract_configured = False


def _ensure_tesseract_configured() -> str | None:
    """Configure pytesseract pour trouver le binaire Tesseract (PATH, ou
    repli sur l'emplacement d'installation standard Windows) et le pack de
    langue francaise (tessdata/ du projet, si present). Renvoie le
    --tessdata-dir a passer en config si le pack local doit etre utilise,
    sinon None (le tessdata embarque avec Tesseract suffit). Ne fait rien
    si deja configure (execute une seule fois par process)."""
    global _tesseract_configured
    if not _tesseract_configured:
        import pytesseract

        if shutil.which("tesseract") is None and _TESSERACT_DEFAULT_PATH.exists():
            pytesseract.pytesseract.tesseract_cmd = str(_TESSERACT_DEFAULT_PATH)
        _tesseract_configured = True

    if (_PROJECT_TESSDATA_DIR / "fra.traineddata").exists():
        return str(_PROJECT_TESSDATA_DIR)
    return None


def _ocr_page(page: "pdfplumber.page.Page") -> str:
    """Rend une page PDF en image puis y applique l'OCR -- necessite le
    binaire systeme Tesseract (voir README.md) ; leve une exception
    explicite si absent, interceptee par l'appelant."""
    import pytesseract

    tessdata_dir = _ensure_tesseract_configured()
    # Pas de guillemets autour du chemin : pytesseract passe le config tel
    # quel a l'executable, sans interpretation shell -- des guillemets
    # litteraux dans l'argument font echouer l'ouverture du fichier.
    config = f"--tessdata-dir {tessdata_dir}" if tessdata_dir else ""
    image = page.to_image(resolution=200).original
    raw_text = pytesseract.image_to_string(image, lang="fra", config=config)
    return re.sub(r"\s+", " ", raw_text).strip()


def _slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    return text.strip("_")[:60]


def _extract_full_text(pdf_path: Path) -> str:
    with pdfplumber.open(str(pdf_path)) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def _strip_table_of_contents(full_text: str) -> str:
    matches = list(re.finditer(r"Article\s*1\s*:", full_text))
    if len(matches) >= 2:
        return full_text[matches[-1].start():]
    return full_text


def _strip_toc_lines(full_text: str) -> str:
    return TOC_LINE_PATTERN.sub("", full_text)


def _split_long_section(titre: str, contenu: str) -> list[dict]:
    if len(contenu) <= MAX_CHARS:
        return [{"titre": titre, "contenu": contenu}]

    sentences = re.split(r"(?<=[.;:])\s+", contenu)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) > MAX_CHARS:
            chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current.strip())

    return [
        {"titre": f"{titre} (partie {i}/{len(chunks)})", "contenu": chunk}
        for i, chunk in enumerate(chunks, start=1)
    ]


def _split_by_article(full_text: str) -> list[dict]:
    full_text = _strip_table_of_contents(full_text)
    full_text = _strip_toc_lines(full_text)
    matches = ARTICLE_PATTERN.findall(full_text)

    seen_titles: set[str] = set()
    sections: list[dict] = []
    for match in matches:
        content = re.sub(r"\s+", " ", match).strip()
        title_match = TITLE_FROM_ARTICLE.search(match)
        title = title_match.group(1).strip() if title_match else content[:60]
        title = re.sub(r"\s+", " ", title)
        if title in seen_titles:
            continue
        seen_titles.add(title)
        sections.extend(_split_long_section(title, content))
    return sections


def _split_by_page(pdf_path: Path, display_name: str) -> tuple[list[dict], list[str]]:
    """Renvoie (sections, avertissements). Une page sans texte natif (PDF
    genere depuis une image -- tableau/capture d'ecran, scan...) declenche
    un essai OCR ; si le resultat est vide ou de mauvaise qualite (meme
    seuils que services/image_extractor.py), la page est ignoree comme
    avant MAIS un avertissement explicite est ajoute (au lieu du silence
    total constate en usage reel), pour que l'admin comprenne pourquoi rien
    n'a ete extrait.

    display_name sert UNIQUEMENT au titre affiche (nom de fichier ORIGINAL,
    pas le chemin temporaire a nom aleatoire sous lequel l'upload est
    sauvegarde -- sinon le titre affiche sur /a-valider est illisible, voir
    id_slug dans extract_pdf)."""
    sections = []
    warnings: list[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            text = re.sub(r"\s+", " ", text)

            if text:
                sections.append({"titre": f"{display_name} - page {page_num}", "contenu": text})
                continue

            # Aucun texte natif -- probablement une page-image (scan,
            # capture, tableau exporte en graphique). Tente l'OCR avant
            # d'abandonner la page.
            try:
                ocr_text = _ocr_page(page)
            except Exception as exc:
                warnings.append(
                    f"page {page_num} : aucun texte natif et OCR indisponible ({exc}) "
                    f"-- Tesseract OCR est-il installe comme binaire systeme ? Voir README.md."
                )
                continue

            ok, reason = _quality_ok(ocr_text)
            if not ok:
                warnings.append(f"page {page_num} : aucun texte natif, OCR tente mais rejete ({reason}).")
                continue

            sections.append({"titre": f"{display_name} - page {page_num} (OCR)", "contenu": ocr_text})

    return sections, warnings


def extract_pdf(pdf_path: Path, categorie: str, source: str, id_slug: str | None = None) -> tuple[list[dict], list[str]]:
    """Retourne (fiches, avertissements). Une fiche est
    {id, categorie, titre, contenu, source} ; les avertissements expliquent
    les pages ignorees (ex. page-image sans OCR disponible) -- pour que
    l'admin comprenne pourquoi un fichier peut produire 0 fiche au lieu
    d'un echec silencieux.

    id_slug sert a construire des id stables et deterministes pour permettre
    la dedup par id (kb_merge.py) sur un re-upload du meme fichier -- a
    fournir a partir du nom de fichier ORIGINAL (pas du chemin temporaire,
    qui est aleatoire). A defaut, derive du nom du fichier temporaire."""
    programme_records = extract_programme_etude(pdf_path, source)
    if programme_records is not None:
        return programme_records, []

    full_text = _extract_full_text(pdf_path)
    sections = _split_by_article(full_text)
    warnings: list[str] = []
    if not sections:
        display_name = f"{id_slug}.pdf" if id_slug is not None else pdf_path.name
        sections, warnings = _split_by_page(pdf_path, display_name)

    slug = _slugify(id_slug if id_slug is not None else pdf_path.stem)
    records = []
    for i, section in enumerate(sections, start=1):
        if len(section["contenu"]) < 20:
            continue
        records.append(
            {
                "id": f"upload_pdf_{slug}_{i:03d}",
                "categorie": categorie,
                "titre": section["titre"],
                "contenu": section["contenu"],
                "source": source,
            }
        )
    return records, warnings
