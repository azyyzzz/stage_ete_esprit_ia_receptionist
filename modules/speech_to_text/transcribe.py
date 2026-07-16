"""
Transcrit un fichier audio en texte.
"""

from __future__ import annotations

from pathlib import Path

from modules.speech_to_text.config import INITIAL_PROMPT
from modules.speech_to_text.model import get_model


def transcribe(audio_path: Path | str) -> dict:
    """Retourne {"text": str, "language": str, "language_probability": float}."""
    model = get_model()
    segments, info = model.transcribe(str(audio_path), initial_prompt=INITIAL_PROMPT)
    text = " ".join(segment.text.strip() for segment in segments)

    return {
        "text": text.strip(),
        "language": info.language,
        "language_probability": info.language_probability,
    }
