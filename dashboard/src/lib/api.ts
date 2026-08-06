// Client pour l'API REST du backend principal (backend/, port 8000) --
// types alignes sur backend/schemas.py. Toutes les routes sont sous /api,
// voir backend/routers/{rag,stt,tts}.py.

import { BACKEND_URL } from "./config";

export interface Source {
  titre: string;
  source: string;
  score: number;
}

export interface AskResponse {
  answer: string;
  sources: Source[];
  used_fallback: boolean;
  needs_clarification: boolean;
}

export interface VoiceAskResponse extends AskResponse {
  language: string;
  language_probability: number;
  question: string;
}

async function assertOk(res: Response): Promise<Response> {
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${detail ? ` — ${detail}` : ""}`);
  }
  return res;
}

/** POST /api/ask -- question texte, reponse texte du RAG. */
export async function ask(question: string): Promise<AskResponse> {
  const res = await fetch(`${BACKEND_URL}/api/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  await assertOk(res);
  return res.json();
}

/** POST /api/voice-ask -- question a l'oral (blob audio), reponse texte
 * (transcription + reponse du RAG), pas d'audio en retour. */
export async function voiceAsk(audio: Blob): Promise<VoiceAskResponse> {
  const form = new FormData();
  form.append("file", audio, "question.webm");
  const res = await fetch(`${BACKEND_URL}/api/voice-ask`, { method: "POST", body: form });
  await assertOk(res);
  return res.json();
}

/** POST /api/converse -- cycle complet voix-a-voix : audio en entree,
 * audio (.wav) en sortie directement, sans etape texte intermediaire. */
export async function converse(audio: Blob): Promise<Blob> {
  const form = new FormData();
  form.append("file", audio, "question.webm");
  const res = await fetch(`${BACKEND_URL}/api/converse`, { method: "POST", body: form });
  await assertOk(res);
  return res.blob();
}

/** POST /api/speak -- synthetise un texte en audio (.wav). */
export async function speak(text: string): Promise<Blob> {
  const res = await fetch(`${BACKEND_URL}/api/speak`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  await assertOk(res);
  return res.blob();
}

/** GET /api/health -- utilise pour l'indicateur d'etat en nav. */
export async function healthCheck(baseUrl: string): Promise<boolean> {
  try {
    const res = await fetch(`${baseUrl}/api/health`, { signal: AbortSignal.timeout(4000) });
    return res.ok;
  } catch {
    return false;
  }
}
