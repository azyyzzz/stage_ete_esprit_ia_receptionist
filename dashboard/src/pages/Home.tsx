import { useState } from "react";
import ChatDemo from "../components/ChatDemo";
import VoiceDemo from "../components/VoiceDemo";

type Mode = "texte" | "voix";

export default function Home() {
  const [mode, setMode] = useState<Mode>("texte");

  return (
    <div className="mx-auto max-w-6xl px-6 pb-24 pt-16">
      <section className="mx-auto max-w-2xl text-center">
        <span className="pill mx-auto">
          <span className="h-1.5 w-1.5 rounded-full bg-volt-400" />
          100% local · aucune donnée envoyée à un tiers
        </span>
        <h1 className="mt-6 font-display text-4xl font-extrabold leading-[1.1] text-white sm:text-5xl">
          L'accueil d'ESPRIT,
          <br />
          <span className="bg-gradient-to-r from-signal-400 to-volt-400 bg-clip-text text-transparent">disponible à toute heure.</span>
        </h1>
        <p className="mt-5 text-lg text-mist-400">
          Un assistant vocal qui répond aux questions des étudiants et des parents — admissions, scolarité, programmes —
          en français ou en arabe tunisien. Teste-le comme le ferait un futur étudiant qui appelle.
        </p>
      </section>

      <section className="mt-12">
        <div className="mx-auto mb-6 flex w-fit rounded-full border border-white/10 bg-white/[0.03] p-1">
          {(["texte", "voix"] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`rounded-full px-5 py-2 text-sm font-medium capitalize transition-colors ${
                mode === m ? "bg-signal-500 text-white" : "text-mist-400 hover:text-mist-100"
              }`}
            >
              {m === "texte" ? "💬 Texte" : "🎙️ Voix"}
            </button>
          ))}
        </div>

        <div className="mx-auto max-w-2xl">{mode === "texte" ? <ChatDemo /> : <VoiceDemo />}</div>
      </section>

      <section className="mx-auto mt-20 grid max-w-4xl gap-4 sm:grid-cols-3">
        <FeatureCard
          title="RAG sur mesure"
          text="Recherche sémantique dans la base de connaissances ESPRIT (admissions, règlements, programmes) avant de générer chaque réponse."
        />
        <FeatureCard title="Bilingue" text="Comprend le français et l'arabe tunisien (dialecte) — détection automatique de la langue parlée." />
        <FeatureCard title="Cycle vocal complet" text="Transcription → recherche → réponse → synthèse vocale, entièrement en local, sans API externe payante." />
      </section>
    </div>
  );
}

function FeatureCard({ title, text }: { title: string; text: string }) {
  return (
    <div className="glass-panel p-5">
      <h3 className="font-display text-sm font-semibold text-white">{title}</h3>
      <p className="mt-1.5 text-sm text-mist-400">{text}</p>
    </div>
  );
}
