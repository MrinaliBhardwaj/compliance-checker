"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { login, setToken, signup } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Spinner } from "@/components/ui";

export default function AuthPage() {
  const router = useRouter();
  const { principal, loading, refresh } = useAuth();
  const [mode, setMode] = useState<"login" | "signup">("signup");
  const [form, setForm] = useState({
    email: "", password: "", organization_name: "", entity_legal_name: "",
  });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // already signed in -> skip the login screen
  useEffect(() => { if (!loading && principal) router.replace("/dashboard"); }, [loading, principal, router]);

  const submit = async () => {
    setErr(null); setBusy(true);
    try {
      const res = mode === "signup"
        ? await signup(form)
        : await login({ email: form.email, password: form.password });
      setToken(res.access_token);
      localStorage.setItem("regis_entity", res.entity_id);
      await refresh();
      router.push(mode === "signup" ? "/onboarding" : "/dashboard");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main style={{ maxWidth: 430, margin: "9vh auto", padding: 24 }}>
      <h1>Regis</h1>
      <p className="muted">A live NBFC compliance calendar in under 30 minutes.</p>
      <div className="card stack" style={{ marginTop: 16 }}>
        {mode === "signup" && (
          <>
            <Field label="Organization name" v={form.organization_name}
              on={(v) => setForm({ ...form, organization_name: v })} />
            <Field label="Entity legal name" v={form.entity_legal_name}
              on={(v) => setForm({ ...form, entity_legal_name: v })} />
          </>
        )}
        <Field label="Work email" v={form.email} on={(v) => setForm({ ...form, email: v })} />
        <Field label="Password" type="password" v={form.password}
          on={(v) => setForm({ ...form, password: v })}
          onEnter={submit} />
        {err && <div className="banner err">{err}</div>}
        <button className="btn primary" onClick={submit} disabled={busy}
          style={{ justifyContent: "center" }}>
          {busy ? <Spinner /> : mode === "signup" ? "Create account" : "Log in"}
        </button>
        <button className="btn ghost" style={{ justifyContent: "center" }}
          onClick={() => { setErr(null); setMode(mode === "signup" ? "login" : "signup"); }}>
          {mode === "signup" ? "Have an account? Log in" : "New here? Sign up"}
        </button>
      </div>
    </main>
  );
}

function Field({ label, v, on, type = "text", onEnter }:
  { label: string; v: string; on: (v: string) => void; type?: string; onEnter?: () => void }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input className="input" type={type} value={v} onChange={(e) => on(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && onEnter?.()} />
    </label>
  );
}
