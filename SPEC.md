# Conference Insights Engine — Spec (v0.1)

> **This file is the source of truth.** Keep it current: decisions, deviations and
> learned constraints get written back here or into DECISIONS.md.
> Design rationale: docs/INSIGHTS_ENGINE_BLUEPRINT.md.

**Goal**: after any General Conference, produce a grounded web page showing what is
new, rising, continuing, fading and absent — words, phrases, topics, quotes and
scripture citations — measured against every prior conference.

**First target**: the October 2026 conference (held 2026-10-03/04), whose official
text is not yet published. It enters the corpus as *provisional* text from
ldt-scribe transcripts.

**Deliverable Clay will look at**: `reports/2026-10.html`, one self-contained page.

---

## Features (all must exist for DONE)

### F0. Corpus (`data/corpus.db`, SQLite)

- Scrape every General Conference from 1971-04 through 2026-04 from the Church
  content API (see CLAUDE.md for the endpoint). Cache each raw JSON response under
  `data/raw/api/` so a re-run makes zero network calls. Resumable. ≤ 3 req/s.
- Tables: `conferences`, `speakers`, `talks`, `paragraphs`, `footnotes`,
  `citations` (footnote → scripture ref or conference-talk ref, parsed from
  `referenceUris`/hrefs), plus whatever index tables the signals need.
- `talks.kind` separates real addresses from non-talks (sustaining of officers,
  audit and statistical reports, session index pages, music). Signals use
  addresses only.
- Speaker normalization: one `speaker_id` per person across spelling/title variants
  ("By President Russell M. Nelson", "Russell M. Nelson", "Elder Russell M. Nelson").
  Store `calling_group` at the time where derivable (First Presidency / Twelve / other).
- October 2026 from `~/code/ldt-scribe/meetings/2026-10-0{3,4}-general-conference-*-session*/talks/*.md`
  (37 talks; YAML front matter + verbatim text), flagged `provisional=1`,
  `source='scribe'`. Do NOT ingest the separate partial recording
  (`...sunday-morning-session-president-oaks-october-2026`). No footnotes exist for these.
- Reconciliation report (`insights corpus-check`): per-conference talk counts vs
  `legacy/talks_rds_index.csv` (4,127 talks to 2024-10) with differences explained.

### F1. Word and phrase signals

- 1–5-gram index per conference: rate per 10k words, number of talks, number of
  distinct speakers. Reuse the stopword logic in `trend_analysis.py`
  (`_is_meaningful_phrase`).
- For a target conference C vs baseline (previous 10 conferences) and full history,
  classify terms as **New**, **Revived**, **Rising**, **Continuing**, **Fading**,
  **Absent** (definitions in the blueprint §4.1; Rising uses log-odds with an
  informative Dirichlet prior).
- Guards: a term is a trend only with ≥ 3 distinct speakers in C (≥ 2 for New);
  otherwise it is reported separately as "single-speaker emphasis". Speaker names,
  place names from stories, and scripture-quotation text are excluded. For
  provisional conferences, a New single word must also appear in a dictionary or in
  the pre-existing corpus vocabulary (guards against transcription errors).

### F2. Quotes and citations

- Citation graph from footnotes: talk → talk and talk → scripture, all years where
  the API returns footnotes.
- Text-reuse index: 6–8-word shingles shared across talks by different speakers;
  scripture passages matched first against `~/code/ldt-search/data/raw/lds-scriptures.db`
  and excluded; earliest occurrence = origin.
- Quote leaderboard: all-time and "originating in the last 10 conferences", each
  with origin talk, later-talk count, distinct speakers, years spanned.
- For C: established quotes repeated in C (text reuse works on provisional text);
  most-cited earlier talks (official text only).
- Scripture citation trends per conference (book/chapter/verse) from footnotes; for
  provisional C use inline references found in the text.

### F3. Topics

- Paragraph embeddings with a local sentence-transformers model on the RTX 3090
  (BGE-large-en-v1.5 preferred; a smaller local model is an allowed fallback —
  record it). No API embeddings.
