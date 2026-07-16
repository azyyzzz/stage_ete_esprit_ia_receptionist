"""
Chargement unique du modèle faster-whisper, partagé par le module de
transcription (speech_to_text) et le module de détection de langue
(language_detection), pour éviter de charger le modèle deux fois en
mémoire.
"""

from __future__ import annotations

from functools import lru_cache

from faster_whisper import WhisperModel

from modules.speech_to_text.config import COMPUTE_TYPE, DEVICE, MODEL_SIZE


@lru_cache(maxsize=1)
def get_model() -> WhisperModel:
    return WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
