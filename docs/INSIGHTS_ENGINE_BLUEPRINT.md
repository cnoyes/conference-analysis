# Conference Insights Engine — Blueprint

**Drafted**: 2026-10-05
**Goal**: within hours of any General Conference, produce a grounded report of what is
new, rising, continuing, fading and absent — at the level of words, phrases, topics,
quotes and scripture citations — measured against every conference since 1971.

---

## 1. What already exists (audit, 2026-10-05)

| Repo | What it has | State |
|---|---|---|
| `ldt-search` | The only full-text corpus on ai-lab: 4,266 talks, 7.3M words, 111 conferences, April 1971 – October 2025. 3,771 talks from the johnmwood CSV (1971–2018) plus 495 scraped JSON files (2019–2025). BGE-large embeddings of 15,841 paragraph chunks in ChromaDB. Scriptures DB (41,995 verses). | Working, last updated 2026-03-10 |
| `conference-analysis` | 2,100 lines of analysis code: scraper, word and n-gram frequency over time, two-period increase/decrease comparison with stopword filtering, hypothesis tests, K-Means/DBSCAN clustering on sentence embeddings, Plotly charts, two notebooks. | Code only. `data/` is empty on this machine. Last commit 2025-12-12 |
| `ldt-data` | Metadata for 4,890 talks (title, speaker, date, URL, word count), public stats JSON, `ROADMAP.md`, and `PHASE_2_1_PLAN.md` for wiring the analysis into the web UI. Empty `citations/` and `embeddings/` folders. | Plan written 2026-02-15, not started |
| `ldt-conference` | Next.js dashboard with static stats and a "Coming Soon" block for NLP features. | Live, static |
| Google Drive `Professional/Projects/` (not on ai-lab) | The original R work. `conference/`: rvest scraper (`talks.R`), `talks.rds` with full text, a tm document-term matrix, a Shiny word-cloud app, and `dev/joy_analysis.R`. `gospel_topics/`: a 50-topic LDA on that matrix. `talk_citations/`: a Selenium footnote scraper and talk-to-talk citation CSVs for 19 conferences (October 2012, April 2016 – October 2024), plus an R ranking of most-cited talks. | Last touched October 2024 |
| `ldt-scribe` | Verbatim transcripts and summaries of all 37 October 2026 talks, produced from broadcast audio the same weekend. | Working |

### Gaps that matter for this engine

1. **No single corpus.** Text lives in `ldt-search` in two formats; metadata lives in
   `ldt-data`; the analysis code expects a `talks.csv` that is not on this machine.
2. **624 talks have metadata but no text** (4,890 vs 4,266). Unverified guess: the CSV
   omits some items the Church index lists. Needs a reconciliation pass.
3. **April 2026 is missing everywhere.** October 2026 exists only as scribe transcripts.
4. **Footnotes are partial and off-machine.** Neither text source on ai-lab kept
   footnotes. The only citation data is the `talk_citations` project on Google Drive:
   talk-to-talk citations for 19 conferences, scraped with Selenium in October 2024.
   It covers conference-talk citations only (no scripture citations) and stops at
   October 2024. It is the starting point for the citation graph in section 4.3.
5. **Speaker names are raw strings** ("By President Russell M. Nelson" in the CSV vs
   "Russell M. Nelson" in the JSON). No stable speaker ID.
6. **Existing trend code compares two fixed periods** (e.g. 1971–1989 vs 2010–2025). It
   has no notion of "this conference vs its baseline", no novelty or burst detection,
   and no quote tracking.
7. **`PHASE_2_1_PLAN.md` assumes an OpenAI API key.** There is none on ai-lab, and
   BGE-large on the 3090 already does the job. That part of the plan should be dropped.

### Proof that the idea works on today's data

Plain substring search over the 4,266 talks, no modeling:

