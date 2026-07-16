# ESPRIT AI Receptionist

Assistant vocal intelligent pour répondre automatiquement aux appels
téléphoniques des étudiants et parents de l'école ESPRIT, en français et en
arabe tunisien (dialecte).

## Structure du projet

```
data/                    Collecte et préparation de la base de connaissances
  raw_data/               Documents bruts (PDF, pages HTML scrapées)
  processed/               Base de connaissances nettoyée + paires Q/R
  scripts/                  Scripts de scraping, extraction PDF, nettoyage

modules/
  rag/                     Module de génération de réponses (RAG) -- voir plus bas
  language_detection/      Détection français / arabe -- voir plus bas
  speech_to_text/          Reconnaissance vocale -- voir plus bas
  text_to_speech/           Synthèse vocale -- voir plus bas

backend/                  API REST reliant les modules -- voir plus bas
dashboard/                Interface CRUD documents + statistiques -- à venir
docker/                   Conteneurisation des services -- à venir
tests/                    Scripts de test manuels
```

Toutes les solutions techniques utilisées sont **gratuites** (aucune clé
API payante) : ChromaDB, sentence-transformers et Ollama tournent
entièrement en local.

## Module RAG : installation et utilisation

### 1. Dépendances Python

```
pip install -r requirements.txt
```

### 2. Ollama (LLM local, gratuit)

Installer Ollama (https://ollama.com), puis télécharger le modèle utilisé
par le module RAG :

```
ollama pull qwen2.5:7b-instruct
```

Ollama doit être lancé (l'application tourne en arrière-plan après
installation) pour que le module RAG puisse générer des réponses.

### 3. Indexer la base de connaissances

À lancer une première fois, puis à chaque mise à jour de
`data/processed/site_esprit_clean.json` :

```
python -m modules.rag.ingest
```

### 4. Tester le pipeline

```
python -m tests.test_rag_pipeline
```

Pose une question (en français ou en arabe tunisien) et affiche la réponse
générée ainsi que les sources utilisées, ou le message de redirection vers
un service humain si aucune information pertinente n'est trouvée dans la
base de connaissances.

## API REST

Une fois le module RAG indexé (étape 3 ci-dessus) et Ollama lancé, l'API
peut être démarrée :

```
uvicorn backend.main:app --reload
```

Documentation interactive et testable dans le navigateur :
http://127.0.0.1:8000/docs. Voir [backend/README.md](backend/README.md)
pour le détail des endpoints.

## Détection de langue + reconnaissance vocale

Basés sur `faster-whisper` (modèle `medium`), 100% local et gratuit. Les
deux modules partagent le même modèle en mémoire (voir
[modules/speech_to_text/model.py](modules/speech_to_text/model.py)).

Test manuel (nécessite un micro) :

```
python -m tests.test_stt_pipeline
```

Enregistre quelques secondes au micro, détecte la langue puis transcrit.
Voir [modules/speech_to_text/README.md](modules/speech_to_text/README.md)
et
[modules/language_detection/README.md](modules/language_detection/README.md)
pour le détail et les limites connues (qualité plus faible sur le dialecte
tunisien que sur le français).

## Synthèse vocale (TTS)

Basée sur [Piper](https://github.com/OHF-Voice/piper1-gpl) (voix française
`fr_FR-siwis-medium`), 100% local et gratuit. Voir
[modules/text_to_speech/README.md](modules/text_to_speech/README.md) pour
l'installation de la voix et les limites connues (français uniquement).

Cycle vocal complet (question à l'oral -> réponse RAG -> audio de la
réponse) via l'endpoint `POST /api/converse` -- voir
[backend/README.md](backend/README.md).
