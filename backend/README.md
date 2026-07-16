# API REST (backend)

Statut : module RAG exposé, autres modules à venir au fur et à mesure.

Rôle : exposer les modules (RAG, STT, TTS, détection de langue) via une API
REST, pour que le dashboard et le système de téléphonie puissent
communiquer avec eux.

## Lancement

```
uvicorn backend.main:app --reload
```

Puis ouvrir http://127.0.0.1:8000/docs : documentation interactive qui
permet de tester les endpoints directement dans le navigateur, sans écrire
de code.

## Endpoints actuels

- `GET /api/health` — vérifie que l'API répond.
- `POST /api/ask` — pose une question au pipeline RAG (`modules/rag/`).
  Corps de la requête : `{"question": "..."}`.
- `POST /api/transcribe` — envoie un fichier audio (wav, mp3, m4a...),
  renvoie la langue détectée et la transcription
  (`modules/language_detection/`, `modules/speech_to_text/`). Testable
  depuis `/docs` en uploadant un fichier, sans commande.
- `POST /api/voice-ask` — envoie un fichier audio contenant une question
  posée à l'oral, renvoie la réponse générée par le RAG (enchaîne
  transcription puis `modules/rag/`, comme le ferait l'assistant
  téléphonique). Testable depuis `/docs` en uploadant un fichier.
- `POST /api/speak` — envoie un texte (ex. la réponse de `/api/ask` ou
  `/api/voice-ask`), renvoie un fichier audio .wav de la voix générée
  (`modules/text_to_speech/`, français uniquement). Testable depuis `/docs`.
- `POST /api/converse` — cycle complet : envoie un fichier audio contenant
  une question à l'oral, renvoie directement la réponse du RAG synthétisée
  en audio .wav (transcription -> RAG -> TTS enchaînés). Testable depuis
  `/docs` en uploadant un fichier.

