"""1-5-gram index per conference (tables terms, term_conf, conf_stats, vocab)."""
import re
from collections import Counter, defaultdict

from ..trend_analysis import TrendAnalyzer
from .db import connect, tokenize
from .lexicon import stopwords
from .text import build_para_norm

MAX_N = 5
MIN_TALKS = 2  # an n-gram is indexed only if at least this many talks ever used it

SCHEMA = """
DROP TABLE IF EXISTS terms; DROP TABLE IF EXISTS term_conf;
DROP TABLE IF EXISTS conf_stats; DROP TABLE IF EXISTS vocab;
CREATE TABLE terms (
    term_id INTEGER PRIMARY KEY, term TEXT UNIQUE, n INTEGER,
    first_ord INTEGER,              -- conference ordinal of first use
    total_count INTEGER, total_talks INTEGER
);
CREATE TABLE term_conf (
    term_id INTEGER, ord INTEGER, count INTEGER, talks INTEGER, speakers INTEGER,
    PRIMARY KEY (term_id, ord)
) WITHOUT ROWID;
CREATE INDEX term_conf_ord ON term_conf(ord);
CREATE TABLE conf_stats (ord INTEGER PRIMARY KEY, conf_id TEXT, words INTEGER,
                         talks INTEGER, speakers INTEGER);
CREATE TABLE vocab (                -- every word ever used, with capitalisation evidence
    word TEXT PRIMARY KEY, total INTEGER, first_ord INTEGER,
    cap_mid INTEGER,                -- times capitalised in the middle of a sentence
    lower_mid INTEGER               -- times lower-case in the middle of a sentence
);
"""

MID_WORD = re.compile(r"(?<=[a-z,;] )([A-Za-z]+(?:['’][a-z]+)*)")


def meaningful(term, n):
    """The repo's existing stopword-position rule (trend_analysis._is_meaningful_phrase)."""
    return TrendAnalyzer._is_meaningful_phrase(None, term, n, stopwords())


def talk_ngrams(clean_paragraphs):
    """Counter of every meaningful 1-5-gram in one talk. '|' and paragraph ends break n-grams."""
    counts = Counter()
    for para in clean_paragraphs:
        for segment in para.split("|"):
            toks = segment.split()
            for n in range(1, MAX_N + 1):
                for i in range(len(toks) - n + 1):
                    counts[" ".join(toks[i:i + n])] += 1
    return Counter({t: c for t, c in counts.items() if meaningful(t, t.count(" ") + 1)})


def iter_talks(con):
    """Yield (ord, talk_id, speaker_id, [clean paragraph, ...]) for every address, oldest first."""
    talks = con.execute(
        "SELECT c.ordinal, t.talk_id, t.speaker_id FROM talks t JOIN conferences c USING (conf_id) "
        "WHERE t.kind='address' ORDER BY c.ordinal, t.position").fetchall()
    for ordinal, talk_id, speaker_id in talks:
        paras = [r[0] for r in con.execute(
            "SELECT clean FROM para_norm WHERE talk_id=? ORDER BY para_id", (talk_id,))]
        yield ordinal, talk_id, speaker_id, paras


