"""
Route qui expose la synthèse vocale (modules/text_to_speech/) via HTTP.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from backend.schemas import SpeakRequest
from modules.text_to_speech.synthesize import synthesize_to_wav

router = APIRouter(prefix="/api", tags=["speech"])


@router.post("/speak")
def speak(request: SpeakRequest) -> FileResponse:
    """
    Reçoit un texte (typiquement la réponse renvoyée par `/api/ask` ou
    `/api/voice-ask`) et renvoie un fichier audio .wav de la voix générée.
    """
    tmp_path = Path(tempfile.mktemp(suffix=".wav"))
    synthesize_to_wav(request.text, tmp_path)
    return FileResponse(tmp_path, media_type="audio/wav", filename="reponse.wav")
