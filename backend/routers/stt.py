"""
Route qui expose la détection de langue + reconnaissance vocale
(modules/language_detection/, modules/speech_to_text/) via HTTP.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse

from backend.schemas import TranscribeResponse, VoiceAskResponse
from modules.language_detection.detect import detect_language
from modules.rag.pipeline import answer_question
from modules.speech_to_text.transcribe import transcribe
from modules.text_to_speech.synthesize import synthesize_to_wav

router = APIRouter(prefix="/api", tags=["speech"])


def _save_upload_to_tmp(file: UploadFile) -> Path:
    suffix = Path(file.filename or "audio").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file.file.read())
        return Path(tmp.name)


@router.post("/transcribe", response_model=TranscribeResponse)
def transcribe_audio(file: UploadFile = File(...)) -> TranscribeResponse:
    """
    Reçoit un fichier audio (wav, mp3, m4a...), détecte sa langue et le
    transcrit en texte.
    """
    tmp_path = _save_upload_to_tmp(file)
    try:
        lang_result = detect_language(tmp_path)
        stt_result = transcribe(tmp_path, language=lang_result["language"])
    finally:
        tmp_path.unlink(missing_ok=True)

    return TranscribeResponse(
        language=lang_result["language"],
        language_probability=lang_result["probability"],
        text=stt_result["text"],
    )


@router.post("/voice-ask", response_model=VoiceAskResponse)
def voice_ask(file: UploadFile = File(...)) -> VoiceAskResponse:
    """
    Reçoit une question posée à l'oral (fichier audio) et renvoie la
    réponse générée par le RAG : enchaîne détection de langue, transcription
    (modules/speech_to_text/, modules/language_detection/) puis génération
    de réponse (modules/rag/), comme le ferait l'assistant téléphonique.
    """
    tmp_path = _save_upload_to_tmp(file)
    try:
        lang_result = detect_language(tmp_path)
        stt_result = transcribe(tmp_path, language=lang_result["language"])
    finally:
        tmp_path.unlink(missing_ok=True)

    question = stt_result["text"]
    rag_result = answer_question(question, allow_clarification=False)

    return VoiceAskResponse(
        language=lang_result["language"],
        language_probability=lang_result["probability"],
        question=question,
        answer=rag_result["answer"],
        sources=rag_result["sources"],
        used_fallback=rag_result["used_fallback"],
        needs_clarification=rag_result["needs_clarification"],
    )


@router.post("/converse")
def converse(file: UploadFile = File(...)) -> FileResponse:
    """
    Cycle complet de l'assistant vocal : reçoit une question posée à l'oral
    (fichier audio), la transcrit, génère la réponse via le RAG, puis
    renvoie cette réponse synthétisée en audio (.wav) -- l'appelant entend
    directement la réponse, sans passer par du texte intermédiaire.

    Ne demande jamais de précision sur le programme (allow_clarification=
    False) : contrairement à /api/voice-ask, ce canal est un aller-retour
    unique -- l'appelant n'a pas moyen de répondre à une question de
    clarification.
    """
    tmp_path = _save_upload_to_tmp(file)
    try:
        lang_result = detect_language(tmp_path)
        stt_result = transcribe(tmp_path, language=lang_result["language"])
    finally:
        tmp_path.unlink(missing_ok=True)

    rag_result = answer_question(stt_result["text"], allow_clarification=False)

    output_path = Path(tempfile.mktemp(suffix=".wav"))
    synthesize_to_wav(rag_result["answer"], output_path)

    return FileResponse(output_path, media_type="audio/wav", filename="reponse.wav")
