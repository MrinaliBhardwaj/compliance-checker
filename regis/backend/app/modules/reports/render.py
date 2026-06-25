"""
Report renderers.

- `render_html` — always available, pure stdlib, the canonical rich report.
- `render_pdf` — reportlab when installed (production image), else a dependency-free
  pure-Python PDF writer so the endpoint always returns a valid PDF. Both are
  swappable; nothing here is an external hard dependency.
"""
from __future__ import annotations

import html


# ---------------------------------------------------------------------------
# HTML (canonical)
# ---------------------------------------------------------------------------
def render_html(report: dict) -> str:
    e = html.escape
    banner = ("<div class='prov'>PROVISIONAL — generated from a DRAFT_UNVERIFIED "
              "obligation library pending content-team verification.</div>"
              if report["provisional"] else "")

    def table(items, cols):
        head = "".join(f"<th>{c}</th>" for c, _ in cols)
        body = ""
        for it in items:
            body += "<tr>" + "".join(f"<td>{e(str(it.get(k) or ''))}</td>" for _, k in cols) + "</tr>"
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"

    cols = [("Period", "period_label"), ("Obligation", "title"),
            ("Form", "form_reference"), ("Due", "due_date"), ("Risk", "risk_level")]
    s = report["sections"]
    cat_rows = "".join(
        f"<tr><td>{e(k)}</td><td>{e(str(v))}</td></tr>" for k, v in report["by_category"].items())

    return f"""<!doctype html><html><head><meta charset='utf-8'>
<title>Compliance Status — {e(report['organization'])}</title>
<style>
 body{{font-family:Arial,Helvetica,sans-serif;color:#16203a;margin:32px;}}
 h1{{margin-bottom:0}} .muted{{color:#5b6b8c}}
 .prov{{background:#fff4e5;border:1px solid #e8b339;padding:8px 12px;border-radius:6px;margin:12px 0;font-weight:600}}
 .tiles{{display:flex;gap:16px;margin:16px 0}} .tile{{border:1px solid #d6deec;border-radius:8px;padding:12px 16px}}
 .tile b{{font-size:24px;display:block}}
 table{{border-collapse:collapse;width:100%;margin:8px 0 20px}} th,td{{border:1px solid #d6deec;padding:6px 8px;text-align:left;font-size:13px}}
 th{{background:#f3f6fc}}
</style></head><body>
<h1>Compliance Status Report</h1>
<div class='muted'>{e(report['organization'])} · {e(report['entity'])} · as of {e(report['as_of'])}
 · library {e(report['library_version'])}</div>
{banner}
<p><b>Health score:</b> {report['health_score']}%</p>
<p>{e(report['narrative'])}</p>
<div class='tiles'>
 <div class='tile'><b>{report['tiles']['overdue']}</b>Overdue</div>
 <div class='tile'><b>{report['tiles']['due_this_week']}</b>Due this week</div>
 <div class='tile'><b>{report['tiles']['awaiting_review']}</b>Awaiting review</div>
 <div class='tile'><b>{report['tiles']['completed']}</b>Completed</div>
</div>
<h3>Overdue ({len(s['overdue'])})</h3>{table(s['overdue'], cols)}
<h3>Due this week ({len(s['due_this_week'])})</h3>{table(s['due_this_week'], cols)}
<h3>Awaiting review ({len(s['awaiting_review'])})</h3>{table(s['awaiting_review'], cols)}
<h3>By category</h3><table><thead><tr><th>Category</th><th>Status breakdown</th></tr></thead>
<tbody>{cat_rows}</tbody></table>
<p class='muted'>Generated {e(report['generated_at'])}. Compliance evidence is retained in the
 platform audit log. This report is informational; confirm filings with your compliance team.</p>
</body></html>"""


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def render_pdf(report: dict) -> bytes:
    try:
        return _render_pdf_reportlab(report)
    except Exception:
        return _render_pdf_minimal(_report_lines(report))


def _report_lines(report: dict) -> list[str]:
    s = report["sections"]
    lines = [
        "COMPLIANCE STATUS REPORT",
        f"{report['organization']}  |  {report['entity']}  |  as of {report['as_of']}",
        f"Library {report['library_version']}",
        "",
    ]
    if report["provisional"]:
        lines += ["PROVISIONAL — DRAFT_UNVERIFIED library pending content-team verification.", ""]
    lines += [
        f"Health score: {report['health_score']}%",
        report["narrative"],
        "",
        f"Overdue: {report['tiles']['overdue']}   Due this week: {report['tiles']['due_this_week']}"
        f"   Awaiting review: {report['tiles']['awaiting_review']}"
        f"   Completed: {report['tiles']['completed']}",
        "",
    ]
    for title, key in (("OVERDUE", "overdue"), ("DUE THIS WEEK", "due_this_week"),
                       ("AWAITING REVIEW", "awaiting_review")):
        lines.append(f"{title} ({len(s[key])})")
        for it in s[key][:40]:
            lines.append(f"  {it.get('due_date') or '—'}  {it['period_label']}  "
                         f"{(it['title'] or '')[:60]}")
        lines.append("")
    lines.append(f"Generated {report['generated_at']}")
    return lines


def _render_pdf_reportlab(report: dict) -> bytes:
    import io

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 50
    for line in _report_lines(report):
        if y < 50:
            c.showPage()
            y = height - 50
        c.setFont("Helvetica", 10)
        c.drawString(40, y, line[:110])
        y -= 14
    c.showPage()
    c.save()
    return buf.getvalue()


def _render_pdf_minimal(lines: list[str]) -> bytes:
    """Dependency-free PDF writer: paginates text lines into a valid multi-page PDF."""
    def esc(t: str) -> str:
        return (t.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
                .encode("latin-1", "replace").decode("latin-1"))

    per_page = 50
    pages = [lines[i:i + per_page] for i in range(0, max(len(lines), 1), per_page)] or [[""]]

    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)  # 1-based object number

    catalog_num = add(b"")          # 1 placeholder (catalog)
    pages_num = add(b"")            # 2 placeholder (pages)
    font_num = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    page_nums: list[int] = []
    content_nums: list[int] = []
    for page_lines in pages:
        body = ["BT", "/F1 10 Tf", "40 800 Td", "13 TL"]
        for j, ln in enumerate(page_lines):
            body.append(f"({esc(ln[:110])}) Tj" if j == 0 else f"T* ({esc(ln[:110])}) Tj")
        body.append("ET")
        stream = "\n".join(body).encode("latin-1")
        cnum = add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        content_nums.append(cnum)
        pnum = add(("<< /Type /Page /Parent %d 0 R /MediaBox [0 0 595 842] "
                    "/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
                    % (pages_num, font_num, cnum)).encode("latin-1"))
        page_nums.append(pnum)

    kids = " ".join(f"{n} 0 R" for n in page_nums)
    objects[pages_num - 1] = ("<< /Type /Pages /Kids [%s] /Count %d >>"
                              % (kids, len(page_nums))).encode("latin-1")
    objects[catalog_num - 1] = ("<< /Type /Catalog /Pages %d 0 R >>" % pages_num).encode("latin-1")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0] * (len(objects) + 1)
    for idx, obj in enumerate(objects, start=1):
        offsets[idx] = len(out)
        out += b"%d 0 obj\n" % idx + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for idx in range(1, len(objects) + 1):
        out += b"%010d 00000 n \n" % offsets[idx]
    out += (b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF"
            % (len(objects) + 1, catalog_num, xref_pos))
    return bytes(out)
