"""
Transcrit un fichier audio en texte.
"""

from __future__ import annotations

from pathlib import Path

from modules.speech_to_text.config import INITIAL_PROMPT
from modules.speech_to_text.model import get_model


def transcribe(audio_path: Path | str, language: str | None = None) -> dict:
    """Retourne {"text": str, "language": str, "language_probability": float}.

    `language` : force Whisper a decoder dans cette langue plutot que de
    re-detecter la sienne independamment (Whisper detecte alors parmi ~99
    langues, sans la restriction fr/ar appliquee par
    modules.language_detection.detect_language -- passer explicitement le
    resultat de cet appel evite que les deux etapes se contredisent, voir
    backend/routers/stt.py)."""
    model = get_model()
    segments, info = model.transcribe(str(audio_path), language=language, initial_prompt=INITIAL_PROMPT)
    text = " ".join(segment.text.strip() for segment in segments)

    return {
        "text": text.strip(),
        "language": info.language,
        "language_probability": info.language_probability,
    }