| Phrase | Talks | Pattern |
|---|---|---|
| "little to do with the circumstances" (Nelson, Oct 2016) | 12 | origin 2016, then quoted in 11 later talks: 2019 ×2, 2021 ×4, 2022, 2024, 2025 ×3 |
| "covenant path" | 177 | 4 talks in 2017, then 15–25 per year from 2018 on |
| "think celestial" | 13 | one stray use in 1978, 1 in 2023, 10 in 2024, 1 in 2025 |
| "let God prevail" | 27 | 1 in 2020, 11 in 2021, 7 in 2022, then a tail |
| "peacemaker" | 58 | jump to 7 talks in 2023 |

These are exactly the four shapes the engine must name automatically: a quote that
keeps being cited, a phrase that entered and stayed, a burst that faded, and a revival.

One caution on the premise: the Nelson joy quote is clearly a heavily repeated quote,
but whether it is repeated "more than almost anything else" is not yet known. Eleven
later verbatim uses is the number; the ranking needs the quote index in section 4.3.

---

## 2. Design principles

- **Numbers come from code, words come from the LLM.** Every count, rate and rank is
  computed deterministically and stored. The LLM (via `claude -p`, as in ldt-scribe)
  only labels topics and narrates tables it is handed. It never produces a number.
- **Every insight carries its evidence**: the talks, the paragraph, the count, the
  baseline it was compared with.
- **The conference is the unit of time.** 111 points so far, two per year.
- **Normalize everything.** Talk counts, talk lengths and session formats have changed
  since 1971. Report rates per 10,000 words and the share of talks or speakers using a
  term, never raw counts alone.
- **Guard against one-speaker artifacts.** A phrase used 14 times by one speaker is a
  talk, not a trend. Each lexical insight reports distinct talks and distinct speakers,
  and "trend" requires at least 3 speakers unless flagged as single-speaker.
- **Local only, no API keys.** BGE-large on the 3090 for embeddings, `claude -p` for
  labeling. Talk text stays on ai-lab; only statistics and short quotes are published.
- **Resumable and idempotent stages**, same contract style as ldt-scribe.

---

## 3. Architecture

```
churchofjesuschrist.org ──scrape (text + footnotes)──┐
johnmwood CSV (1971–2018, bootstrap) ────────────────┤
ldt-scribe transcripts (provisional, same weekend) ──┤
                                                     v
                              corpus.db  (SQLite, the one source of truth)
                                                     │
        ┌──────────────┬──────────────┬──────────────┼──────────────┐
        v              v              v              v              v
   lexical        phrase/quote     citation       topic         scripture
   index          reuse index      graph          model         citations
        └──────────────┴──────────────┴──────┬───────┴──────────────┘
                                             v
                              insights.db  (facts, per conference)
                                             │
                    ┌────────────────────────┼─────────────────────┐
                    v                        v                     v
            report (HTML email)     JSON for ldt-conference    MCP / CLI queries
```

### Where it lives

Recommendation: build it in `conference-analysis`, which the ecosystem docs already
name as the NLP engine, and reuse its scraper and n-gram filtering. Have `ldt-search`
read `corpus.db` instead of keeping its own copy of the talks. Renaming the repo to
`ldt-insights` is optional and cosmetic.

### corpus.db schema

| Table | Key columns |
|---|---|
| `conferences` | `conf_id` (2026-10), year, month, president_of_church |
| `speakers` | `speaker_id`, canonical name, aliases |
| `talks` | `talk_id`, conf_id, speaker_id, calling_at_time, session, title, url, word_count, `source` (official / csv / scribe), `provisional` flag |
| `paragraphs` | talk_id, position, text |
| `footnotes` | talk_id, marker, paragraph position, raw text |
| `citations` | from talk_id → target type (scripture / talk / other), target id, parsed from footnotes |
| `quoted_spans` | talk_id, paragraph, span text, whether inside quotation marks |

`calling_at_time` matters: "what the President of the Church said" and "what the
Twelve said" are separate, useful cuts. `ldt-prophet` already holds apostle tenure
data that can fill it.

