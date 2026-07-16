"""
Synthèse vocale : transforme une réponse texte du RAG en audio, via Piper
(local, gratuit, aucune clé API).
"""

from __future__ import annotations

import wave
from functools import lru_cache
from pathlib import Path

from piper import PiperVoice
from piper.config import SynthesisConfig

from modules.text_to_speech.config import SPEECH_LENGTH_SCALE, VOICE_MODEL_PATH


@lru_cache(maxsize=1)
def get_voice() -> PiperVoice:
    return PiperVoice.load(VOICE_MODEL_PATH)


def synthesize_to_wav(text: str, output_path: Path) -> Path:
    """Génère un fichier .wav à partir du texte fourni et renvoie son chemin."""
    voice = get_voice()
    syn_config = SynthesisConfig(length_scale=SPEECH_LENGTH_SCALE)
    with wave.open(str(output_path), "wb") as wav_file:
        voice.synthesize_wav(text, wav_file, syn_config=syn_config)
    return output_path
