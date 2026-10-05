"""Text-reuse quote index (SPEC F2): passages shared by talks from different speakers.

Method: hash every 7-word shingle of every address (never crossing a paragraph, never
touching scripture-quoted words). A shingle used by two or more different speakers is
shared; its earliest use is the origin. Runs of shared shingles in the origin talk are
cut into quotes around the most-reused spot. A passage counts as a *quote* (not a stock
phrase such as "in the name of Jesus Christ, amen") when later talks mostly put it
inside quotation marks.
"""
import re
from collections import defaultdict

import numpy as np

from .db import connect, tokenize
from .text import scripture_coverage

K = 7                 # shingle length in words
MIN_LATER = 2         # a quote needs this many later talks by other speakers
MIN_QUOTED = 0.5      # share of later (official-text) uses that sit inside quotation marks
SCRIPTURE_SHARE = 0.6 # a passage this covered by 4-word scripture sequences is scripture
MAX_WORDS = 40        # longest quote text shown anywhere
MIN_WORDS = 9         # shorter shared passages are titles or fragments, not quotes

SCHEMA = """
DROP TABLE IF EXISTS quotes; DROP TABLE IF EXISTS quote_uses;
CREATE TABLE quotes (
    quote_id INTEGER PRIMARY KEY,
    origin_talk_id INTEGER, origin_para_id INTEGER,
    tok_start INTEGER, tok_end INTEGER,   -- token span inside the origin paragraph's norm
    text TEXT,                            -- the span, normalised tokens
    later_talks INTEGER,                  -- later talks by other speakers
    later_speakers INTEGER,               -- distinct other speakers
    origin_ord INTEGER, last_ord INTEGER,
    origin_quoted INTEGER,                -- 1 = the earliest use is itself inside quotation
                                          --     marks (the speaker was quoting someone else)
    quoted_share REAL                     -- share of later official uses inside quote marks
);
CREATE TABLE quote_uses (
    quote_id INTEGER, talk_id INTEGER,
    words INTEGER,                        -- words of the quote this talk shares (>= 7)
    PRIMARY KEY (quote_id, talk_id));
CREATE INDEX quote_uses_talk ON quote_uses(talk_id);
"""


def load_tokens(con):
    """Flat token arrays over every address, in chronological order."""
    rows = con.execute(
        "SELECT n.para_id, n.talk_id, t.speaker_id, c.ordinal, t.provisional, n.norm, n.quoted, "
        "n.scripture FROM para_norm n JOIN talks t USING (talk_id) JOIN conferences c USING (conf_id) "
        "ORDER BY c.ordinal, t.position, n.para_id").fetchall()
    vocab = {}
    ids, para, quoted, scripture = [], [], [], []
    paras = []  # per paragraph: (para_id, talk_id, speaker_id, ordinal, provisional, first token index)
    for para_id, talk_id, speaker_id, ordinal, provisional, norm, q, s in rows:
        toks = norm.split()
        paras.append((para_id, talk_id, speaker_id or -talk_id, ordinal, provisional, len(ids)))
        ids.extend(vocab.setdefault(t, len(vocab) + 1) for t in toks)
        para.extend([len(paras) - 1] * len(toks))
        quoted.extend(c == "1" for c in q)
        scripture.extend(c == "1" for c in s)
    return (np.array(ids, dtype=np.uint64), np.array(para), np.array(quoted),
            np.array(scripture), paras, vocab)


def shared_shingles(ids, para, scripture):
    """(origin_window, user_window) index pairs for every shingle reused later."""
    n = len(ids) - K + 1
    h = np.zeros(n, dtype=np.uint64)
    for k in range(K):
        h = h * np.uint64(1000003) + ids[k:k + n]
    bad = np.cumsum(np.concatenate([[0], scripture.astype(int)]))
    valid = (para[:n] == para[K - 1:]) & (bad[K:] - bad[:n] == 0)
    windows = np.flatnonzero(valid)
    order = windows[np.argsort(h[windows], kind="stable")]  # by hash, then position
    hs = h[order]
    start = np.flatnonzero(np.concatenate([[True], hs[1:] != hs[:-1]]))
    group = np.repeat(np.arange(len(start)), np.diff(np.concatenate([start, [len(order)]])))
    origin = order[start][group]
    reused = origin != order
    return origin[reused], order[reused]


