# extraction_app -- Ingestion multi-source vers la base de connaissances

Appli web separee (dossier independant, ne modifie rien dans `backend/`,
`modules/` ou `data/scripts/`) qui permet d'ajouter des fiches a la base de
connaissances ESPRIT a partir d'un PDF, d'un Word (.docx), d'un Excel,
d'une image ou d'une URL, avec deux garde-fous obligatoires avant toute
sauvegarde : filtrage de pertinence et verification de similarite
semantique contre la base existante.

## Installation

Depuis la racine du projet (meme environnement virtuel que le reste) :

```bash
pip install -r requirements.txt
```

**Important -- OCR (extraction d'images) :** `pytesseract` est un simple
wrapper Python, il ne fonctionne pas sans le moteur **Tesseract OCR**
installe separement comme binaire systeme :
- Windows : installeur sur https://github.com/UB-Mannheim/tesseract/wiki,
  puis verifier que `tesseract.exe` est dans le PATH (ou renseigner
  `pytesseract.pytesseract.tesseract_cmd` dans
  `extraction_app/services/image_extractor.py` si besoin).
- Sans ce binaire, toute extraction d'image echouera avec une erreur claire
  (pas de plantage silencieux).

## Lancement

```bash
uvicorn extraction_app.main:app --reload --port 8001
```

Interface : http://127.0.0.1:8001/ (le backend principal du projet reste
sur le port 8000, inchange, les deux peuvent tourner en parallele).

Au tout premier lancement, un compte unique `admin` est cree avec un mot de
passe genere aleatoirement, **affiche une seule fois dans la console** --
note-le immediatement. Pour le regenerer, supprime
`extraction_app/data/config_local.json` et relance le serveur.

## Utilisation

1. Se connecter sur `/login`.
2. Sur la page d'accueil : choisir le type de source (PDF, Word, Excel,
   image, URL), une categorie, puis "Extraire".
3. Le resultat (fiches ajoutees / rejetees / erreurs) s'affiche
   immediatement.
4. La page `/history` liste toutes les extractions passees (manuelles et
   planifiees), avec le detail des doublons detectes.

## Extraction PDF -- programmes d'étude (paniers/UE, matières, ECTS)

Avant les stratégies génériques (article / page), un PDF uploadé est d'abord
testé contre la détection de programme d'étude (tableau UE/panier +
matières + heures/charge + période + ECTS ou Workload/Credits en anglais)
-- réutilise la même logique déjà validée par
`data/scripts/extract_programmes_etude.py` (voir le registre de
validation). Si détecté, une fiche est créée par (classe, panier),
listant ses matières avec heures/période/ECTS ; sinon le PDF retombe sur
l'extraction article/page classique. Catégorie dédiée : `Programme
d'étude`.

## Extraction Word (.docx)

Regroupe le contenu par section (dernier titre en gras rencontre dans le
document), pas par question individuelle -- une fiche par sujet complet
remonte mieux en recherche semantique qu'une fiche par mini-question
isolee. Detecte les paires question/reponse (question = paragraphe finissant
par « ? ») a l'interieur de chaque section. Logique reprise de
`data/scripts/extract_admission_docx.py` (`services/docx_extractor.py`).

## Ou vont les nouvelles fiches -- point d'attention important

Une extraction (upload manuel, scraping planifie) n'ecrit **jamais**
directement dans la base : les fiches candidates sont deposees en attente
sur `/a-valider`, et un admin doit cliquer **Approuver** fiche par fiche
(voir `services/kb_merge.py::queue_for_validation`/`approve_fiche`).

Seule une fiche **approuvee** est ecrite -- et elle l'est alors directement
dans `data/processed/site_esprit_clean.json` (celui que le RAG ingere
reellement via `modules/rag/ingest.py`), les deux garde-fous (pertinence +
dedup semantique) ayant deja ete verifies au moment de l'approbation.
`site_esprit.json` (fichier "brut" historique) est mis a jour en miroir
pour rester coherent avec les autres scripts du projet, mais n'est plus
la source de verite pour la dedup.

Un `python -m modules.rag.ingest` reste necessaire apres une session de
validation pour que le contenu approuve devienne cherchable par
l'assistant (reconstruction de l'index vectoriel ChromaDB, jamais fait
automatiquement par extraction_app).

## Planificateur

