# Module de reconnaissance vocale (Speech-to-Text)

Statut : fonctionnel (transcription fichier audio -> texte).

Rôle : transformer la voix de l'appelant (français ou arabe tunisien) en
texte, à transmettre au module de compréhension/RAG.

Basé sur `faster-whisper` (modèle `medium`), 100% local et gratuit.
Partage son modèle avec `modules/language_detection/` pour éviter de le
charger deux fois en mémoire (voir `model.py`).

## Utilisation

```python
from modules.speech_to_text.transcribe import transcribe

result = transcribe("chemin/vers/audio.wav")
# {"text": "...", "language": "fr", "language_probability": 0.98}
```

## Test manuel

```
python -m tests.test_stt_pipeline
```

Enregistre quelques secondes au micro et affiche la transcription.

## Limite connue

La qualité de transcription est nettement meilleure en français qu'en
arabe tunisien (dialecte peu représenté dans les données d'entraînement de
Whisper). À réévaluer une fois testé en conditions réelles.
