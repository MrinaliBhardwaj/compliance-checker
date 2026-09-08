"use client";
// 404. A dead URL should still offer the two things people actually want:
// a way back to their queue, and a way to search for the thing they wanted.
import Link from "next/link";
import { IconArrowRight, IconSearch } from "@/components/icons";

export default function NotFound() {
  return (
    <main style={{ display: "grid", placeItems: "center", minHeight: "100dvh", padding: 24 }}>
      <div style={{ maxWidth: 420, width: "100%" }}>
        <span className="eyebrow">Not found</span>
        <h1 style={{ marginTop: 6 }}>That page doesn’t exist</h1>
        <p className="muted" style={{ marginTop: 8, fontSize: 12.5, lineHeight: 1.6 }}>
          The link may be out of date, or the obligation it pointed to was reopened,
          reassigned or marked not applicable.
        </p>
        <div className="row" style={{ gap: 8, marginTop: 18 }}>
          <Link className="btn primary" href="/dashboard">
            Back to Today <IconArrowRight size={13} />
          </Link>
          <Link className="btn" href="/obligations">
            <IconSearch size={13} /> Search obligations
          </Link>
        </div>
      </div>
    </main>
  );
}