Un job mensuel (1er du mois, 03h00, `extraction_app/scheduler.py`) rejoue
automatiquement l'extraction pour toutes les URLs deja soumises via
l'interface (registre dans `extraction_app/data/url_sources.json`). Un
second job mensuel (1er du mois, 04h00) scrape les options de
specialisation ESPRIT Tunis. Les sources PDF/Excel/image ne sont jamais
replanifiees (le fichier original n'est pas conserve durablement).

## Limites assumees (a lire avant de faire confiance aux resultats)

- **Filtrage de pertinence** (`services/relevance_filter.py`) : simple
  correspondance de mots-cles (liste dans `config.py`, `RELEVANCE_KEYWORDS`),
  insensible aux accents/casse. Peut laisser passer du contenu hors-sujet
  s'il contient un mot-cle isole, ou rejeter du contenu pertinent mal
  formule qui n'utilise aucun des mots-cles prevus. Ce n'est pas une
  comprehension du sens, juste un filtre grossier.
- **Verification semantique** (`services/semantic_dedup.py`) : compare le
  contenu via les MEMES embeddings multilingues que le RAG
  (`modules/rag/embeddings.py`, `paraphrase-multilingual-mpnet-base-v2`) +
  similarite cosinus -- comparaison par le sens, pas par simple chevauchement
  de mots (contrairement a l'ancienne version TF-IDF). Seuil actuel :
  `SIMILARITY_THRESHOLD = 0.92` dans `config.py`, calibre empiriquement sur
  la base reelle (des paires de fiches sans rapport peuvent deja depasser
  0.8 en similarite d'embedding) -- a reajuster si trop de faux positifs
  (fiches legitimes rejetees) ou faux negatifs (doublons non detectes) sont
  constates en usage reel.
- **Performance de la dedup semantique** : les embeddings de la base
  existante sont recalcules a chaque extraction (le modele tourne
  directement dans le process `extraction_app`, contrairement a la
  reindexation ChromaDB qui est isolee en sous-processus). Sans probleme a
  l'echelle actuelle (~800 fiches), mais si la base grossit a plusieurs
  milliers de fiches, cela ralentira sensiblement. Piste d'optimisation non
  implementee ici : pre-calculer et mettre en cache les vecteurs de la base
  existante plutot que de les recalculer a chaque appel.
- **Scraping web generique** (`services/web_extractor.py`) : base sur
  `requests` + BeautifulSoup, qui ne peut ni executer de JavaScript ni
  contourner un blocage anti-bot. Si un site cible charge son contenu
  dynamiquement ou bloque les requetes automatisees, l'appli ne sauvegarde
  **aucune fiche vide ou trompeuse** -- elle affiche explicitement :
  *"Ce site n'a pas pu etre scrape completement, son contenu est peut-etre
  charge dynamiquement."* Seul le domaine `esprit.tn` beneficie d'une
  extraction FAQ-accordeon dediee ; tout autre site passe par l'extraction
  generique par sections h2/h3.
- **OCR (images)** : si le texte reconnu est trop court ou contient trop de
  caracteres non reconnus, la fiche n'est **pas** fusionnee automatiquement
  -- elle est mise de cote dans `extraction_app/data/a_verifier.json` pour
  verification manuelle, et signalee comme telle dans l'historique.
- **Authentification** : compte unique, session en memoire cote serveur
  (perdue si le serveur redemarre -- il suffit de se reconnecter). Pas
  concu pour un usage multi-utilisateur ni pour une exposition publique
  sur Internet -- outil interne uniquement.

## Schema des fiches (strict)

```json
{"id": "...", "categorie": "...", "titre": "...", "contenu": "...", "source": "..."}
```
Aucun champ supplementaire. Identique au schema utilise par le reste du
pipeline (`data/scripts/`) et par `site_esprit.json`/`site_esprit_clean.json`.

## Structure

```
extraction_app/
  main.py                 # app FastAPI + lifespan (scheduler)
  config.py                # seuils, mots-cles, chemins -- a ajuster ici
  auth.py, bootstrap_credentials.py
  scheduler.py
  services/
    relevance_filter.py    # garde-fou 1
    semantic_dedup.py       # garde-fou 2
    pdf_extractor.py, docx_extractor.py, excel_extractor.py, image_extractor.py, web_extractor.py
    kb_merge.py              # orchestration + journal d'historique
  routers/extraction.py, history.py
  templates/, static/
  data/                     # historique, registre URLs, items a verifier, identifiants (local, gitignore)
  uploads/                  # fichiers temporaires uploades (gitignore)
```
