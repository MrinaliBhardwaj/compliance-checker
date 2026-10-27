"use client";
// Route-level error boundary.
//
// Without this, any render error blanks the entire app — which in a compliance
// product reads as data loss. It recovers in place, keeps the technical detail
// available for a support ticket, and never pretends the failure didn't happen.
import { useEffect } from "react";
import Link from "next/link";
import { IconAlert, IconUndo } from "@/components/icons";

export default function RouteError({ error, reset }:
  { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    // Surfaced for whoever is watching the console or a log drain.
    console.error("Route error:", error);
  }, [error]);

  return (
    <main style={{ display: "grid", placeItems: "center", minHeight: "100dvh", padding: 24 }}>
      <div style={{ maxWidth: 460, width: "100%" }}>
        <div className="row" style={{ gap: 8, marginBottom: 10, color: "var(--crit)" }}>
          <IconAlert size={16} />
          <span className="eyebrow" style={{ color: "inherit" }}>Something broke</span>
        </div>
        <h1>This screen failed to load</h1>
        <p className="muted" style={{ marginTop: 8, fontSize: 12.5, lineHeight: 1.6 }}>
          Nothing was changed or lost — this is a display failure, not a data failure.
          Your compliance record is untouched.
        </p>

        <div className="row" style={{ gap: 8, marginTop: 18 }}>
          <button className="btn primary" onClick={reset}>
            <IconUndo size={13} /> Try again
          </button>
          <Link className="btn" href="/dashboard">Back to Today</Link>
        </div>

        <details style={{ marginTop: 20 }}>
          <summary className="micro faint" style={{ cursor: "pointer" }}>
            Technical detail
          </summary>
          <pre className="mono" style={{
            marginTop: 8, whiteSpace: "pre-wrap", wordBreak: "break-word",
            background: "var(--surface-2)", border: "1px solid var(--rule)",
            borderRadius: "var(--r-xs)", padding: 10, color: "var(--ink-2)",
          }}>
            {error.message}
            {error.digest ? `\n\nDigest: ${error.digest}` : ""}
          </pre>
          <p className="micro faint" style={{ marginTop: 6 }}>
            Include this when reporting the problem.
          </p>
        </details>
      </div>
    </main>
  );
}
