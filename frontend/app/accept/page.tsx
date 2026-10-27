"use client";
// Invite acceptance (public route).
//
// Rework notes:
//  • The two cases the old copy conflated are now separate and stated up front:
//    a brand-new user is *setting* a password, an existing user is *proving*
//    theirs. Getting this wrong looks like a broken link.
//  • A missing or spent token gets a real explanation and a way forward instead
//    of a bare red banner.
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { ApiError, acceptInvite } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { IconCheck, IconLock, IconShield } from "@/components/icons";
import { Field, Note, Segmented, Spinner } from "@/components/ui";

export default function AcceptPage() {
  return (
    <Suspense fallback={null}>
      <Accept />
    </Suspense>
  );
}

type Who = "new" | "existing";

function Accept() {
  const params = useSearchParams();
  const router = useRouter();
  const { refresh } = useAuth();
  const token = params.get("token") ?? "";

  const [who, setWho] = useState<Who>("new");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const pwError = !password ? "Enter a password."
    : who === "new" && password.length < 8 ? "Use at least 8 characters."
    : null;

  const submit = async () => {
    setTouched(true);
    if (pwError) return;
    setErr(null); setBusy(true);
    try {
      const res = await acceptInvite(token, password, name.trim() || undefined);
      localStorage.setItem("regis_entity", res.entity_id); // session cookie set by the server
      await refresh();
      router.push("/dashboard");
    } catch (e) {
      setErr(explain(e));
    } finally { setBusy(false); }
  };

  if (!token) {
    return (
      <main className="auth-main" style={{ minHeight: "100dvh" }}>
        <div className="auth-form stack">
          <div className="brand" style={{ fontSize: 15 }}>
            <span className="brand-mark" aria-hidden="true">R</span> Regis
          </div>
          <Note tone="crit">
            <b>This link is missing its invite token.</b> Use the full link from your
            invitation email — copying only part of the URL will drop it.
          </Note>
          <a className="btn" href="/">Go to sign in</a>
        </div>
      </main>
    );
  }

  return (
    <main className="auth-page">
      <aside className="auth-aside">
        <div>
          <div className="brand" style={{ fontSize: 15 }}>
            <span className="brand-mark" aria-hidden="true">R</span> Regis
          </div>
          <h1 style={{ fontSize: 25, letterSpacing: "-.02em", marginTop: 40, maxWidth: "17ch", lineHeight: 1.22 }}>
            You’ve been invited to a compliance workspace.
          </h1>
          <p className="muted" style={{ marginTop: 14, fontSize: 13.5, maxWidth: "42ch", lineHeight: 1.6 }}>
            Your role decides what you can do — a preparer works the obligations assigned
            to them, a head approves them. You’ll see your role as soon as you’re in.
          </p>
        </div>
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 12 }}>
          {[
            "This link works once and then expires.",
            "Everything you do is recorded in an append-only audit trail.",
            "You only see obligations your role is entitled to.",
          ].map((t) => (
            <li key={t} className="row micro muted" style={{ alignItems: "flex-start", gap: 9 }}>
              <span style={{ color: "var(--good)", marginTop: 1, flex: "none" }}><IconCheck size={13} /></span>
              {t}
            </li>
          ))}
        </ul>
        <div className="row micro faint" style={{ gap: 6 }}>
          <IconShield size={13} /> Possession of this link isn’t identity — you must prove your password.
        </div>
      </aside>

      <section className="auth-main">
        <div className="auth-form">
          <h2 style={{ fontSize: 19 }}>Accept your invitation</h2>
          <p className="muted micro" style={{ marginTop: 4, marginBottom: 16 }}>
            Tell us whether you already have a Regis account — it changes what the
            password field means.
          </p>

          <div style={{ marginBottom: 16 }}>
            <Segmented label="Do you already have an account?" value={who} onChange={setWho}
              options={[
                { value: "new", label: "I’m new here" },
                { value: "existing", label: "I have an account" },
              ]} />
          </div>

          <Note tone="info">
            {who === "new"
              ? "The password you enter below becomes your account password."
              : "Enter your existing Regis password so we can confirm it’s you."}
          </Note>

          <form className="stack-sm" style={{ marginTop: 14 }}
            onSubmit={(e) => { e.preventDefault(); void submit(); }} noValidate>
            {who === "new" && (
              <Field label="Full name" hint="Optional — makes the team list and audit trail readable.">
                {(p) => <input className="input" value={name} autoComplete="name"
                  onChange={(e) => setName(e.target.value)} {...p} />}
              </Field>
            )}

            <Field label={who === "new" ? "Choose a password" : "Your existing password"} required
              hint={who === "new" ? "At least 8 characters." : undefined}
              error={touched ? pwError : null}>
              {(p) => (
                <input className="input" type="password" value={password} autoFocus
                  autoComplete={who === "new" ? "new-password" : "current-password"}
                  onChange={(e) => setPassword(e.target.value)}
                  onBlur={() => setTouched(true)} {...p} />
              )}
            </Field>

            {err && <Note tone="crit">{err}</Note>}

            <button className="btn primary lg block" type="submit" disabled={busy} style={{ marginTop: 6 }}>
              {busy ? <Spinner onDark /> : <IconLock size={14} />}
              Accept and continue
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}

function explain(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 401 || e.status === 403) {
      return "That password doesn’t match an existing Regis account. If you’re new, switch to “I’m new here” and choose a password instead.";
    }
    if (e.status === 409 || e.status === 410) {
      return "This invitation has already been used or withdrawn. Ask a compliance admin to send you a fresh one.";
    }
    if (e.status === 404) return "This invitation is no longer valid. Ask a compliance admin to re-invite you.";
    if (e.status === 422) return e.message || "Some details weren’t accepted — check the password requirements.";
    if (e.status === 0) return "Couldn’t reach the server. Check your connection and try again.";
    if (e.status >= 500) return "The server had a problem. This is usually temporary — try again in a moment.";
    return e.message;
  }
  return e instanceof Error ? e.message : "Couldn’t accept the invitation.";
}
