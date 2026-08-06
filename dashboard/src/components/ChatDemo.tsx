import { useRef, useState } from "react";
import { ask, type Source } from "../lib/api";

interface Turn {
  question: string;
  answer?: string;
  sources?: Source[];
  needsClarification?: boolean;
  usedFallback?: boolean;
  error?: string;
}

const SUGGESTIONS = [
  "Quels sont les frais de scolarité pour les étudiants tunisiens ?",
  "Quelles spécialités propose ESPRIT Tunis ?",
  "Comment se déroule la session de rattrapage ?",
];

export default function ChatDemo() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  async function send(question: string) {
    const q = question.trim();
    if (!q || loading) return;
    setInput("");
    setLoading(true);
    setTurns((prev) => [...prev, { question: q }]);

    try {
      const res = await ask(q);
      setTurns((prev) =>
        prev.map((t, i) =>
          i === prev.length - 1
            ? { ...t, answer: res.answer, sources: res.sources, needsClarification: res.needs_clarification, usedFallback: res.used_fallback }
            : t,
        ),
      );
    } catch (err) {
      setTurns((prev) =>
        prev.map((t, i) => (i === prev.length - 1 ? { ...t, error: err instanceof Error ? err.message : "Erreur inconnue" } : t)),
      );
    } finally {
      setLoading(false);
      requestAnimationFrame(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }));
    }
  }

  return (
    <div className="glass-panel flex h-[560px] flex-col overflow-hidden">
      <div className="flex-1 space-y-5 overflow-y-auto px-6 py-6">
        {turns.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <p className="text-mist-400">Pose une question comme le ferait un futur étudiant.</p>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => send(s)} className="pill hover:border-signal-500/40 hover:text-mist-100">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((t, i) => (
          <div key={i} className="space-y-3">
            <div className="flex justify-end">
              <p className="max-w-[80%] rounded-2xl rounded-tr-sm bg-white/[0.06] px-4 py-2.5 text-sm text-white">{t.question}</p>
            </div>
            <div className="flex justify-start">
              <div className="max-w-[85%] space-y-2">
                {t.error ? (
                  <p className="rounded-2xl rounded-tl-sm border border-signal-500/30 bg-signal-500/10 px-4 py-2.5 text-sm text-signal-400">
                    {t.error} — vérifie que le backend tourne sur le port 8000.
                  </p>
                ) : t.answer ? (
                  <>
                    <p className="rounded-2xl rounded-tl-sm bg-ink-800 px-4 py-2.5 text-sm leading-relaxed text-mist-100">{t.answer}</p>
                    {t.sources && t.sources.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 pl-1">
                        {t.sources.slice(0, 4).map((s, j) => (
                          <span key={j} className="pill font-mono text-[11px]" title={s.source}>
                            {s.titre || s.source}
                          </span>
                        ))}
                      </div>
                    )}
                  </>
                ) : (
                  <div className="flex items-center gap-1.5 rounded-2xl rounded-tl-sm bg-ink-800 px-4 py-3">
                    {[0, 1, 2].map((d) => (
                      <span key={d} className="h-1.5 w-1.5 animate-pulse-slow rounded-full bg-mist-400" style={{ animationDelay: `${d * 0.15}s` }} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="flex items-center gap-3 border-t border-white/[0.06] p-4"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Écris ta question ici…"
          className="flex-1 rounded-full border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white placeholder:text-mist-500 outline-none focus:border-signal-500/50"
        />
        <button type="submit" disabled={loading || !input.trim()} className="btn-primary px-5 py-2.5 text-sm">
          Envoyer
        </button>
      </form>
    </div>
  );
}
