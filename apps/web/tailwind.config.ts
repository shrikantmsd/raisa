import type { Config } from "tailwindcss";

// Design tokens are defined as CSS variables in app/globals.css (one set
// per theme, switched via `[data-theme]` on <html>) so Tailwind classes
// like `bg-surface` resolve to whichever theme is active without a
// second Tailwind build.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: "var(--color-surface)",
        canvas: "var(--color-canvas)",
        accent: "var(--color-accent)",
        "accent-secondary": "var(--color-accent-secondary)",
        ink: "var(--color-ink)",
      },
      fontFamily: {
        theme: ["var(--font-family)", "sans-serif"],
      },
      borderRadius: {
        pill: "999px",
      },
    },
  },
  plugins: [],
};
export default config;
