/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Direction : "Signal" -- fond quasi-noir tech, rouge signal
        // (clin d'oeil au rouge ESPRIT sans copier son identite visuelle),
        // cyan electrique pour tout ce qui est "voix/IA en action".
        ink: {
          950: "#08090c",
          900: "#0e1015",
          800: "#15181f",
          700: "#1e222b",
          600: "#2a2f3a",
          500: "#3a4150",
        },
        signal: {
          50: "#fff1f0",
          400: "#ff5c52",
          500: "#f0342a",
          600: "#d21f18",
          700: "#a8180f",
        },
        volt: {
          300: "#8ff0ff",
          400: "#4fd9f2",
          500: "#22c1e0",
          600: "#0e9dbd",
        },
        mist: {
          50: "#f7f8fa",
          100: "#eceef2",
          300: "#b9c0cc",
          400: "#8a92a3",
          500: "#666f82",
        },
      },
      fontFamily: {
        display: ["Sora", "system-ui", "sans-serif"],
        body: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(240,52,42,0.15), 0 8px 40px -8px rgba(240,52,42,0.35)",
        "glow-volt": "0 0 0 1px rgba(34,193,224,0.2), 0 8px 40px -8px rgba(34,193,224,0.35)",
        glass: "0 1px 0 0 rgba(255,255,255,0.06) inset, 0 8px 32px -12px rgba(0,0,0,0.6)",
      },
      backgroundImage: {
        "grid-fade":
          "linear-gradient(to bottom, transparent, rgba(8,9,12,1)), repeating-linear-gradient(0deg, rgba(255,255,255,0.035) 0px, rgba(255,255,255,0.035) 1px, transparent 1px, transparent 40px), repeating-linear-gradient(90deg, rgba(255,255,255,0.035) 0px, rgba(255,255,255,0.035) 1px, transparent 1px, transparent 40px)",
        "radial-glow":
          "radial-gradient(60% 50% at 50% 0%, rgba(240,52,42,0.16) 0%, rgba(8,9,12,0) 70%)",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        float: "float 6s ease-in-out infinite",
      },
      keyframes: {
        float: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-8px)" },
        },
      },
    },
  },
  plugins: [],
};
