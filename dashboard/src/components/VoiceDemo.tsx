import { useRef, useState } from "react";
import { voiceAsk, speak, type Source } from "../lib/api";
import { useRecorder } from "../lib/useRecorder";

type Phase = "idle" | "recording" | "thinking" | "speaking" | "done" | "error";

interface Result {
  question: string;
  answer: string;
  sources: Source[];
  language: string;
}

export default function VoiceDemo() {
  const { status, error: micError, start, stop } = useRecorder();
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);

  async function handleToggleRecord() {
    if (status === "recording") {
      setPhase("thinking");
      const blob = await stop();
      if (!blob) {
        setPhase("error");
        setError("Aucun son capté — réessaie en parlant plus près du micro.");
        return;
      }
      await handleAudio(blob);
    } else {
      setResult(null);
      setError(null);
      await start();
      setPhase("recording");
    }
  }

  async function handleAudio(blob: Blob) {
    try {
      const res = await voiceAsk(blob);
      setResult({ question: res.question, answer: res.answer, sources: res.sources, language: res.language });

      setPhase("speaking");
      const wav = await speak(res.answer);
      const url = URL.createObjectURL(wav);
      if (audioRef.current) {
        audioRef.current.src = url;
        await audioRef.current.play().catch(() => undefined);
      }
      setPhase("done");
    } catch (err) {
      setPhase("error");
      setError(err instanceof Error ? err.message : "Erreur inconnue — vérifie que le backend tourne sur le port 8000.");
    }
  }

  const isRecording = status === "recording";
  const isBusy = phase === "thinking" || phase === "speaking";

  return (
    <div className="glass-panel flex h-[560px] flex-col items-center justify-center gap-8 px-8 py-10 text-center">
      <div>
        <h3 className="font-display text-lg font-semibold text-white">Parle à l'assistant</h3>
        <p className="mt-1 text-sm text-mist-400">Français ou arabe tunisien — appuie, parle, relâche.</p>
      </div>

      <button
        onClick={handleToggleRecord}
        disabled={status === "requesting" || isBusy}
        className={`relative flex h-32 w-32 items-center justify-center rounded-full transition-all duration-300 disabled:opacity-60 ${
          isRecording ? "bg-signal-500 shadow-glow" : "bg-white/[0.06] border border-white/10 hover:border-volt-400/40 hover:bg-white/[0.09]"
        }`}
      >
        {isRecording && <span className="absolute inset-0 animate-ping rounded-full bg-signal-500/40" />}
        <MicIcon active={isRecording} />
      </button>

      <p className="font-mono text-xs uppercase tracking-widest text-mist-500">
        {status === "requesting" && "Autorisation micro…"}
        {isRecording && "Enregistrement — clique pour arrêter"}
        {phase === "thinking" && "Transcription + réflexion…"}
        {phase === "speaking" && "Synthèse de la voix…"}
        {phase === "idle" && !result && "Appuie pour parler"}
        {phase === "done" && "Terminé — réappuie pour recommencer"}
        {phase === "error" && "Erreur"}
      </p>

      {(micError || error) && (
        <p className="max-w-sm rounded-xl border border-signal-500/30 bg-signal-500/10 px-4 py-2 text-sm text-signal-400">
          {micError ?? error}
        </p>
      )}

      {result && (
        <div className="w-full max-w-md space-y-3 text-left">
          <div className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
            <p className="font-mono text-[11px] uppercase tracking-wide text-mist-500">
              Compris ({result.language === "fr" ? "français" : result.language})
            </p>
            <p className="mt-1 text-sm text-mist-200">{result.question}</p>
          </div>
          <div className="rounded-xl border border-volt-500/20 bg-volt-500/[0.06] px-4 py-3">
            <p className="font-mono text-[11px] uppercase tracking-wide text-volt-400">Réponse</p>
            <p className="mt-1 text-sm text-mist-100">{result.answer}</p>
          </div>
        </div>
      )}

      <audio ref={audioRef} className="hidden" controls />
    </div>
  );
}

function MicIcon({ active }: { active: boolean }) {
  return (
    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" className={active ? "text-white" : "text-mist-200"}>
      <rect x="9" y="2" width="6" height="12" rx="3" fill="currentColor" />
      <path d="M5 11a7 7 0 0 0 14 0" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M12 18v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
