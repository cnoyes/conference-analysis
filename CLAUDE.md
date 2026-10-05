# CLAUDE.md

This file provides **mandatory instructions** to Claude Code (claude.ai/code) when working with code in this repository.

---

## 🌐 CENTRAL DOCUMENTATION

**BEFORE MAKING ANY CHANGES**, read the ecosystem documentation in ldt-data:

```
../ldt-data/docs/ECOSYSTEM.md  - All repos and architecture
../ldt-data/docs/ROADMAP.md    - Phases and priorities
```

Or on GitHub: https://github.com/cnoyes/ldt-data/tree/main/docs

This ensures you understand how this repo fits into the larger LatterDay Tools ecosystem.

---

## Project Overview

**conference-analysis** is a Python NLP toolkit for deep analysis of LDS General Conference talks.

**Features**:
- Web scraping from churchofjesuschrist.org (4,890 talks, 1971-2025)
- Sentence embeddings (sentence-transformers)
- Temporal word/phrase frequency analysis
- Trend discovery (increasing/decreasing terms over decades)
- Topic clustering with K-Means and DBSCAN
- Interactive Plotly visualizations

**Tech Stack**: Python, sentence-transformers, pandas, plotly, scikit-learn

**Relationship to ldt-conference**:
- This repo = NLP analysis engine (command line / Jupyter)
- ldt-conference = Web UI that displays results
- Future work will connect them via ldt-data exports

---

## Key Commands

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Scrape talks (first time)
python -m conference_analysis.scraper

# Run analysis in Jupyter
jupyter notebook notebooks/

# Run trend analysis
python -c "from conference_analysis import trend_analysis; ..."
```

---

## Architecture

```
src/conference_analysis/
├── scraper.py           # Web scraping from Church website
├── embeddings.py        # Sentence embeddings and semantic search
├── temporal_analysis.py # Word frequency over time
├── trend_analysis.py    # Systematic trend discovery
└── example.py           # Usage examples

notebooks/
├── 01_exploration.ipynb     # Interactive tutorial
└── 02_trend_analysis.ipynb  # Comprehensive trend analysis

data/
├── raw/talks.csv            # Scraped talks (gitignored)
└── processed/embeddings*.pkl # Cached embeddings (gitignored)
```

---

## Key Capabilities

### Embeddings (embeddings.py)
```python
from conference_analysis.embeddings import EmbeddingsAnalyzer
analyzer = EmbeddingsAnalyzer()
results = analyzer.semantic_search("faith during trials", top_k=10)
```

### Temporal Analysis (temporal_analysis.py)
```python
from conference_analysis.temporal_analysis import TemporalAnalyzer
analyzer = TemporalAnalyzer()
analyzer.plot_word_frequency("repentance", by="decade")
```

### Trend Analysis (trend_analysis.py)
```python
from conference_analysis.trend_analysis import TrendAnalyzer
analyzer = TrendAnalyzer()
increasing = analyzer.find_increasing_words(top_n=20)
```

---

## Related Repos

- **ldt-data** - Central documentation hub; will receive exports from this repo
- **ldt-conference** - Web UI that will display analysis results

---

## Insights engine (loop-dev build, started 2026-10-05)

SPEC.md is the goal; PROMPT.md is the loop manual; docs/INSIGHTS_ENGINE_BLUEPRINT.md
is the rationale. Work happens on branch `feat/insights-engine`.

### Hard-won facts — do not re-derive

- **Church content API (no browser needed, footnotes included):**
  `https://www.churchofjesuschrist.org/study/api/v3/language-pages/type/content?lang=eng&uri=<URI>`
  - Conference index: `uri=/general-conference/1971/04` → `content.body` is HTML whose
    links `/study/general-conference/YYYY/MM/<slug>` are that conference's items
    (talks AND non-talks such as `audit-report`, session pages).
  - Talk: `uri=/general-conference/2016/10/joy-and-spiritual-survival` →
    `content.body` (HTML, paragraphs carry `data-aid` / `id="p1"`…), `content.footnotes`
    (dict keyed `note1`…: `marker`, `text` HTML, `referenceUris` list with `type`
    e.g. `scripture-ref` and `href`), `meta.title`, `meta.structuredData`.
  - Send a browser-like User-Agent. Verified working 2026-10-05.
  - `/general-conference/2026/10` currently lists only the four session pages — the
    talks are NOT published yet. Do not treat that as a scraper bug.
- **October 2026 text** comes from ldt-scribe: `~/code/ldt-scribe/meetings/2026-10-03-general-conference-saturday-{morning,afternoon}-session/talks/*.md`
  and `~/code/ldt-scribe/meetings/2026-10-04-general-conference-sunday-{morning,afternoon}-session-october-2026/talks/*.md`
  (8 + 10 + 9 + 10 = 37 talks). Each file: YAML front matter (`speaker`, `talk`,
  `date`, `words`, …) then the verbatim transcript. They are whisper transcripts:
  expect occasional doubled words and stray tokens; names were corrected.
  Skip `...sunday-morning-session-president-oaks-october-2026` (a partial duplicate).
