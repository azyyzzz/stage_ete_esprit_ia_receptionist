import { useEffect, useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import Logo from "./Logo";
import GlowBackground from "./GlowBackground";
import { healthCheck } from "../lib/api";
import { BACKEND_URL } from "../lib/config";

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `text-sm font-medium transition-colors ${isActive ? "text-white" : "text-mist-400 hover:text-mist-100"}`;

function StatusDot() {
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    const check = () => healthCheck(BACKEND_URL).then((ok) => !cancelled && setOnline(ok));
    check();
    const id = setInterval(check, 15000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const label = online === null ? "Vérification…" : online ? "Backend en ligne" : "Backend hors ligne";
  const color = online === null ? "bg-mist-500" : online ? "bg-volt-400" : "bg-signal-500";

  return (
    <span className="pill" title={label}>
      <span className={`h-1.5 w-1.5 rounded-full ${color} ${online ? "animate-pulse-slow" : ""}`} />
      {label}
    </span>
  );
}

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="relative min-h-screen flex flex-col">
      <GlowBackground />

      <header className="sticky top-0 z-20 border-b border-white/[0.06] bg-ink-950/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <NavLink to="/">
            <Logo />
          </NavLink>
          <nav className="flex items-center gap-6">
            <NavLink to="/" end className={navLinkClass}>
              Démo
            </NavLink>
            <NavLink to="/admin" className={navLinkClass}>
              Espace admin
            </NavLink>
            <StatusDot />
          </nav>
        </div>
      </header>

      <main className="flex-1">{children}</main>

      <footer className="border-t border-white/[0.06] py-8">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-6 text-xs text-mist-500 sm:flex-row">
          <p>ESPRIT AI Receptionist — projet de stage, assistant vocal 100% local (aucune donnée envoyée à un tiers).</p>
          <p className="font-mono">backend :8000 · extraction_app :8001</p>
        </div>
      </footer>
    </div>
  );
}
