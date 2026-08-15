"""
Route qui expose la détection de langue + reconnaissance vocale
(modules/language_detection/, modules/speech_to_text/) via HTTP.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile
from fastapi.responses import FileResponse

from backend.schemas import TranscribeResponse, VoiceAskResponse
from modules.language_detection.detect import detect_language
from modules.quality_log import append_live_result
from modules.rag.pipeline import answer_question
from modules.rag.translate import detect_text_language
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
def voice_ask(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    pending_question: str | None = Form(None),
) -> VoiceAskResponse:
    """
    Reçoit une question posée à l'oral (fichier audio) et renvoie la
    réponse générée par le RAG : enchaîne détection de langue, transcription
    (modules/speech_to_text/, modules/language_detection/) puis génération
    de réponse (modules/rag/), comme le ferait l'assistant téléphonique.

    `pending_question` : question d'origine mémorisée côté client (voir
    dashboard/src/components/VoiceDemo.tsx) quand le tour précédent s'est
    terminé par une demande de précision (needs_clarification=True) --
    combinée ici avec ce que l'appelant vient de dire, pour que le modèle
    reçoive le contexte complet ("frais d'inscription" + "Tunis") plutôt
    que juste sa réponse ("Tunis") seule, qui ne suffirait pas à retrouver
    la bonne information.
    """
    tmp_path = _save_upload_to_tmp(file)
    try:
        lang_result = detect_language(tmp_path)
        stt_result = transcribe(tmp_path, language=lang_result["language"])
    finally:
        tmp_path.unlink(missing_ok=True)

    question = stt_result["text"]
    combined_question = f"{pending_question} ({question})" if pending_question else question

    t0 = time.time()
    # allow_clarification=True : voir dashboard/src/components/VoiceDemo.tsx,
    # qui memorise la question d'origine et relance un tour vocal avec
    # `pending_question` quand le modele a demande une precision.
    rag_result = answer_question(combined_question, allow_clarification=True)
    elapsed = time.time() - t0

    # detect_text_language() (mots-cles sur le texte transcrit) donne une
    # distinction fusha/tounsi plus fine que detect_language() (audio,
    # fr/ar uniquement) -- voir modules/rag/translate.py. Ne journalise
    # PAS un tour de demande de precision (needs_clarification=True) --
    # voir backend/routers/rag.py pour la meme regle cote chat.
    if not rag_result["needs_clarification"]:
        background_tasks.add_task(
            append_live_result,
            question=combined_question,
            reponse=rag_result["answer"],
            langue=detect_text_language(combined_question),
            canal="vocal",
            temps_reponse_s=elapsed,
            score_principal=rag_result["sources"][0]["score"] if rag_result.get("sources") else None,
            used_fallback=rag_result["used_fallback"],
            sources=rag_result.get("sources", []),
        )

    return VoiceAskResponse(
        language=lang_result["language"],
        language_probability=lang_result["probability"],
        question=combined_question,
        answer=rag_result["answer"],
        sources=rag_result["sources"],
        used_fallback=rag_result["used_fallback"],
        needs_clarification=rag_result["needs_clarification"],
    )


@router.post("/converse")
def converse(background_tasks: BackgroundTasks, file: UploadFile = File(...)) -> FileResponse:
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

    question = stt_result["text"]
    t0 = time.time()
    rag_result = answer_question(question, allow_clarification=False)
    elapsed = time.time() - t0

    background_tasks.add_task(
        append_live_result,
        question=question,
        reponse=rag_result["answer"],
        langue=detect_text_language(question),
        canal="vocal",
        temps_reponse_s=elapsed,
        score_principal=rag_result["sources"][0]["score"] if rag_result.get("sources") else None,
        used_fallback=rag_result["used_fallback"],
        sources=rag_result.get("sources", []),
    )

    output_path = Path(tempfile.mktemp(suffix=".wav"))
    synthesize_to_wav(rag_result["answer"], output_path)

    return FileResponse(output_path, media_type="audio/wav", filename="reponse.wav")
