# Mirrored primary sources

The actual regulatory documents every obligation and threshold derives from.

**Committed deliberately.** These are the evidence behind sign-offs, and a
sign-off is only as durable as the ability to re-read exactly what was signed
off. A regulator can amend, move, or withdraw a document; the register records
the sha256 of the bytes reviewed, and this directory holds those bytes.

## Adding one

1. Download the instrument from the `url` in `../sources.json`. **From the
   regulator's own site** — a law-firm summary is not a source.
2. Save it here, named for its source id (e.g. `rbi_sbr_md_2023.pdf`).
3. Record it:

   ```bash
   python -m app.content.pipeline mirror rbi_sbr_md_2023 \
       app/content/mirror/rbi_sbr_md_2023.pdf --by "A. Rao, ACS 12345"
   ```

That writes the digest, date, and retriever into the register. Anything
previously verified against an older digest becomes **stale** and returns to the
queue — check with `python -m app.content.pipeline status`.

## Why not fetch automatically

`rbi.org.in` is not reliably reachable from CI or a sandboxed environment, and a
regulator's website is not a dependency worth putting in a code path. More
importantly, retrieval should be attributable: a named person obtained this
document on this date. A scraper cannot sign anything.

## If these get large

Nothing here is big today. If the corpus grows past what is comfortable in git,
move to git-lfs rather than dropping the files — losing the evidence would make
every historical sign-off unreproducible.
