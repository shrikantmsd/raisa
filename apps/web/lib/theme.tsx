"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type ThemeName = "office" | "genx" | "system";

const THEME_STORAGE_KEY = "raisa-synapse-theme-preference";

type ThemeContextValue = {
  theme: ThemeName;
  setTheme: (theme: ThemeName) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

function resolveDataTheme(theme: ThemeName): "office" | "genx" {
  if (theme === "system") {
    const prefersDark =
      typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches;
    // Layer 1 has no dark variant of either theme yet — "system" falls
    // back to Office, the default enterprise theme (spec §45: "Do not
    // infer themes from age or role" — same principle applies to
    // guessing a theme from OS dark-mode).
    return prefersDark ? "office" : "office";
  }
  return theme;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeName>("office");

  useEffect(() => {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY) as ThemeName | null;
    if (stored) setThemeState(stored);
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", resolveDataTheme(theme));
  }, [theme]);

  const setTheme = (next: ThemeName) => {
    setThemeState(next);
    window.localStorage.setItem(THEME_STORAGE_KEY, next);
    // Layer 1 scope note: persisting theme_preference to the User row via
    // PATCH /api/v1/users/{id} (so it follows the user across devices) is
    // a Users-API extension left for the next pass — see
    // docs/LAYER_1_FOUNDATION.md "Known limitations". This is a real gap,
    // not a stylistic choice: right now the preference is per-browser.
  };

  return <ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used inside <ThemeProvider>");
  return ctx;
}

const OPTIONS: { value: ThemeName; label: string }[] = [
  { value: "office", label: "RAISA Office" },
  { value: "genx", label: "RAISA GenX" },
  { value: "system", label: "System" },
];

/** Profile -> Appearance (spec §45). A plain <select> rather than a
 * styled dropdown component — Layer 1's shared component library
 * (Dropdown, Select, etc. from spec §41) is deferred; this proves the
 * theme-switching mechanism works without waiting on that library. */
export function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();
  return (
    <label className="flex items-center gap-2 text-sm">
      <span>Appearance</span>
      <select
        value={theme}
        onChange={(e) => setTheme(e.target.value as ThemeName)}
        className="rounded border border-black/10 bg-surface px-2 py-1"
      >
        {OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  );
}
