"use client";

import { useEffect, useState } from "react";

export type ThemePreference = "light" | "dark" | "system";

const STORAGE_KEY = "videoqa-theme";

function resolvedTheme(preference: ThemePreference) {
  if (preference !== "system") return preference;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function useTheme() {
  const [preference, setPreferenceState] = useState<ThemePreference>("system");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY) as ThemePreference | null;
    const initial = saved === "light" || saved === "dark" || saved === "system" ? saved : "system";
    setPreferenceState(initial);
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.dataset.theme = resolvedTheme(preference);
      document.documentElement.style.colorScheme = resolvedTheme(preference);
    };
    apply();
    query.addEventListener("change", apply);
    return () => query.removeEventListener("change", apply);
  }, [mounted, preference]);

  const setPreference = (next: ThemePreference) => {
    window.localStorage.setItem(STORAGE_KEY, next);
    setPreferenceState(next);
  };

  return { preference, setPreference, mounted };
}
