"""
Détecte la langue parlée dans un fichier audio (français ou arabe).

Réutilise le même modèle que modules/speech_to_text (voir
modules/speech_to_text/model.py), et n'analyse qu'un court échantillon --
plus rapide qu'une transcription complète.

Limite connue : Whisper distingue les langues (ISO), pas les dialectes. Un
appel en arabe tunisien sera détecté comme "ar" (arabe), sans distinction
avec l'arabe standard.
"""

from __future__ import annotations

from pathlib import Path

from faster_whisper import decode_audio

from modules.speech_to_text.config import SAMPLE_RATE
from modules.speech_to_text.model import get_model


def detect_language(audio_path: Path | str) -> dict:
    """Retourne {"language": str, "probability": float}."""
    model = get_model()
    audio = decode_audio(str(audio_path), sampling_rate=SAMPLE_RATE)
    language, probability, _all_probabilities = model.detect_language(audio)

    return {"language": language, "probability": probability}
