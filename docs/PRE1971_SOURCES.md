# Pre-1971 conference text — sources (researched 2026-10-05)

Endpoints below were verified by fetching on 2026-10-05 unless marked otherwise.
This file enables SPEC feature F6. Do the tiers in order; tier 1 alone satisfies F6.

All of this is `source='historical'` in `corpus.db`. Throttle to ≤ 2 requests/second,
cache every raw response under `data/raw/`, and keep the text private like the rest.

## Tier 1 — 1942–1970, talk-level (scriptures.byu.edu)

- List conferences: `https://scriptures.byu.edu/citation_index/gc_ajax`
  → entries like `getConf('1955','A')` (A = April, O = October).
- List talks: `https://scriptures.byu.edu/citation_index/gc_ajax/1955/A`
  → HTML fragment: `div.sessiontitle`, then `getTalk('749')` with `div.speaker`
  and `div.talktitle`.
- Fetch a talk: `https://scriptures.byu.edu/content/talks_ajax/749`
  → `p.gctitle`, `p.gcspeaker`, `p.gcspkpos`, `p.gcbib`
  ("Conference Report, April 1955, pp. 10-11"), body in `div.gcbody`.
- Scripture citations sit in `span.citation`, which duplicates the reference text:
  record them as citations, then strip the spans from the body.
- Talk IDs run roughly 1 (April 1942) to 1823 (October 1970); enumerate through the
  listings, do not guess. About 1,800 talks.
- Quirks: many titles are "Untitled"; October 1957 returns no talks.
- Plain HTTP GET works; no auth, no JavaScript.

## Tier 2 — 1851–1886, Journal of Discourses (same site)

- List a volume: `https://scriptures.byu.edu/citation_index/jod_ajax/<vol>` (1–26).
- Talk ID = vol × 10000 + n, e.g. `/content/talks_ajax/10001`.
- These are discourses, not all given at General Conference. Store them with
  `kind='discourse'` and keep them out of conference-level trend lines unless a
  date/venue filter shows they were conference addresses.

## Tier 3 — 1897–1941, whole-volume OCR (archive.org) — optional, hardest

- Items: `conferencereport<YYYY>a` (April), `conferencereport<YYYY>sa` (October).
  147 of 149 expected volumes for 1880 and 1897–1970 have OCR text; `1897a` and
  `1957sa` are missing.
- The text filename is not always `<id>_djvu.txt` (26 items differ). Resolve it via
  `https://archive.org/metadata/<id>` and take the file ending `_djvu.txt`.
- Whole-volume OCR with running page headers and statistical tables. Talks must be
  segmented; all-caps speaker headings are the likely anchors. Only attempt this
  after tiers 1–2, and record segmentation accuracy on a hand-checked sample.

## Known gap

1887–1896 is covered by none of these sources.

## Not usable

- lds-general-conference.org (BYU corpus, 1850s–2020s): query interface only, no
  bulk download.
- No packaged dataset with pre-1971 full text was found on GitHub or HuggingFace.

## Analysis caveat

Pre-1971 talks have no footnotes in the modern sense and a different speaker mix,
length and format. Long-run charts that cross 1971 must mark the source change.