def build_index(log=print):
    """Rebuild the whole n-gram index from para_norm. Idempotent (drops and recreates)."""
    con = connect()
    build_para_norm(con, log)

    # Pass 1: how many talks use each n-gram (hashes only, to keep memory modest).
    seen, keep = set(), set()
    n_talks = 0
    for ordinal, talk_id, speaker_id, paras in iter_talks(con):
        counts = talk_ngrams(paras)
        n_talks += 1
        for term in counts:
            h = hash(term)
            if h in seen:
                keep.add(h)
            else:
                seen.add(h)
    log(f"pass 1: {n_talks} talks, {len(seen)} distinct n-grams, {len(keep)} in >= {MIN_TALKS} talks")
    del seen

    # Pass 2: per-conference counts for the kept n-grams.
    con.executescript(SCHEMA)
    term_ids, totals = {}, {}
    conf = defaultdict(lambda: [0, 0, set()])  # term -> [count, talks, speakers]
    stats = {}                                  # ord -> [words, talks, speakers]

    def flush(ordinal):
        rows = []
        for term, (count, talks, speakers) in conf.items():
            if term not in term_ids:
                term_ids[term] = len(term_ids) + 1
                totals[term] = [ordinal, 0, 0]
            totals[term][1] += count
            totals[term][2] += talks
            rows.append((term_ids[term], ordinal, count, talks, len(speakers)))
        con.executemany("INSERT INTO term_conf VALUES (?,?,?,?,?)", rows)
        conf.clear()

    current = None
    for ordinal, talk_id, speaker_id, paras in iter_talks(con):
        if current is not None and ordinal != current:
            flush(current)
        current = ordinal
        s = stats.setdefault(ordinal, [0, 0, set()])
        s[0] += sum(len(p.replace("|", " ").split()) for p in paras)
        s[1] += 1
        s[2].add(speaker_id)
        for term, count in talk_ngrams(paras).items():
            if hash(term) in keep:
                entry = conf[term]
                entry[0] += count
                entry[1] += 1
                entry[2].add(speaker_id)
    if current is not None:
        flush(current)

    con.executemany("INSERT INTO terms VALUES (?,?,?,?,?,?)",
                    [(tid, term, term.count(" ") + 1, *totals[term]) for term, tid in term_ids.items()])
    con.executemany(
        "INSERT INTO conf_stats SELECT ?, conf_id, ?, ?, ? FROM conferences WHERE ordinal=?",
        [(o, s[0], s[1], len(s[2]), o) for o, s in stats.items()])
    build_vocab(con)
    con.commit()
    log(f"indexed {len(term_ids)} n-grams across {len(stats)} conferences")


def build_vocab(con):
    """Every word with first use and mid-sentence capitalisation counts (proper-noun evidence)."""
    vocab = {}  # word -> [total, first_ord, cap_mid, lower_mid]
    rows = con.execute(
        "SELECT c.ordinal, p.text FROM paragraphs p JOIN talks t USING (talk_id) "
        "JOIN conferences c USING (conf_id) WHERE t.kind='address' ORDER BY c.ordinal")
    for ordinal, text in rows:
        for word in tokenize(text):
            entry = vocab.setdefault(word, [0, ordinal, 0, 0])
            entry[0] += 1
        for raw in MID_WORD.findall(text):
            entry = vocab.get(raw.lower().replace("’", "'"))
            if entry:
                entry[2 if raw[0].isupper() else 3] += 1
    con.executemany("INSERT INTO vocab VALUES (?,?,?,?,?)",
                    [(w, *e) for w, e in vocab.items()])


def phrase_history(con, text):
    """Per-conference use of any phrase, counted directly on para_norm.clean.

    Returns [(conf_id, count, talks, speakers)] for conferences where it occurs.
    """
    needle = " " + " ".join(tokenize(text)) + " "
    rows = con.execute(
        "SELECT t.conf_id, t.talk_id, t.speaker_id, n.clean FROM para_norm n "
        "JOIN talks t USING (talk_id) WHERE instr(' ' || n.clean || ' ', ?) > 0 "
        "ORDER BY t.conf_id", (needle,)).fetchall()
    out = {}
    for conf_id, talk_id, speaker_id, clean in rows:
        entry = out.setdefault(conf_id, [0, set(), set()])
        entry[0] += count_occurrences(" " + clean + " ", needle)
        entry[1].add(talk_id)
        entry[2].add(speaker_id)
    return [(c, e[0], len(e[1]), len(e[2])) for c, e in sorted(out.items())]


def count_occurrences(haystack, needle):
    """Overlapping-safe count of a space-delimited phrase."""
    count, start = 0, haystack.find(needle)
    while start != -1:
        count += 1
        start = haystack.find(needle, start + 1)
    return count


def print_phrase(text):
    con = connect()
    history = phrase_history(con, text)
    if not history:
        print(f'"{text}": never used (outside scripture quotations)')
        return
    print(f'"{text}": {sum(h[1] for h in history)} uses in {sum(h[2] for h in history)} talks, '
          f"first {history[0][0]}, last {history[-1][0]}")
    print("conference  uses  talks  speakers")
    for conf_id, count, talks, speakers in history:
        print(f"{conf_id}    {count:5d}  {talks:5d}  {speakers:8d}")
