/** Fond decoratif partage par toutes les pages : grille tres subtile +
 * lueur radiale rouge en haut, coherent avec le systeme de design "Signal"
 * (voir tailwind.config.js). Purement visuel, aria-hidden. */
export default function GlowBackground() {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden" aria-hidden="true">
      <div className="absolute inset-0 bg-radial-glow" />
      <div className="absolute inset-0 bg-grid-fade opacity-60" />
      <div className="absolute -top-24 right-[-10%] h-[420px] w-[420px] rounded-full bg-volt-500/10 blur-[120px]" />
      <div className="absolute top-1/3 left-[-15%] h-[380px] w-[380px] rounded-full bg-signal-500/10 blur-[130px]" />
    </div>
  );
}
