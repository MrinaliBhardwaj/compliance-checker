"use client";
// Invite acceptance (public): an invited teammate sets a password and lands in
// the workspace with their assigned role. Token comes from the invite link.
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { acceptInvite, setToken } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Spinner } from "@/components/ui";

export default function AcceptPage() {
  return (
    <Suspense fallback={null}>
      <Accept />
    </Suspense>
  );
}

function Accept() {
  const params = useSearchParams();
  const router = useRouter();
  const { refresh } = useAuth();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    setErr(null); setBusy(true);
    try {
      const res = await acceptInvite(token, password || undefined, name || undefined);
      setToken(res.access_token);
      localStorage.setItem("regis_entity", res.entity_id);
      await refresh();
      router.push("/dashboard");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not accept invite");
    } finally {
      setBusy(false);
    }
  };

  if (!token) {
    return <main style={{ maxWidth: 430, margin: "9vh auto", padding: 24 }}>
      <div className="banner err">Missing invite token. Please use the link from your invitation email.</div>
    </main>;
  }

  return (
    <main style={{ maxWidth: 430, margin: "9vh auto", padding: 24 }}>
      <h1>Accept your invite</h1>
      <p className="muted">Set a password to join your team&apos;s compliance workspace.</p>
      <div className="card stack" style={{ marginTop: 8 }}>
        <label className="field"><span>Full name (optional)</span>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label className="field"><span>Choose a password</span>
          <input className="input" type="password" value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()} /></label>
        {err && <div className="banner err">{err}</div>}
        <button className="btn primary" style={{ justifyContent: "center" }}
          disabled={busy} onClick={submit}>
          {busy ? <Spinner /> : "Accept & continue"}
        </button>
      </div>
    </main>
  );
}
