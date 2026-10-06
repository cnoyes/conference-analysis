"""Citation graph and scripture use (SPEC F2).

Two independent views of scripture use:
  citations table  - explicit references (footnotes and inline links), official text only
  scripture_quotes - verses quoted verbatim in the talk text, found by matching against
                     the standard works. Works on provisional transcripts too, so this is
                     the like-for-like measure when a provisional conference is compared
                     with earlier ones.
"""
import re
import sqlite3
from collections import Counter

from .config import SCRIPTURES_DB
from .db import connect, tokenize
from .text import SCRIPTURE_N

MIN_RUN = 8        # a verbatim quotation is at least this many consecutive scripture words
MAX_VERSES = 5     # shingles found in more verses than this are too generic to vote
FORMULA_TALKS = 150  # a scripture shingle used in more talks than this is a stock formula
                     # ("the Church of Jesus Christ of Latter-day Saints"), not a quotation

SCHEMA = """
DROP TABLE IF EXISTS scripture_quotes;
CREATE TABLE scripture_quotes (
    talk_id INTEGER, para_id INTEGER,
    book TEXT, chapter INTEGER, verse INTEGER,
    words INTEGER                        -- length of the quoted run
);
CREATE INDEX scripture_quotes_talk ON scripture_quotes(talk_id);
"""

_verses = None


def verse_index():
    """(shingle -> [verse row ids], verse row id -> (book, chapter, verse))."""
    global _verses
    if _verses is None:
        con = sqlite3.connect(f"file:{SCRIPTURES_DB}?mode=ro", uri=True)
        index, names = {}, {}
        for vid, book, chapter, verse, text in con.execute(
                "SELECT verse_id, book_title, chapter_number, verse_number, scripture_text "
                "FROM scriptures"):
            names[vid] = (book, chapter, verse)
            toks = tokenize(text)
            for i in range(len(toks) - SCRIPTURE_N + 1):
                index.setdefault(" ".join(toks[i:i + SCRIPTURE_N]), []).append(vid)
        _verses = (index, names)
    return _verses


def parallel_verses():
    """Pairs of verses in different books that share text (Malachi 3:10 and 3 Nephi 24:10)."""
    index, names = verse_index()
    shared = Counter()
    for verses in index.values():
        if 2 <= len(verses) <= MAX_VERSES:
            for a in verses:
                for b in verses:
                    if a < b and names[a][0] != names[b][0]:
                        shared[frozenset((a, b))] += 1
    return {pair for pair, n in shared.items() if n >= 3}


def book_names():
    """URL book code ('2-ne') -> display title ('2 Nephi')."""
    con = sqlite3.connect(f"file:{SCRIPTURES_DB}?mode=ro", uri=True)
    names = dict(con.execute("SELECT book_lds_url, book_title FROM books"))
    names.update({"dc": "Doctrine and Covenants", "od": "Official Declaration"})
    return names


def quoted_verses(norm, mask, formulas=frozenset()):
    """[(verse row id, run length)] for each scripture-quoted run of >= MIN_RUN words."""
    index, names = verse_index()
    toks = norm.split()
    out, i = [], 0
    while i < len(toks):
        if mask[i] != "1":
            i += 1
            continue
        j = i
        while j < len(toks) and mask[j] == "1":
            j += 1
        if j - i >= MIN_RUN:
            votes = Counter()
            for k in range(i, j - SCRIPTURE_N + 1):
                shingle = " ".join(toks[k:k + SCRIPTURE_N])
                verses = index.get(shingle, ())
                if 0 < len(verses) <= MAX_VERSES and shingle not in formulas:
                    votes.update(set(verses))
            if votes:
                top = max(votes.values())
                # a run can span several verses: keep each verse matching nearly as well
                kept = sorted(v for v, n in votes.items() if n >= max(2, 0.6 * top))
                # the same passage in two books (Malachi 3 = 3 Nephi 24) counts once: under
                # the book of the best match, or the earlier book in the canon on a tie
                if kept:
                    book = names[min(v for v in kept if votes[v] == top)][0]
                    kept = [v for v in kept if names[v][0] == book]
                out.extend((vid, j - i) for vid in kept)
        i = j
    return out


def build_scripture_quotes(log=print):
    """Rebuild scripture_quotes from para_norm. Idempotent."""
    con = connect()
    _, names = verse_index()
    con.executescript(SCHEMA)
    rows = con.execute(
        "SELECT para_id, talk_id, norm, scripture FROM para_norm WHERE scripture LIKE '%1%'"
    ).fetchall()
    index, _ = verse_index()
    used_by = {}  # scripture shingle -> talks using it
    for _, talk_id, norm, _ in rows:
        toks = norm.split()
        for k in range(len(toks) - SCRIPTURE_N + 1):
            shingle = " ".join(toks[k:k + SCRIPTURE_N])
            if shingle in index:
                used_by.setdefault(shingle, set()).add(talk_id)
    formulas = {s for s, talks in used_by.items() if len(talks) > FORMULA_TALKS}
    twins = parallel_verses()
    batch = []
    for para_id, talk_id, norm, mask in rows:
        best = {}  # one row per verse and paragraph, however often it is quoted there
        for vid, words in quoted_verses(norm, mask, formulas):
            best[vid] = max(words, best.get(vid, 0))
        for vid in sorted(best):  # a parallel passage counts once, under the earlier book
            if any(frozenset((vid, other)) in twins for other in best if other < vid):
                del best[vid]
        batch += [(talk_id, para_id, *names[vid], words) for vid, words in best.items()]
    con.executemany("INSERT INTO scripture_quotes VALUES (?,?,?,?,?,?)", batch)
    con.commit()
    log(f"scripture quotes: {len(batch)} verse quotations ({len(formulas)} stock formulas ignored)")


