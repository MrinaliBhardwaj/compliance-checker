"use client";
// Auth + session context. Resolves the JWT to a Principal via /auth/me on mount,
// exposes role-aware helpers, and powers route guarding + role-aware rendering.
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { type Capability, type Principal, type Role, can, logout as logoutApi, me } from "@/lib/api";

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
  const queryClient = useQueryClient();
  const [principal, setPrincipal] = useState<Principal | null>(null);
  const [loading, setLoading] = useState(true);
  const [entityId, setEntityIdState] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    // Session lives in an httpOnly cookie we can't read — ask the server who we are.
    setLoading(true);
    try {
      const p = await me();
      setPrincipal(p);
      const stored = typeof window !== "undefined" ? localStorage.getItem(ENTITY_KEY) : null;
      const valid = p.entities.find((e) => e.id === stored)?.id ?? p.entities[0]?.id ?? null;
      setEntityIdState(valid);
    } catch {
      setPrincipal(null);  // 401 -> not signed in
      queryClient.clear();  // drop any previous user's cached data
    } finally {
      setLoading(false);
    }
  }, [queryClient]);

  useEffect(() => { void refresh(); }, [refresh]);

  const setEntityId = useCallback((id: string) => {
    setEntityIdState(id);
    if (typeof window !== "undefined") localStorage.setItem(ENTITY_KEY, id);
  }, []);

  const logout = useCallback(async () => {
    try { await logoutApi(); } catch { /* clear locally regardless */ }
    if (typeof window !== "undefined") localStorage.removeItem(ENTITY_KEY);
    setPrincipal(null);
    // Cached queries belong to the user who just left; the next one to sign in
    // in this tab must not see them, even while their own data refetches.
    queryClient.clear();
    router.push("/");
  }, [router, queryClient]);

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
