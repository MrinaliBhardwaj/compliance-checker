"use client";
// Sign in / sign up.
//
// Rework notes:
//  • Client-side validation matching the server's actual rules (password ≥ 8
//    chars, per the signup schema), shown on blur rather than as a server
//    round-trip failure.
//  • Errors are specific: a wrong password and an unreachable API are different
//    problems and now read differently.
//  • The left panel states what the product does and what it refuses to do —
//    the human-confirmed, deterministic-source-of-truth contract is the reason
//    a regulated firm would trust it, so it belongs on the front door.
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, login, signup } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { IconCheck, IconShield } from "@/components/icons";
import { Field, Note, Spinner } from "@/components/ui";

type Mode = "login" | "signup";

interface Form {
  email: string; password: string; organization_name: string; entity_legal_name: string;
}
type FieldName = keyof Form;

export default function AuthPage() {
  const router = useRouter();
  const { principal, loading, refresh } = useAuth();
  const [mode, setMode] = useState<Mode>("signup");
  const [form, setForm] = useState<Form>({
    email: "", password: "", organization_name: "", entity_legal_name: "",
  });
  const [touched, setTouched] = useState<Partial<Record<FieldName, boolean>>>({});
  const [submitted, setSubmitted] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!loading && principal) router.replace("/dashboard");
  }, [loading, principal, router]);

  const errors: Partial<Record<FieldName, string>> = {};
  if (!form.email.trim()) errors.email = "Enter your work email.";
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) errors.email = "That doesn’t look like a valid email address.";
  if (!form.password) errors.password = "Enter your password.";
  else if (mode === "signup" && form.password.length < 8) {
    errors.password = "Use at least 8 characters.";
  }
  if (mode === "signup") {
    if (!form.organization_name.trim()) errors.organization_name = "Name the organisation this workspace belongs to.";
    if (!form.entity_legal_name.trim()) errors.entity_legal_name = "Enter the registered legal name of the NBFC.";
  }

  const show = (f: FieldName) => (touched[f] || submitted ? errors[f] ?? null : null);
  const set = (f: FieldName, v: string) => setForm((s) => ({ ...s, [f]: v }));
  const blur = (f: FieldName) => setTouched((t) => ({ ...t, [f]: true }));

  const submit = async () => {
    setSubmitted(true);
    setErr(null);
    if (Object.keys(errors).length > 0) return;
    setBusy(true);
    try {
      const res = mode === "signup"
        ? await signup({
            email: form.email.trim(), password: form.password,
            organization_name: form.organization_name.trim(),
            entity_legal_name: form.entity_legal_name.trim(),
          })
        : await login({ email: form.email.trim(), password: form.password });
      // The session itself is an httpOnly cookie set by the server; we only
      // remember which entity to open.
      localStorage.setItem("regis_entity", res.entity_id);
      await refresh();
      router.push(mode === "signup" ? "/onboarding" : "/dashboard");
    } catch (e) {
      setErr(explain(e, mode));
    } finally {
      setBusy(false);
    }
  };

  const switchMode = (m: Mode) => {
    setMode(m); setErr(null); setSubmitted(false); setTouched({});
  };

  return (
    <main className="auth-page">
      <aside className="auth-aside">
        <div>
          <div className="brand" style={{ fontSize: 15 }}>
            <span className="brand-mark" aria-hidden="true">R</span> Regis
          </div>
          <h1 style={{ fontSize: 27, letterSpacing: "-.022em", marginTop: 44, maxWidth: "16ch", lineHeight: 1.2 }}>
            A defensible compliance calendar for Indian NBFCs.
          </h1>
          <p className="muted" style={{ marginTop: 14, fontSize: 13.5, maxWidth: "44ch", lineHeight: 1.6 }}>
            Answer a short profile questionnaire and get every obligation you owe —
            dated, owned, evidenced and audit-ready — instead of a spreadsheet nobody
            trusts by March.
          </p>
        </div>

        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 14 }}>
          {[
            ["Deterministic, not guessed",
              "Applicability and due dates come from a rules engine locked behind regression tests. AI only assists — it never sets a status."],
            ["Human-confirmed by design",
              "Every AI suggestion is proposed for your confirmation, and unverified library entries are labelled provisional wherever they appear."],
            ["Built for inspection",
              "Maker-checker approval on every filing and an append-only audit trail, so you can show an inspector who did what, when and why."],
          ].map(([title, body]) => (
            <li key={title} className="row" style={{ alignItems: "flex-start", gap: 10 }}>
              <span style={{ color: "var(--good)", marginTop: 2, flex: "none" }}>
                <IconCheck size={14} />
              </span>
              <span>
                <b style={{ fontSize: 12.5 }}>{title}</b>
                <div className="micro muted" style={{ marginTop: 2, maxWidth: "46ch" }}>{body}</div>
              </span>
            </li>
          ))}
        </ul>

        <div className="row micro faint" style={{ gap: 6 }}>
          <IconShield size={13} /> Sessions are httpOnly cookies · tenant-isolated at the database
        </div>
      </aside>

      <section className="auth-main">
        <div className="auth-form">
          <div className="segmented" style={{ marginBottom: 20 }} role="group" aria-label="Sign in or create an account">
            <button aria-pressed={mode === "signup"} onClick={() => switchMode("signup")}>Create account</button>
            <button aria-pressed={mode === "login"} onClick={() => switchMode("login")}>Log in</button>
          </div>

          <h2 style={{ fontSize: 19 }}>
            {mode === "signup" ? "Set up your workspace" : "Welcome back"}
          </h2>
          <p className="muted micro" style={{ marginTop: 4, marginBottom: 18 }}>
            {mode === "signup"
              ? "You’ll be the compliance admin for this organisation and can invite your team afterwards."
              : "Sign in to your organisation’s compliance workspace."}
          </p>

          <form className="stack-sm" onSubmit={(e) => { e.preventDefault(); void submit(); }} noValidate>
            {mode === "signup" && (
              <>
                <Field label="Organisation name" required error={show("organization_name")}
                  hint="How your company is referred to internally.">
                  {(p) => (
                    <input className="input" value={form.organization_name} autoComplete="organization"
                      onChange={(e) => set("organization_name", e.target.value)}
                      onBlur={() => blur("organization_name")} {...p} />
                  )}
                </Field>
                <Field label="Entity legal name" required error={show("entity_legal_name")}
                  hint="Exactly as registered with the RBI — it appears on every report you export.">
                  {(p) => (
                    <input className="input" value={form.entity_legal_name}
                      onChange={(e) => set("entity_legal_name", e.target.value)}
                      onBlur={() => blur("entity_legal_name")} {...p} />
                  )}
                </Field>
              </>
            )}

            <Field label="Work email" required error={show("email")}>
              {(p) => (
                <input className="input" type="email" value={form.email} autoComplete="email"
                  onChange={(e) => set("email", e.target.value)} onBlur={() => blur("email")} {...p} />
              )}
            </Field>

            <Field label="Password" required error={show("password")}
              hint={mode === "signup" ? "At least 8 characters." : undefined}>
              {(p) => (
                <input className="input" type="password" value={form.password}
                  autoComplete={mode === "signup" ? "new-password" : "current-password"}
                  onChange={(e) => set("password", e.target.value)} onBlur={() => blur("password")} {...p} />
              )}
            </Field>

            {err && <Note tone="crit">{err}</Note>}

            <button className="btn primary lg block" type="submit" disabled={busy} style={{ marginTop: 6 }}>
              {busy ? <Spinner onDark /> : null}
              {mode === "signup" ? "Create account" : "Log in"}
            </button>
          </form>

          <p className="micro faint" style={{ marginTop: 16, textAlign: "center" }}>
            {mode === "signup" ? (
              <>Already have an account?{" "}
                <button className="btn ghost sm" onClick={() => switchMode("login")}>Log in</button></>
            ) : (
              <>New here?{" "}
                <button className="btn ghost sm" onClick={() => switchMode("signup")}>Create an account</button></>
            )}
          </p>
        </div>
      </section>
    </main>
  );
}

/** Server failures translated into something a user can act on. */
function explain(e: unknown, mode: Mode): string {
  if (e instanceof ApiError) {
    if (e.status === 401 || e.status === 403) {
      return mode === "login"
        ? "That email and password don’t match an active account. If you were recently removed from a workspace, your access has been revoked."
        : e.message;
    }
    if (e.status === 409) return e.message || "An account with that email already exists — log in instead.";
    if (e.status === 422) return e.message || "Some details weren’t accepted. Check the fields above.";
    if (e.status === 429) return "Too many attempts. Wait a minute before trying again.";
    if (e.status === 0) return "Couldn’t reach the server. Check your connection and try again.";
    if (e.status >= 500) return "The server had a problem. This is usually temporary — try again in a moment.";
    return e.message;
  }
  return e instanceof Error ? e.message : "Something went wrong.";
}
