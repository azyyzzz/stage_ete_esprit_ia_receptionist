"""
Synthèse vocale : transforme une réponse texte du RAG en audio, via Piper
(local, gratuit, aucune clé API).
"""

from __future__ import annotations

import re
import wave
from functools import lru_cache
from pathlib import Path

from piper import PiperVoice
from piper.config import SynthesisConfig

from modules.text_to_speech.config import (
    SPEECH_LENGTH_SCALE,
    VOICE_MODEL_PATH,
    VOICE_MODEL_PATH_AR,
)

# Plage Unicode de l'alphabet arabe (couvre aussi les chiffres/ponctuation
# arabes) -- sert a detecter le script DOMINANT du texte a synthetiser, pas
# une vraie detection de langue : les appelants d'ESPRIT n'utilisent que le
# francais, l'arabe, ou un melange des deux (voir modules/rag/generator.py),
# donc distinguer les deux scripts suffit a choisir la bonne voix.
_ARABIC_CHAR_RE = re.compile(r"[؀-ۿ]")
_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)


def _is_mostly_arabic(text: str) -> bool:
    letters = _LETTER_RE.findall(text)
    if not letters:
        return False
    arabic_count = sum(1 for ch in letters if _ARABIC_CHAR_RE.match(ch))
    return arabic_count / len(letters) > 0.5


@lru_cache(maxsize=1)
def _get_voice_fr() -> PiperVoice:
    return PiperVoice.load(VOICE_MODEL_PATH)


@lru_cache(maxsize=1)
def _get_voice_ar() -> PiperVoice:
    return PiperVoice.load(VOICE_MODEL_PATH_AR)


def synthesize_to_wav(text: str, output_path: Path) -> Path:
    """Génère un fichier .wav à partir du texte fourni et renvoie son chemin.

    Choisit automatiquement la voix francaise ou arabe selon le script
    dominant du texte -- avant ce choix, un texte en arabe etait toujours lu
    avec la voix francaise (aucune erreur technique, mais un son
    incomprehensible, une voix francaise prononcant phonetiquement de
    l'arabe). Voix arabe = arabe standard jordanien (aucune voix tunisienne
    disponible chez Piper, voir README.md)."""
    voice = _get_voice_ar() if _is_mostly_arabic(text) else _get_voice_fr()
    syn_config = SynthesisConfig(length_scale=SPEECH_LENGTH_SCALE)
    with wave.open(str(output_path), "wb") as wav_file:
        voice.synthesize_wav(text, wav_file, syn_config=syn_config)
    return output_path