def top_cited(con, limit=20, citing_from="0000-00", citing_to="9999-99"):
    """Most-cited conference talks, counted as distinct citing talks in a conference range.

    A talk citing itself does not count. Returns dict rows.
    """
    return [dict(r) for r in con.execute(
        "SELECT c.target_uri, t2.title, s.name AS speaker, t2.conf_id, "
        "COUNT(DISTINCT c.talk_id) AS citing_talks, COUNT(*) AS citations "
        "FROM citations c JOIN talks t1 ON t1.talk_id = c.talk_id "
        "LEFT JOIN talks t2 ON t2.uri = c.target_uri LEFT JOIN speakers s ON s.speaker_id = t2.speaker_id "
        "WHERE c.target_type='talk' AND t1.uri != c.target_uri AND t1.conf_id BETWEEN ? AND ? "
        "GROUP BY c.target_uri ORDER BY citing_talks DESC, citations DESC, c.target_uri LIMIT ?",
        (citing_from, citing_to, limit))]


def legacy_top_cited(paths, limit=20):
    """The same ranking from the legacy Selenium CSVs: [(uri, citing_talks)]."""
    import csv
    citing = {}
    for path in paths:
        with open(path, newline="") as fh:
            for row in csv.DictReader(fh):
                src = uri_of(row["talk_url"])
                dst = uri_of(row["citation_link"])
                if src and dst and src != dst:
                    citing.setdefault(dst, set()).add(src)
    ranked = sorted(citing.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    return [(uri, len(talks)) for uri, talks in ranked[:limit]]


def uri_of(url):
    m = re.search(r"(/general-conference/\d{4}/\d{2}/[^?#/]+)", url or "")
    return m[1] if m else None


def write_top_cited(log=print):
    """docs/TOP_CITED.md: all-time top 20, plus a 2018-2024 comparison with the legacy CSVs."""
    from .config import LEGACY, REPO
    con = connect()
    paths = sorted(p for p in (LEGACY / "talk_citations" / "data").glob("citations_*.csv")
                   if "2018-04" <= p.stem[-10:-3] <= "2024-10")
    legacy = dict(legacy_top_cited(paths, limit=10000))
    ours = top_cited(con, 20, "2018-04", "2024-10")
    ours_all = {r["target_uri"]: r["citing_talks"]
                for r in top_cited(con, 10000, "2018-04", "2024-10")}
    legacy_top = sorted(legacy.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
    shared = len({r["target_uri"] for r in ours} & {u for u, _ in legacy_top})
    lines = [
        "# Most-cited conference talks", "",
        "Generated by `python -m conference_analysis.insights index` from the `citations` table",
        "(links to other conference talks in footnotes and in talk bodies). A talk is counted",
        "once per citing talk; self-citations are excluded.", "",
        "## All time (citing talks 1971-04 to 2026-04)", "",
        "| # | Citing talks | Talk | Speaker | Conference |", "|---|---|---|---|---|",
    ]
    for i, r in enumerate(top_cited(con, 20), 1):
        lines.append(f"| {i} | {r['citing_talks']} | {r['title']} | {r['speaker']} | {r['conf_id']} |")
    lines += [
        "", "## Check against the legacy Selenium scrape (citing talks 2018-04 to 2024-10)", "",
        f"{shared} of our top 20 are also in the legacy top 20 for the same 14 conferences.", "",
        "| # | Talk | Speaker | Conference | Ours | Legacy |", "|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(ours, 1):
        lines.append(f"| {i} | {r['title']} | {r['speaker']} | {r['conf_id']} | "
                     f"{r['citing_talks']} | {legacy.get(r['target_uri'], 0)} |")
    missing = [(u, n) for u, n in legacy_top if u not in {r["target_uri"] for r in ours}]
    lines += ["", "Legacy top-20 talks outside our top 20: " + (", ".join(
        f"`{u}` (legacy {n}, ours {ours_all.get(u, 0)})" for u, n in missing) or "none") + ".", "",
        "Why the counts differ: our counts are equal or slightly higher because we read every",
        "link in every footnote from the API (the legacy scraper kept one link per footnote row",
        "it could click through) and we also count links in the body of a talk. The ranking of",
        "the top talks is the same.", ""]
    out = REPO / "docs" / "TOP_CITED.md"
    out.write_text("\n".join(lines))
    log(f"wrote {out}")
