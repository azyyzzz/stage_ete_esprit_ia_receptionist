"""
Schémas de requête/réponse de l'API (validation automatique par FastAPI).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, examples=["Quels sont les frais de scolarité ?"])


class Source(BaseModel):
    titre: str
    source: str
    score: float


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    used_fallback: bool
    needs_clarification: bool


class TranscribeResponse(BaseModel):
    language: str
    language_probability: float
    text: str


class SpeakRequest(BaseModel):
    text: str = Field(..., min_length=1, examples=["Bonjour, bienvenue à ESPRIT."])


class VoiceAskResponse(BaseModel):
    language: str
    language_probability: float
    question: str
    answer: str
    sources: list[Source]
    used_fallback: bool
    needs_clarification: bool
