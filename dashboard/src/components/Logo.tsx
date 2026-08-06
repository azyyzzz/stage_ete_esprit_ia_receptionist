interface LogoProps {
  className?: string;
}

/** Marque : un contour de bulle vocale traverse par une onde -- signal
 * rouge / volt cyan, les deux couleurs d'accent du systeme de design. */
export default function Logo({ className = "" }: LogoProps) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <svg width="30" height="30" viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <rect x="1" y="1" width="30" height="30" rx="9" className="fill-ink-800 stroke-white/10" />
        <path
          d="M8 20.5V11.5C8 10.1193 9.11929 9 10.5 9H21.5C22.8807 9 24 10.1193 24 11.5V17.5C24 18.8807 22.8807 20 21.5 20H14L10 23.5V20.5H8Z"
          className="fill-signal-500"
        />
        <path
          d="M11 15.5L13 13L15 16.5L17.5 11.5L19.5 15.5L21.5 14"
          stroke="white"
          strokeWidth="1.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="opacity-90"
        />
      </svg>
      <span className="font-display font-bold tracking-tight text-lg text-white">
        ESPRIT<span className="text-signal-500">.AI</span>
      </span>
    </span>
  );
}
