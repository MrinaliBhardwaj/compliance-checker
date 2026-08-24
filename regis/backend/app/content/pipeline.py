"""
The content review queue.

`python -m app.content.pipeline status` answers the only question a content
reviewer needs each morning: what is not verified, and what stopped being
verified because its source changed underneath it.

Deliberately not a scraper. The regulator's site is not reachable from CI and is
not a dependency worth having in a code path; retrieval is a human act recorded
in the register. What is automated is the *bookkeeping* — which derivations rest
on which bytes, and which of those bytes have since moved.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from app.content.sources import (
    Source,
    load_register,
    register_mirror,
)
from app.engines import thresholds as th
from app.seed.library_loader import load_library

UNVERIFIED = "DRAFT_UNVERIFIED"


@dataclass
class Queue:
    unmirrored: list[Source]
    corrupt: list[Source]           # digest on disk no longer matches the register
    unverified_thresholds: list
    stale_thresholds: list
    unverified_templates: list[str]
    orphan_thresholds: list         # bound to no source at all

    @property
    def blocking(self) -> int:
        """Items that make the library unsafe to present as certain."""
        return len(self.corrupt) + len(self.stale_thresholds)

    @property
    def total(self) -> int:
        return (len(self.unmirrored) + len(self.corrupt)
                + len(self.unverified_thresholds) + len(self.stale_thresholds)
                + len(self.unverified_templates) + len(self.orphan_thresholds))


def build_queue(register_path: Path | None = None) -> Queue:
    reg = load_register(register_path) if register_path else load_register()
    lib = load_library()

    return Queue(
        unmirrored=[s for s in reg.values() if not s.mirrored],
        # A mirrored file that no longer hashes to its recorded digest means the
        # evidence has been edited or replaced without going through the register.
        corrupt=[s for s in reg.values() if s.mirrored and not s.verify_mirror()],
        unverified_thresholds=th.unverified(),
        stale_thresholds=th.stale(reg),
        unverified_templates=[t["template_id"] for t in lib["obligation_templates"]
                              if t["verification_status"] == UNVERIFIED],
        orphan_thresholds=[t for t in th.ALL if not t.source_id],
    )


def render(q: Queue) -> str:
    lines: list[str] = ["REGIS CONTENT REVIEW QUEUE", "=" * 60, ""]

    if q.corrupt:
        lines += ["!! MIRROR INTEGRITY FAILURE",
                  "   A mirrored document no longer matches its recorded digest.",
                  "   Every sign-off citing it is void until this is resolved.", ""]
        lines += [f"   [!] {s.id}  ({s.mirror})" for s in q.corrupt] + [""]

    if q.stale_thresholds:
        lines += ["!! STALE SIGN-OFFS",
                  "   The source was re-mirrored after these were verified.", ""]
        lines += [f"   [!] {t.key}  (source: {t.source_id})" for t in q.stale_thresholds]
        lines += [""]

    lines += [f"SOURCES NOT YET MIRRORED  ({len(q.unmirrored)})",
              "   Nobody can verify against a document nobody has obtained.", ""]
    for s in q.unmirrored:
        lines += [f"   [ ] {s.id}", f"       {s.citation}", f"       {s.url}"]
    lines += [""]

    lines += [f"THRESHOLDS AWAITING SIGN-OFF  ({len(q.unverified_thresholds)})", ""]
    for t in q.unverified_thresholds:
        src = t.source_id or "UNBOUND — no source in the register"
        lines += [f"   [ ] {t.key} = {t.value} {t.unit}", f"       source: {src}"]
    lines += [""]

    if q.orphan_thresholds:
        lines += [f"THRESHOLDS BOUND TO NO SOURCE  ({len(q.orphan_thresholds)})",
                  "   These cannot go stale, because nothing tracks what they rest on.", ""]
        lines += [f"   [!] {t.key}" for t in q.orphan_thresholds] + [""]

    lines += [f"OBLIGATION TEMPLATES AWAITING SIGN-OFF  ({len(q.unverified_templates)})",
              "   Reports render PROVISIONAL while any of these remain.", ""]
    shown = q.unverified_templates[:10]
    lines += [f"   [ ] {tid}" for tid in shown]
    if len(q.unverified_templates) > len(shown):
        lines += [f"   ... and {len(q.unverified_templates) - len(shown)} more"]
    lines += ["", "=" * 60,
              f"{q.total} open items, {q.blocking} of them blocking.", ""]

    if q.blocking:
        lines += ["Blocking items void existing sign-offs. Resolve before any",
                  "report leaves the building."]
    elif q.unverified_templates or q.unverified_thresholds:
        lines += ["Nothing is blocking, but the library is still provisional —",
                  "which the product says out loud, and should keep saying."]
    return "\n".join(lines)


def _cmd_status(args) -> int:
    print(render(build_queue()))
    return 0


def _cmd_check(args) -> int:
    """CI gate: fail only on blocking items, never on merely-unverified ones.

    An unverified library is the honest, expected state before a reviewer is
    engaged; failing the build on it would train everyone to ignore the check.
    A broken mirror or a stale sign-off is different — it means something we
    already claimed to have verified is no longer supported.
    """
    q = build_queue()
    if q.blocking:
        print(render(q), file=sys.stderr)
        return 1
    print(f"content check ok — {q.total} open items, none blocking")
    return 0


def _cmd_mirror(args) -> int:
    f = Path(args.file)
    if not f.exists():
        print(f"no such file: {f}", file=sys.stderr)
        return 2
    s = register_mirror(args.source_id, f, retrieved_by=args.by)
    print(f"mirrored {s.id}\n  file:   {s.mirror}\n  digest: {s.digest}\n"
          f"  by:     {s.retrieved_by} on {s.retrieved_on}")
    print("\nAny sign-off previously made against an older digest is now stale.\n"
          "Run `python -m app.content.pipeline status` to see what returned to the queue.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.content.pipeline",
                                     description="Regis content review queue")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="print the review queue").set_defaults(fn=_cmd_status)
    sub.add_parser("check", help="CI gate: non-zero on blocking items").set_defaults(fn=_cmd_check)

    m = sub.add_parser("mirror", help="record a retrieved primary document")
    m.add_argument("source_id")
    m.add_argument("file", help="path to the file, already placed under content/mirror/")
    m.add_argument("--by", required=True, help='who retrieved it, e.g. "A. Rao, ACS 12345"')
    m.set_defaults(fn=_cmd_mirror)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":  # pragma: no cover - operator entrypoint
    raise SystemExit(main())
