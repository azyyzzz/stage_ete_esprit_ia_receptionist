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
    """Retourne {"language": str, "probability": float}, RESTREINT a
    francais ou arabe -- un appelant d'ESPRIT n'utilise que l'une de ces
    deux langues, ou un melange des deux (dialecte tunisien), jamais une
    autre langue (voir modules/rag/generator.py).

    Whisper detecte nativement parmi ~99 langues : sur un echantillon court
    ou bruite, la langue avec le score global le plus eleve peut etre une
    langue totalement hors sujet plutot que fr/ar (constate en usage reel).
    On recupere donc les probabilites de TOUTES les langues et on ne
    compare que fr vs ar entre elles, en ignorant le reste."""
    model = get_model()
    audio = decode_audio(str(audio_path), sampling_rate=SAMPLE_RATE)
    _, _, all_probabilities = model.detect_language(audio)

    probs = dict(all_probabilities)
    prob_fr = probs.get("fr", 0.0)
    prob_ar = probs.get("ar", 0.0)

    if prob_fr >= prob_ar:
        return {"language": "fr", "probability": prob_fr}
    return {"language": "ar", "probability": prob_ar}
