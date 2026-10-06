# Conference Insights Engine kickoff prompt (loop-driven development)

Build the Conference Insights Engine to completion using loop-driven development.
SPEC.md is the goal state, CLAUDE.md has the data contracts and gotchas, and
docs/INSIGHTS_ENGINE_BLUEPRINT.md has the design rationale — read all three before
writing any code.

## The loop

Repeat until every Definition-of-DONE checkbox in SPEC.md is checked:

1. Pick the highest-value unfinished item from SPEC.md (work top to bottom unless
   something is blocked; the scrape is slow, so start it early and build against
   partial data while it runs).
2. Implement it.
3. Verify it for real — run pytest, run the actual pipeline against data/corpus.db,
   and inspect real output: open the numbers behind at least three insights and
   confirm them with an independent grep/SQL count; open the generated HTML and read it.
4. When verification fails, fix it AND update SPEC.md / tests so the same failure
   can't silently recur.
5. Check the boxes you've earned in SPEC.md, append one line per iteration to
   PROGRESS.md, and go to 1.

Do not stop early, do not stop to summarize, do not ask "should I continue?" — the
only finish line is the DONE checklist. If you hit a genuine blocker, write it to
BLOCKERS.md with what you tried, pick a different SPEC item, and keep looping. End
only when every box is checked or every remaining item is blocked.

## The army

Use subagents where work is independent (scraper vs. signal code vs. report
template). After each major stage, spawn a fresh-eyed verifier that tries to BREAK
the work. Failure modes to hunt: a count in the report that does not match the
database; a "new" phrase that is really a whisper mis-transcription or a speaker's
name; a "trend" driven by one speaker; a quote attributed to the wrong origin talk;
scripture text counted as a talk quote; talks double-counted across sources.
Before declaring DONE: a code review pass, then a completeness critic: "which SPEC
line is not actually satisfied end-to-end?"

## Autonomy contract

Decide yourself, without asking: library choices within SPEC constraints, naming,
layout, thresholds, test structure, anything reversible inside this repo. Record
each non-obvious call as one line in DECISIONS.md.

Never do, even if it seems helpful: write/delete/modify anything outside this repo
(except .venv and package caches) — in particular ~/code/ldt-scribe, ~/code/ldt-search,
~/code/ldt-data and this repo's legacy/ are READ-ONLY; delete data/raw/ (it is the
scrape cache and costs hours to rebuild); git push; sudo; add any API-key code path
(no OpenAI, no Anthropic key — LLM calls go through the `claude` CLI in -p mode
only); send audio or talk text to any third-party service; hammer
churchofjesuschrist.org (max 3 requests/second, one connection, honour errors with
backoff); publish or deploy anything.

Ask a human only if the SPEC is self-contradictory. Otherwise ship the flagged
fallback the SPEC allows and keep going.

## Ground rules

- Work on the current branch (feat/insights-engine). Commit after each verified
  loop iteration with a conventional-commit message. Never commit data/, legacy/
  or generated reports.
- Fewer lines wins; no premature abstraction; a junior dev should be able to read
  every file.
- Real data or it didn't happen: every feature must be demonstrated against the
  real corpus in data/corpus.db, not fixtures, before its box is checked.
- Numbers come from code, words come from the LLM. No number in any report may be
  produced by an LLM.