def build_quotes(log=print):
    """Rebuild the quote tables from para_norm. Idempotent."""
    con = connect()
    ids, para, quoted, scripture, paras, vocab = load_tokens(con)
    talk = np.array([p[1] for p in paras])[para]
    speaker = np.array([p[2] for p in paras])[para]
    ordinal = np.array([p[3] for p in paras])[para]
    provisional = np.array([p[4] for p in paras])[para]
    origin, user = shared_shingles(ids, para, scripture)
    other = speaker[origin] != speaker[user]
    origin, user = origin[other], user[other]
    log(f"quotes: {len(ids)} tokens, {len(origin)} reused shingles across speakers")

    # origin window -> {later talk: [inside quotes?, provisional?, ordinal]}
    users = defaultdict(dict)
    mid = K // 2
    for o, u in zip(origin.tolist(), user.tolist()):
        entry = users[o].setdefault(int(talk[u]), [False, bool(provisional[u]), int(ordinal[u])])
        entry[0] |= bool(quoted[u + mid])

    con.executescript(SCHEMA)
    words = {i: w for w, i in vocab.items()}
    quote_id = 0
    windows = sorted(users)
    i = 0
    while i < len(windows):
        j = i  # run of consecutive origin windows in one paragraph
        while j + 1 < len(windows) and windows[j + 1] == windows[j] + 1 \
                and para[windows[j + 1]] == para[windows[i]]:
            j += 1
        run = windows[i:j + 1]
        free = [True] * len(run)
        while True:
            best = max((k for k in range(len(run)) if free[k]),
                       key=lambda k: len(users[run[k]]), default=None)
            if best is None or len(users[run[best]]) < MIN_LATER:
                break
            core = set(users[run[best]])
            lo = hi = best
            # grow while neighbours are reused by mostly the same talks, up to MAX_WORDS words,
            # so the stored quote (and its counts) is exactly the text that gets shown
            fits = lambda: hi - lo + K < MAX_WORDS
            while lo > 0 and free[lo - 1] and fits() \
                    and len(core & set(users[run[lo - 1]])) >= 0.5 * len(core):
                lo -= 1
            while hi + 1 < len(run) and free[hi + 1] and fits() \
                    and len(core & set(users[run[hi + 1]])) >= 0.5 * len(core):
                hi += 1
            for k in range(lo, hi + 1):
                free[k] = False
            later = {}  # talk -> [inside quotes?, provisional?, ordinal, shared windows]
            for k in range(lo, hi + 1):
                for t, (q, prov, o) in users[run[k]].items():
                    entry = later.setdefault(t, [False, prov, o, 0])
                    entry[0] |= q
                    entry[3] += 1
            official = [v[0] for v in later.values() if not v[1]]
            if len(official) < MIN_LATER:
                continue
            first, last = run[lo], run[hi] + K  # token span [first, last)
            if scripture_coverage([words[t] for t in ids[first:last].tolist()]) >= SCRIPTURE_SHARE:
                continue  # scripture stitched together with ellipses, not a talk quote
            p = paras[para[first]]
            quote_id += 1
            con.execute(
                "INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (quote_id, p[1], p[0], first - p[5], last - p[5],
                 "", len(later), 0, p[3], max(v[2] for v in later.values()),
                 int(quoted[first:last].mean() >= 0.5), sum(official) / len(official)))
            con.executemany("INSERT INTO quote_uses VALUES (?,?,?)",
                            [(quote_id, t, v[3] + K - 1) for t, v in later.items()])
        i = j + 1

    # fill text and distinct-speaker counts with SQL (simpler than carrying them above)
    for qid, para_id, a, b in con.execute(
            "SELECT quote_id, origin_para_id, tok_start, tok_end FROM quotes").fetchall():
        norm = con.execute("SELECT norm FROM para_norm WHERE para_id=?", (para_id,)).fetchone()[0]
        con.execute("UPDATE quotes SET text=? WHERE quote_id=?",
                    (" ".join(norm.split()[a:b]), qid))
    con.execute(
        "UPDATE quotes SET later_speakers = (SELECT COUNT(DISTINCT t.speaker_id) "
        "FROM quote_uses u JOIN talks t USING (talk_id) WHERE u.quote_id = quotes.quote_id)")
    con.commit()
    log(f"quotes: {quote_id} shared passages stored")