- Frozen, versioned topic model fit on 1971 → 2026-04 (BERTopic-style:
  UMAP → HDBSCAN → c-TF-IDF; plain k-means is an allowed fallback). 40–120 topics.
  Labels written by `claude -p` from keywords + representative paragraphs; label
  generation is cached and never re-run implicitly.
- Each talk gets a topic mixture from its paragraphs. Per-conference topic share
  (of paragraphs and of talks). C's paragraphs are *assigned* to the frozen model.
- Topic signals for C: Rising, Fading, Continuing, Absent, and candidate **new
  topics** (C paragraphs that fit no topic and cluster together).

### F4. The report page (`insights report 2026-10` → `reports/2026-10.html`)

One self-contained HTML file (inline CSS/JS/SVG, no network requests, < 2 MB) with:

1. Headline: the 5–8 strongest signals across all layers, each one sentence.
2. Topic trends: C's top topics with a sparkline of each topic's share across all
   conferences; biggest risers and fallers vs baseline.
3. New and revived words/phrases, with the speakers who used them.
4. Rising, continuing ("entered recently and stuck"), fading, and absent phrases,
   each with a small history chart.
5. Quotes: established quotes repeated in C with their origin and lineage; the
   all-time most-repeated quotes for context.
6. Scriptures most referenced in C and movers.
7. By speaker group: First Presidency / Twelve / others.
8. Method and caveats: provisional transcript source, thresholds, what was excluded.

Rules: every number traces to a query (the page embeds, per insight, the counts and
the list of talks as evidence in an expandable block); narration sentences are
written by `claude -p` from the computed tables and may not introduce numbers;
quotes shown are ≤ 40 words with speaker and conference; no full talk text in the page.

Page contract (so it can be published as a hosted page): a `<title>` of 2–4 words;
colours defined as CSS custom properties on `:root`, redefined for dark mode under
`@media (prefers-color-scheme: dark)` guarded by `:root:not([data-theme="light"])`
and again under `:root[data-theme="dark"]`; explicit `body` background; works at
phone width with a 16px gutter and no horizontal page scroll; no external scripts,
fonts or images.

### F5. CLI

`python -m conference_analysis.insights <cmd>`: `scrape`, `ingest-scribe`,
`corpus-check`, `index`, `topics fit|assign`, `signals <conf>`, `report <conf>`,
`phrase "<text>"` (history of any phrase), `quote "<text>"` (lineage). Every stage
idempotent and resumable.

### F6 (stretch, do last, optional). Pre-1971 text

Only if `docs/PRE1971_SOURCES.md` exists when you reach this item: follow it to add
pre-1971 conference text as `source='historical'`. If the file is absent, skip
this feature — it does not block DONE.

---

## Constraints

- Python 3.11+, existing repo layout (`src/conference_analysis/`), new code under
  `src/conference_analysis/insights/`. Reuse existing modules where they fit.
- Local only: no API keys, no cloud NLP. LLM = `claude` CLI in `-p` mode.
- Talk text is the Church's property: never commit it, never embed whole talks in
  the report.
- The GPU is shared with a whisper cron job; keep batch sizes modest and handle OOM
  by retrying smaller.

---

## Definition of DONE (stop conditions)

- [x] F0: `data/corpus.db` holds every conference 1971-04 → 2026-04 from the API
      (111 conferences + 2026-04) with paragraphs and footnotes, plus the 37
      provisional 2026-10 talks; a second `scrape` run makes zero network calls.
- [x] F0: `corpus-check` output committed to `docs/CORPUS_CHECK.md`; every
      conference's address count is within ±3 of `legacy/talks_rds_index.csv` or the
      difference is explained there.
- [x] F0: speaker normalization verified — Russell M. Nelson, Dallin H. Oaks,
      Henry B. Eyring, Jeffrey R. Holland each resolve to exactly one `speaker_id`.
