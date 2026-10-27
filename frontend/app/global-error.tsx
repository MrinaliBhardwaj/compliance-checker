"use client";
// Last-resort boundary: catches failures in the root layout itself, where the
// theme, providers and stylesheet may not have mounted. It therefore inlines
// everything it needs and assumes nothing about the design system being present.
export default function GlobalError({ error, reset }:
  { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en">
      <body style={{
        margin: 0, minHeight: "100vh", display: "grid", placeItems: "center",
        background: "#FBFBF9", color: "#15161A", padding: 24,
        fontFamily: 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
      }}>
        <div style={{ maxWidth: 440 }}>
          <div style={{
            fontSize: 10.5, fontWeight: 650, letterSpacing: ".07em",
            textTransform: "uppercase", color: "#B42318",
          }}>Application error</div>
          <h1 style={{ fontSize: 20, margin: "8px 0 0", letterSpacing: "-0.011em" }}>
            Regis couldn’t start
          </h1>
          <p style={{ color: "#55585F", fontSize: 13, lineHeight: 1.6, marginTop: 10 }}>
            This is a failure loading the application shell. No compliance data was
            read or modified.
          </p>
          <button onClick={reset} style={{
            marginTop: 18, padding: "8px 14px", borderRadius: 5, border: "1px solid #15161A",
            background: "#15161A", color: "#fff", fontWeight: 600, fontSize: 13, cursor: "pointer",
          }}>Reload the application</button>
          {error.digest && (
            <p style={{ color: "#82858D", fontSize: 11.5, marginTop: 14 }}>
              Reference: {error.digest}
            </p>
          )}
        </div>
      </body>
    </html>
  );
}
