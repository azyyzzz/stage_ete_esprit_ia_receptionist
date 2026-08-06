import { EXTRACTION_APP_URL } from "../lib/config";

/**
 * Point d'entree admin : ne recree PAS l'authentification -- se contente
 * de renvoyer vers extraction_app (port 8001), qui a deja son propre
 * systeme complet (compte unique, session cookie HttpOnly, voir
 * extraction_app/auth.py). Une simple navigation suffit : le cookie de
 * session d'extraction_app est gere nativement par le navigateur des que
 * l'utilisateur s'authentifie la-bas, ce frontend n'a besoin de rien savoir
 * de plus.
 */
export default function Admin() {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center px-6 py-20 text-center">
      <span className="pill">Espace réservé à l'équipe</span>
      <h1 className="mt-5 font-display text-3xl font-bold text-white">Administration de la base de connaissances</h1>
      <p className="mt-4 text-mist-400">
        Ajout de nouvelles sources (PDF, Word, Excel, image, URL), scraping planifié, et validation manuelle de chaque
        fiche avant qu'elle n'entre dans la base — tout se passe dans <span className="font-mono text-mist-300">extraction_app</span>,
        avec sa propre authentification.
      </p>

      <a href={EXTRACTION_APP_URL} className="btn-primary mt-8 shadow-glow-volt">
        Ouvrir l'espace admin
        <ArrowIcon />
      </a>

      <div className="mt-10 grid w-full gap-3 text-left sm:grid-cols-3">
        <MiniLink href={`${EXTRACTION_APP_URL}/`} label="Extraire" desc="Ajouter une nouvelle source" />
        <MiniLink href={`${EXTRACTION_APP_URL}/a-valider`} label="À valider" desc="Approuver ou rejeter fiche par fiche" />
        <MiniLink href={`${EXTRACTION_APP_URL}/history`} label="Historique" desc="Journal de toutes les extractions" />
      </div>

      <p className="mt-10 font-mono text-xs text-mist-500">{EXTRACTION_APP_URL}</p>
    </div>
  );
}

function MiniLink({ href, label, desc }: { href: string; label: string; desc: string }) {
  return (
    <a href={href} className="glass-panel block p-4 transition-colors hover:border-white/20">
      <p className="font-display text-sm font-semibold text-white">{label}</p>
      <p className="mt-1 text-xs text-mist-400">{desc}</p>
    </a>
  );
}

function ArrowIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