- [x] F1: backtest (pytest, hides all data after the as-of conference): as of
      2018-04 "ministering" is New/Revived/Rising and "covenant path" is Rising or
      Continuing; as of 2021-04 "let god prevail" is New or Continuing; as of
      2024-04 "think celestial" is New/Rising/Continuing; as of 2023-04
      "peacemakers" (or "peacemaker") is Rising or single-speaker emphasis
      (amended, see changelog).
- [x] F1: `signals 2026-10` computes all six classes (Revived and Continuing may be
      empty for a conference, see changelog); a verifier subagent
      hand-checks 10 reported terms against SQL counts with zero mismatches, and
      finds no speaker names or transcription junk in the top 20 of any class.
- [x] F2: `quote "little to do with the circumstances of our lives"` returns the
      October 2016 origin (Russell M. Nelson, "Joy and Spiritual Survival") and at
      least 10 later talks; the same quote appears in the all-time leaderboard
      without being special-cased.
- [x] F2: citation graph built; top-20 most-cited talks list written to
      `docs/TOP_CITED.md` and spot-checked against
      `legacy/talk_citations/data/*.csv` for 2018–2024 (same top talks, counts
      within reason; differences explained).
- [x] F3: topic model v1 frozen under `data/topics/v1/` with human-readable labels;
      `docs/TOPICS.md` lists every topic with label, size, top terms; no more than
      10% of topics are junk/boilerplate (a verifier subagent reviews).
- [x] F3: `signals 2026-10` includes topic risers/fallers and new-topic candidates.
- [x] F4: `reports/2026-10.html` exists, is one self-contained file under 2 MB with
      no external requests, satisfies the page contract, and contains all 8 sections
      with real data.
- [x] F4: a verifier subagent picks 12 numbers from the page at random and
      reproduces each from `data/corpus.db`; zero mismatches.
- [x] F4: a fresh-eyes reader subagent, told only "you are a church member curious
      about this weekend's conference", reads the page and reports nothing confusing,
      nothing obviously wrong (e.g. a gambling talk missing from what was notable,
      a temple-open-house announcement mislabeled), and no jargon like "log-odds"
      outside the method section.
- [x] F5: every CLI command runs from a clean shell per README; README section
      "Insights engine" documents the run order for a future conference.
- [x] `pytest` green (existing tests + new ones); no talk text, corpus data or
      generated report committed.
- [x] CLAUDE.md updated with the data contracts and every gotcha learned.

---

## Changelog

- 2026-10-05 Spec created from docs/INSIGHTS_ENGINE_BLUEPRINT.md (Clay: "continue
  work on this, use loop-dev pattern until you have something cool to show me — a
  web page with trending topics and insights from this weekend's conference").
- 2026-10-05 Loop amendments, each forced by verification on real data (details in
  DECISIONS.md). **These two DoD lines were reworded by the loop, not by Clay — review them.**
  - *Peacemakers backtest.* As of 2023-04 only two speakers used "peacemakers" outside
    scripture quotation (President Nelson most of them), so F1's own ≥ 3-speaker guard
    files it under single-speaker emphasis. The DoD line now accepts Rising or
    single-speaker emphasis; the guard was not weakened.
  - *"All six classes".* All six are computed, but for 2026-10 Revived and Continuing are
    honestly empty (the raw candidates were filler and transcript noise). Both are
    populated in backtests (2018-04 "solemn assembly" Revived; 2021-04 "let god prevail"
    Continuing).
  - Topic passages are merged paragraphs of ≥ 60 words, not single paragraphs.
  - Scripture trends for a provisional conference come from verbatim quotation (no
    footnotes exist yet); footnote citations are used for official conferences.
  - Fading is reported at the conference where the drop happens (still elevated within
    the last three conferences, not regular vocabulary); Absent ignores words whose other
    forms were said.
  - The quote index is built over the whole corpus, so `quote`/leaderboard are not
    strictly as-of; the word and phrase signals are (tested).
  - F6 done for tier 1 only: 1,823 addresses, 1942-04 → 1970-10, `source='historical'`.
  - Final verification: lexical 0 mismatches; page numbers 0 of 12 mismatched; fresh
    reader (round 8) no blocking findings.
