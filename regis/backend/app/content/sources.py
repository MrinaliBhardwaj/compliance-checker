"""
Register of primary regulatory sources.

The moat is not the app — a competent engineer rebuilds that. It is a library of
obligations a Chief Compliance Officer will stake their job on, and the pipeline
that keeps it current. This module is that pipeline's spine.

Three design decisions, each learned the hard way:

1. **Sources are mirrored, never fetched on demand.** `rbi.org.in` is not
   reliably reachable from CI or a sandbox, and a regulator's site is not a
   dependency you want in a code path. A human downloads the instrument, drops
   it under `mirror/`, and records its digest here. Retrieval is a deliberate
   human act with a date attached.

2. **A verification is bound to a digest, not just a source.** Signing off a
   template against "the SBR Master Direction" is meaningless when that document
   is amended. Sign-off records the exact bytes reviewed. Re-mirror an amended
   instrument and everything verified against the old digest goes **STALE** and
   returns to the queue — automatically, rather than when someone remembers.

3. **The register lives in git, beside the templates it governs.** It is
   reviewable in a pull request, diffable, and readable offline. A database table
   would put the content team's audit trail somewhere a reviewer cannot see it.

Secondary summaries are not sources. Law-firm notes and news write-ups have
already been observed conflating the 29 Apr 2026 Amendment Directions (Type I
registration exemption) with an SBR layer revision, which they are not.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

REGISTER_PATH = Path(__file__).with_name("sources.json")
MIRROR_DIR = Path(__file__).with_name("mirror")

# A source that has been identified but whose text nobody has mirrored yet.
NOT_MIRRORED = "not_mirrored"


class SourceError(ValueError):
    """The register violates its contract."""


@dataclass(frozen=True)
class Source:
    """One primary instrument: a circular, a Master Direction, a statute."""

    id: str
    citation: str                 # how a reviewer would cite it in a sign-off
    regulator: str                # RBI | MCA | CBIC | CBDT | Parliament | state
    url: str                      # where to obtain it, for the human who mirrors it
    published: str | None = None  # ISO date on the instrument itself
    mirror: str | None = None     # filename under mirror/, once retrieved
    digest: str = NOT_MIRRORED    # sha256 of the mirrored bytes
    retrieved_on: str | None = None
    retrieved_by: str | None = None
    note: str = ""
    supersedes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def mirrored(self) -> bool:
        return self.digest != NOT_MIRRORED

    @property
    def path(self) -> Path | None:
        return MIRROR_DIR / self.mirror if self.mirror else None

    def __post_init__(self) -> None:
        if not self.id or not self.citation:
            raise SourceError("a source needs an id and a citation")
        if self.mirrored and not (self.mirror and self.retrieved_on and self.retrieved_by):
            raise SourceError(
                f"{self.id}: a mirrored source must record mirror, retrieved_on and "
                "retrieved_by — an unattributed document is not evidence")
        if self.mirror and not self.mirrored:
            raise SourceError(f"{self.id}: has a mirror file but no digest")

    def verify_mirror(self) -> bool:
        """True when the file on disk still matches the recorded digest."""
        p = self.path
        if not (self.mirrored and p and p.exists()):
            return False
        return sha256_file(p) == self.digest


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_register(path: Path | str = REGISTER_PATH) -> dict[str, Source]:
    """Read and structurally validate the register. Pure; no I/O beyond the file."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    sources: dict[str, Source] = {}
    for entry in raw["sources"]:
        s = Source(**{**entry, "supersedes": tuple(entry.get("supersedes", ()))})
        if s.id in sources:
            raise SourceError(f"duplicate source id {s.id!r}")
        sources[s.id] = s

    for s in sources.values():
        for old in s.supersedes:
            if old not in sources:
                raise SourceError(f"{s.id}: supersedes unknown source {old!r}")
    return sources


def register_mirror(source_id: str, file: Path, *, retrieved_by: str,
                    retrieved_on: date | None = None,
                    path: Path | str = REGISTER_PATH) -> Source:
    """Record a newly mirrored instrument, writing its digest into the register.

    Copies nothing: the caller places the file under `mirror/` themselves, so the
    act of retrieval stays a deliberate, attributable human step.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    for entry in raw["sources"]:
        if entry["id"] == source_id:
            entry["mirror"] = file.name
            entry["digest"] = sha256_file(file)
            entry["retrieved_on"] = (retrieved_on or date.today()).isoformat()
            entry["retrieved_by"] = retrieved_by
            break
    else:
        raise SourceError(f"unknown source {source_id!r}")

    Path(path).write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    return load_register(path)[source_id]
