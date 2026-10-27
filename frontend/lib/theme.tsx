"use client";
// Theme: light (default) / dark / system.
//
// Light is the default because compliance work happens in bright offices and
// output gets screenshotted into board packs. Dark is a real second theme, not
// an inverted afterthought. The resolved value is written to <html data-theme>
// by an inline script in layout.tsx so there is no flash on first paint.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type ThemePref = "light" | "dark" | "system";
const KEY = "regis_theme";

interface ThemeApi { pref: ThemePref; resolved: "light" | "dark"; setPref: (p: ThemePref) => void; }
const Ctx = createContext<ThemeApi>({ pref: "system", resolved: "light", setPref: () => {} });

function systemIsDark(): boolean {
  return typeof window !== "undefined"
    && window.matchMedia?.("(prefers-color-scheme: dark)").matches;
}

function apply(pref: ThemePref): "light" | "dark" {
  const resolved = pref === "system" ? (systemIsDark() ? "dark" : "light") : pref;
  document.documentElement.setAttribute("data-theme", resolved);
  return resolved;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [pref, setPrefState] = useState<ThemePref>("system");
  const [resolved, setResolved] = useState<"light" | "dark">("light");

  useEffect(() => {
    const stored = (localStorage.getItem(KEY) as ThemePref | null) ?? "system";
    setPrefState(stored);
    setResolved(apply(stored));
  }, []);

  // Follow the OS while the user is on "system".
  useEffect(() => {
    if (pref !== "system" || typeof window === "undefined") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setResolved(apply("system"));
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [pref]);

  const setPref = useCallback((p: ThemePref) => {
    setPrefState(p);
    localStorage.setItem(KEY, p);
    setResolved(apply(p));
  }, []);

  const value = useMemo(() => ({ pref, resolved, setPref }), [pref, resolved, setPref]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useTheme = () => useContext(Ctx);

/** Runs before hydration to stamp data-theme and avoid a light/dark flash. */
export const THEME_BOOT_SCRIPT = `(function(){try{var p=localStorage.getItem('${KEY}')||'system';var d=p==='dark'||(p==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.setAttribute('data-theme',d?'dark':'light');}catch(e){document.documentElement.setAttribute('data-theme','light');}})();`;