- **Legacy work** (read-only, copied from Google Drive 2026-10-05) in `legacy/`:
  `conference/talks.R` (rvest scraper), `conference/talks.rds` (4,127 talks,
  1971-04 → 2024-10, 7.3M words; exported as `legacy/talks_rds.json` and
  `legacy/talks_rds_index.csv`), a Shiny word-cloud app, `gospel_topics/analysis.R`
  (50-topic LDA), `talk_citations/` (Selenium footnote scraper + talk→talk citation
  CSVs for 19 conferences: 2012-10 and 2016-04 → 2024-10).
- **Other local text** (read-only): `~/code/ldt-search/data/raw/` has the johnmwood
  CSV (1971–2018) and 495 scraped JSON talks (2019–2025); `lds-scriptures.db` there
  is the scripture text for excluding scripture quotations.
- **No API keys on this machine.** LLM = `/home/clay/.local/bin/claude -p`.
  Embeddings = sentence-transformers on the RTX 3090 (shared with a whisper cron).
- Known phrase histories for sanity checks (substring counts on the old corpus):
  "covenant path" 4 talks in 2017 then 15–25/yr; "think celestial" 1 (2023), 10
  (2024), 1 (2025); "let God prevail" 1 (2020), 11 (2021), 7 (2022); Nelson joy
  quote: origin 2016-10 + 11 later talks.
- The MANDATORY PRACTICES above about GitHub issues do not apply to the loop;
  commit on `feat/insights-engine`, never push.

### Insights engine — data contracts and gotchas (added by the loop, 2026-10-05)

Run order and commands: README "Insights engine". Decisions and thresholds: DECISIONS.md.

**corpus.db tables** (schema in `insights/db.py`): `conferences(conf_id, ordinal, provisional)`
(ordinal 1 = 1971-04, 112 = 2026-10), `speakers`, `talks` (`kind`: address/business/session/other;
`source`: api/scribe/historical; `calling_group`), `paragraphs`, `footnotes`, `citations`
(`fn_id` NULL = link in the talk body), `para_norm` (token view: `norm`, `clean`, `quoted`,
`scripture`), `terms`/`term_conf`/`conf_stats`/`vocab` (n-gram index), `quotes`/`quote_uses`,
`scripture_quotes`, `chunks`/`chunk_topics` (topic passages). `talk_id` = ordinal × 100 +
position; `para_id`/`chunk_id` = talk_id × 1000 + n. Everything except `speakers` is rebuilt
deterministically, so ids are stable.

- **A "use" of a phrase** = occurrence of `' phrase '` in `' ' || para_norm.clean || ' '`
  (overlapping occurrences count). `clean` has `|` at sentence ends and in place of scripture
  quotations, so counts never span sentences or include quoted scripture. Any reported count
  can be reproduced with that one SQL expression.
- **API**: `meta.structuredData` (JSON) holds the clean author name; `referenceUris` in
  footnotes is incomplete — parse the `href`s in the footnote HTML. Old talks carry
  scripture links in the body, not in footnotes. Talk→talk links first appear in 1976 and
  are sparse before 2010. Recent URIs look like `/general-conference/2022/04/47nelson`.
  The first uncached fetch of old pages is slow (~1 s each); the whole scrape took ~45 min.
- **Non-talks**: `data-content-type` separates sessions and business items; sustainings and
  reports typed as talks are caught by title (`BUSINESS_TITLE` in `build.py`).
- **Scribe transcripts**: no titles, no footnotes; `program.yaml` in each session folder has
  the callings. Whisper artefacts handled at ingest/tokenising: doubled words and 2–3-word
  phrases, spoken "quote … close quote", one hallucinated "© transcript …" paragraph.
  Whisper spells some words differently from the official text (possessives, worshiped/
  worshipped), which can split a phrase's or quote's history.
- **Word counts**: `talks.word_count` is raw words; `conf_stats.words` excludes quoted
  scripture (and collapsed doubles) and is the denominator for every rate.
- **Topic model v1** is frozen in `data/topics/v1/` (centroids, topics, labels, meta).
  `topics fit` refuses to overwrite it. Label/boilerplate corrections from review live in
  `topics.REVIEWED` (code), not in `labels.json`. Embedding cache: `data/embeddings/` (keyed
  by sha1 of passage text; ~4 min for the full corpus on the 3090, ~4 GB VRAM).
- **LLM cache**: `data/llm_cache/` keyed by prompt. Deleting it re-asks `claude -p` and may
  change labels, screening and sentences (never numbers).
- **Workspace hook gotcha**: a RankView safety hook blocks any Bash command that mentions
  the word for the SQLite CLI/module together with an SQL write keyword (even inside a
  heredoc that only edits a Python file). Edit such files with the Edit/Write tools and run
  read-only queries from a script file.
- **Seasonality**: Easter words/topics spike every April. Fading ignores seasonal words;
  seasonal topics are compared with same-month conferences.
- **Known limits**: scripture quotations under 6 words are not masked; a quote's "origin" is
  the earliest use since 1971 (flag `origin_quoted` = that speaker was already quoting);
  the peacemakers backtest in SPEC was amended (see SPEC changelog).