---

## 4. The five analysis layers

### 4.1 Words and phrases (new / rising / fading vocabulary)

For every 1–5-gram, per conference: rate per 10k words, talks using it, speakers using
it. The existing `_is_meaningful_phrase` stopword logic carries over.

Signals for the newest conference C against its baseline (the trailing 10 conferences,
with the full history as a second reference):

| Signal | Definition |
|---|---|
| **New** | never seen before C, used by ≥ 2 speakers |
| **Revived** | seen before, absent from the trailing 10 conferences, back in C |
| **Rising** | log-odds ratio with an informative Dirichlet prior (Monroe et al., "Fightin' Words") of C vs baseline above threshold. This handles rare words properly where raw percent change does not |
| **Continuing** | first appeared within the last 2–6 conferences and has stayed above its pre-entry rate in every conference since |
| **Fading** | a term that was "Rising" or "Continuing" in a recent conference and has since fallen back toward its old rate |
| **Absent** | a term in the top band of the baseline that did not appear at all in C |

Long-run trend (decades) is a separate, slower view: Mann-Kendall test on the
per-conference rate, which the two-period comparison in `trend_analysis.py`
approximates today.

### 4.2 Topics

BERTopic-style pipeline on paragraphs, reusing the BGE embeddings `ldt-search`
already computes: UMAP → HDBSCAN → c-TF-IDF keywords → a short label written by
`claude -p` from the keywords and five representative paragraphs.

- Paragraph-level, so each talk is a mixture of topics, not one label.
- **Freeze the taxonomy.** Fit once on 1971–present, version it, and assign new talks
  to existing topics. Refit at most yearly, with a mapping between versions, or trend
  lines will not be comparable across conferences.
- Paragraphs from a new conference that fit no existing topic, and cluster with each
  other, are the candidates for a **new topic**.
- Per conference: each topic's share of paragraphs and of talks, then the same
  New / Rising / Continuing / Fading / Absent signals as 4.1, computed on shares.

The hand-coded 10-topic breakdown of October 2026 (37 talks) is a useful sanity check
for the first fit.

### 4.3 Quotes that carry weight

Two independent sources, merged:

1. **Explicit citations** from footnotes: talk → talk and talk → scripture edges. This
   needs the re-scrape; it is the most reliable signal and gives exact attribution.
2. **Text reuse**: hash every 6–8-word shingle in the corpus. A shingle sequence that
   appears in talks by different speakers is a shared passage. Match against the
   scriptures DB first so that scripture quotations are attributed to scripture and
   removed from the talk-quote pool. The earliest remaining occurrence is the origin.
   Passages inside quotation marks get higher confidence.

Per quote: origin talk, number of later talks, distinct speakers, years spanned, uses
in the last 10 conferences, and whether it was used in C. That yields the all-time
leaderboard, the "most quoted from the last five years" list, and for each new
conference: which established quotes were repeated, and which lines from the previous
one or two conferences were already picked up by others.

Paraphrased echoes (same idea, different words) are a later addition using paragraph
embeddings; they are noisier and should not block the first version.

### 4.4 Scripture citations

From footnotes plus inline references, verified against the scriptures DB the same way
ldt-scribe verifies them. Per conference: most-cited books, chapters and verses, and
the same trend signals. This layer is cheap once footnotes exist.

### 4.5 Speaker and calling cuts

Every signal above can be filtered by speaker and by calling at the time. Examples:
phrases introduced by the President of the Church and their adoption curve among
other speakers in the following conferences; one speaker's topic mix over time.

---

## 5. The post-conference report

Produced twice:

- **Pass A, same weekend (provisional)**: from ldt-scribe transcripts of the broadcast
  audio. No footnotes, some recognition errors, so it covers words, phrases, topics and
  text-reuse quotes only, and is labeled provisional.
