"use client";
// Auth + session context. Resolves the JWT to a Principal via /auth/me on mount,
// exposes role-aware helpers, and powers route guarding + role-aware rendering.
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { type Capability, type Principal, type Role, can, clearToken, getToken, me } from "@/lib/api";

interface AuthState {
  principal: Principal | null;
  loading: boolean;
  entityId: string | null;
  setEntityId: (id: string) => void;
  refresh: () => Promise<void>;
  logout: () => void;
  can: (cap: Capability) => boolean;
  role: Role | undefined;
}

const Ctx = createContext<AuthState | null>(null);
const ENTITY_KEY = "regis_entity";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [principal, setPrincipal] = useState<Principal | null>(null);
  const [loading, setLoading] = useState(true);
  const [entityId, setEntityIdState] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!getToken()) { setPrincipal(null); setLoading(false); return; }
    setLoading(true);
    try {
      const p = await me();
      setPrincipal(p);
      const stored = typeof window !== "undefined" ? localStorage.getItem(ENTITY_KEY) : null;
      const valid = p.entities.find((e) => e.id === stored)?.id ?? p.entities[0]?.id ?? null;
      setEntityIdState(valid);
    } catch {
      clearToken();
      setPrincipal(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const setEntityId = useCallback((id: string) => {
    setEntityIdState(id);
    if (typeof window !== "undefined") localStorage.setItem(ENTITY_KEY, id);
  }, []);

  const logout = useCallback(() => {
    clearToken();
    if (typeof window !== "undefined") localStorage.removeItem(ENTITY_KEY);
    setPrincipal(null);
    router.push("/");
  }, [router]);

  const value: AuthState = {
    principal, loading, entityId, setEntityId, refresh, logout,
    role: principal?.role,
    can: (cap) => can(principal?.role, cap),
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth must be used within AuthProvider");
  return v;
}