LEADER_SQL = """
SELECT q.quote_id, q.text, q.later_talks, q.later_speakers, q.origin_ord, q.last_ord,
       q.origin_quoted, q.quoted_share, t.talk_id, t.title, t.conf_id, s.name,
       q.origin_para_id, q.tok_start, q.tok_end
FROM quotes q JOIN talks t ON t.talk_id = q.origin_talk_id
LEFT JOIN speakers s USING (speaker_id)
WHERE q.quoted_share >= ? AND q.origin_ord >= ? AND q.origin_ord <= ?
ORDER BY q.later_speakers DESC, q.later_talks DESC, q.quote_id LIMIT ?
"""


def leaderboard(con, limit=25, since_ord=-10**6, until_ord=10**6, own_words_only=False):
    """Most-repeated quotes whose origin lies in [since_ord, until_ord].

    Quotes under MIN_WORDS words (titles, fragments) are skipped, and so is any quote reused
    by mostly the same talks as a higher-ranked one (another piece of the same passage;
    its text is kept under the surviving row's "pieces"). Several passages that one origin
    talk was itself quoting (a talk reading out a whole document) also count as one entry.
    """
    kept, kept_users = [], []
    for row in con.execute(LEADER_SQL, (MIN_QUOTED, since_ord, until_ord, limit * 20)):
        row = dict(row)
        if len(row["text"].split()) < MIN_WORDS or (own_words_only and row["origin_quoted"]):
            continue
        users = {r[0] for r in con.execute(
            "SELECT talk_id FROM quote_uses WHERE quote_id=?", (row["quote_id"],))}
        same = next((k for k, other in zip(kept, kept_users)
                     if len(users & other) >= 0.5 * min(len(users), len(other))
                     or (k["talk_id"] == row["talk_id"] and k["origin_quoted"]
                         and row["origin_quoted"])), None)
        if same:
            if same["talk_id"] == row["talk_id"]:
                same["pieces"].append(row["text"])
            continue
        row["pieces"] = [row["text"]]
        kept.append(row)
        kept_users.append(users)
        if len(kept) == limit:
            break
    return kept


def display_text(con, para_id, tok_start, tok_end, max_words=MAX_WORDS):
    """The original wording (case, punctuation) of a token span, capped at max_words."""
    text = con.execute("SELECT text FROM paragraphs WHERE para_id=?", (para_id,)).fetchone()[0]
    spans = [m.span() for m in re.finditer(r"[A-Za-z]+(?:['’][A-Za-z]+)*", text)]
    tok_end = min(tok_end, tok_start + max_words, len(spans))
    if tok_start >= tok_end:
        return ""
    return text[spans[tok_start][0]:spans[tok_end - 1][1]]


def quote_lineage(con, text):
    """Every talk containing the exact word sequence, oldest first (origin = first row)."""
    needle = " " + " ".join(tokenize(text)) + " "
    return [dict(r) for r in con.execute(
        "SELECT DISTINCT t.talk_id, t.conf_id, s.name AS speaker, t.title, t.provisional "
        "FROM para_norm n JOIN talks t USING (talk_id) JOIN conferences c USING (conf_id) "
        "LEFT JOIN speakers s USING (speaker_id) "
        "WHERE instr(' ' || n.norm || ' ', ?) > 0 ORDER BY c.ordinal, t.position", (needle,))]


def leaderboard_rank(con, talk_id, text):
    """(rank, row) of the all-time leaderboard passage from this origin talk containing text."""
    needle = " " + " ".join(tokenize(text)) + " "
    for rank, row in enumerate(leaderboard(con, limit=5000), 1):
        if row["talk_id"] == talk_id and any(needle in f" {piece} " for piece in row["pieces"]):
            return rank, row
    return None, None


def print_quote(text):
    con = connect()
    uses = quote_lineage(con, text)
    if not uses:
        print(f'"{text}": not found in any talk')
        return
    origin, later = uses[0], uses[1:]
    print(f'"{text}"')
    print(f"origin: {origin['conf_id']}  {origin['speaker']}, \"{origin['title']}\"")
    print(f"later talks: {len(later)} "
          f"({len({u['speaker'] for u in later} - {origin['speaker']})} other speakers)")
    for u in later:
        note = "  (provisional transcript)" if u["provisional"] else ""
        print(f"  {u['conf_id']}  {u['speaker']}, \"{u['title']}\"{note}")
    rank, row = leaderboard_rank(con, origin["talk_id"], text)
    if rank:
        print(f"all-time leaderboard rank: {rank} "
              f"({row['later_speakers']} other speakers, {row['later_talks']} later talks)")