- **Pass B, when the Church publishes the text** (usually within days): official text
  and footnotes replace the provisional rows; citations and scripture trends are added.

Sections, each a ranked table with evidence links, followed by a short narration:

1. Headline: the 5–8 strongest signals across all layers.
2. New: words, phrases, topics, and quotable lines appearing for the first time.
3. Rising and revived.
4. Continuing: what entered recently and stuck.
5. Fading and absent.
6. Most-quoted: established quotes repeated this time; new lines from recent
   conferences already being cited.
7. Scriptures: most cited, and movers.
8. By speaker group: First Presidency, the Twelve, others.

Delivery: HTML email using the ldt-scribe email style, JSON written to
`ldt-data/data/public/` for `ldt-conference`, and optionally MCP tools
(`phrase_history`, `quote_lineage`, `topic_trend`) alongside `ldt-search`.

---

## 6. Build phases

| Phase | Deliverable | Done when |
|---|---|---|
| **0. Corpus** | `corpus.db` with every talk 1971–present, paragraphs, footnotes, normalized speakers; April and October 2026 included; the 624-talk gap explained | talk counts reconcile with the Church index per conference; a spot check of 20 talks matches the site |
| **1. Lexical signals** | n-gram index and the six signals; CLI `insights conference 2026-10` | backtests in section 7 pass |
| **2. Quotes and citations** | text-reuse index, citation graph, quote leaderboard, scripture trends | the Nelson 2016 quote is found with its later uses without being told what to look for |
| **3. Topics** | frozen topic model v1 with labels; per-conference shares; new-topic detection | labels reviewed by hand; refit stability checked on a held-out decade |
| **4. Report and automation** | Pass A and Pass B reports, email, `run-job` entry that fires on conference weekends | October 2026 report generated end to end from scribe transcripts |
| **5. Web** | JSON exports and the trend, quote and topic views in `ldt-conference` | replaces the "Coming Soon" block |

Phases 1 and 2 are independent of each other after Phase 0. Phase 1 can start on the
existing 4,266 talks before the re-scrape finishes, since it does not need footnotes.

---

## 7. Validation by backtest

Run the engine "as of" a past conference, hiding everything after it, and check that
it surfaces what is known in hindsight:

| As of | Should surface |
|---|---|
| April 2018 | "ministering", "covenant path" as new or rising |
| October 2020 – April 2021 | "let God prevail" as new, then continuing |
| October 2023 – April 2024 | "think celestial" as new, then a burst; "peacemaker" rising |
| October 2022 onward | "let God prevail" as fading |

The same backtests show the false-positive rate: how many "new" phrases per conference
went nowhere. That number sets the thresholds.

---

## 8. Risks and open decisions

**Risks**

- The 1971–2018 CSV has no footnotes and may differ from the current site text. The
  re-scrape fixes it but is about 4,900 page fetches, rate-limited.
- Session formats changed (priesthood and women's sessions were discontinued), which
  shifts the audience mix and therefore vocabulary. Trend claims that cross those
  changes need a note.
- Provisional transcripts contain recognition errors, especially names. A whisper
  misspelling must not be reported as a "new word"; Pass A should check new single
  words against a dictionary plus the scribe vocabulary lists.
- Many terms are tested at once, so some "significant" movers will be noise. The
  speaker-count floor and the backtest-calibrated thresholds are the defense.
- Talk text is the Church's intellectual property. Keep the corpus private; publish
  statistics, short attributed quotes and links only.

**Decisions for Clay**

1. Home: build in `conference-analysis` (recommended) or start a fresh `ldt-insights`
   repo through `dev-templates` and loop-dev?
2. Audience: private tool first, or designed from the start for the public
   `conference.latterdaytools.io` site?
3. Baseline window for "this conference vs recent": trailing 10 conferences (5 years)
   is the proposal; a 6-conference window reacts faster but is noisier.
4. Should Pass A (provisional, from audio) be emailed automatically, or only Pass B?
