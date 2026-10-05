"""Word and phrase signals for a target conference C (SPEC F1, blueprint 4.1).

Everything here reads only conferences with ordinal <= C, so running it "as of" a past
conference is an honest backtest.

Classes (precedence in this order; a term gets exactly one):
  new        never used before C, >= 2 speakers in C
  revived    used before, absent from the 10-conference baseline, >= 3 speakers in C
  continuing a run of 2-7 consecutive conferences ending at C at >= 3x the term's earlier
             rate (it entered recently and stuck), >= 3 speakers in C
  rising     log-odds z-score (C vs baseline, informative Dirichlet prior) >= RISING_Z on
             use counts and >= BREADTH_Z on speaker counts, rate >= 1.5x baseline,
             >= 3 speakers in C
  fading     was a burst (new, revived, continuing, or rising at >= 3x baseline, >= 3
             speakers) in one of the previous 6 conferences and is now at <= 40% of its
             recent peak rate
  absent     used in >= 8 of the 10 baseline conferences, expected >= 3 uses in C, used 0 times
Terms that would be new or rising but have too few speakers (1 for new, 1-2 for rising)
are reported apart as "single-speaker emphasis" (key 'single').
"""
import json

import numpy as np

from .config import BASELINE_N, DATA
from .db import conf_ordinal, connect
from .lexicon import in_dictionary
from .text import scripture_shingles

WINDOW = 33          # conferences of history loaded before C
PRIOR_WORDS = 1000   # alpha_0 of the Dirichlet prior, in pseudo-words
RISING_Z = 3.0       # on use counts
BREADTH_Z = 2.0      # on the number of speakers using the term
RUN_FACTOR = 3.0     # "continuing": each run conference is >= this multiple of the earlier rate
FADE_LOOKBACK = 6
FADE_RATIO = 0.4
TOP = 40             # terms kept per class
TITLES = {"president", "elder", "sister", "brother", "bishop", "presidents", "elders"}
SPOKEN = {"quote", "unquote"}
PROPER_OK = {"familysearch", "justserve", "covid", "seminary", "primary"}
CLASSES = ("new", "revived", "continuing", "rising", "fading", "absent")


class Window:
    """Dense term x conference matrices for ordinals [c - WINDOW, c]."""

    def __init__(self, con, c):
        self.c, self.lo = c, max(1, c - WINDOW)
        rows = np.array(con.execute(
            "SELECT term_id, ord, count, speakers FROM term_conf WHERE ord BETWEEN ? AND ?",
            (self.lo, c)).fetchall(), dtype=np.int64)
        self.term_ids, idx = np.unique(rows[:, 0], return_inverse=True)
        width = c - self.lo + 1
        self.count = np.zeros((len(self.term_ids), width))
        self.speakers = np.zeros((len(self.term_ids), width))
        self.count[idx, rows[:, 1] - self.lo] = rows[:, 2]
        self.speakers[idx, rows[:, 1] - self.lo] = rows[:, 3]
        words = dict(con.execute("SELECT ord, words FROM conf_stats WHERE ord <= ?", (c,)))
        self.words = np.array([words.get(o, 0) for o in range(self.lo, c + 1)], dtype=float)
        self.total_words = float(sum(words.values()))
        talks = dict(con.execute("SELECT ord, talks FROM conf_stats WHERE ord <= ?", (c,)))
        self.talks = np.array([talks.get(o, 0) for o in range(self.lo, c + 1)], dtype=float)
        self.rate = np.divide(self.count * 1e4, self.words, out=np.zeros_like(self.count),
                              where=self.words > 0)
        meta = {r[0]: r[1:] for r in con.execute("SELECT term_id, term, n, first_ord FROM terms")}
        self.terms = [meta[t][0] for t in self.term_ids]
        self.n = np.array([meta[t][1] for t in self.term_ids])
        self.first = np.array([meta[t][2] for t in self.term_ids])
        background = dict(con.execute(
            "SELECT term_id, SUM(count) FROM term_conf WHERE ord <= ? GROUP BY term_id", (c,)))
        self.background = np.array([background[t] for t in self.term_ids], dtype=float)

    def col(self, p):
        return p - self.lo

    def baseline(self, p):
        """Column slice for the 10 conferences before p."""
        return slice(max(0, self.col(p) - BASELINE_N), self.col(p))

    def z_scores(self, p):
        """Monroe et al. log-odds of conference p vs its baseline, as z-scores."""
        b = self.baseline(p)
        y_i, y_j = self.count[:, self.col(p)], self.count[:, b].sum(axis=1)
        n_i, n_j = self.words[self.col(p)], self.words[b].sum()
        alpha = PRIOR_WORDS * self.background / self.total_words
        delta = (np.log((y_i + alpha) / (n_i + PRIOR_WORDS - y_i - alpha))
                 - np.log((y_j + alpha) / (n_j + PRIOR_WORDS - y_j - alpha)))
        return delta / np.sqrt(1 / (y_i + alpha) + 1 / (y_j + alpha))

    def breadth_z(self, p):
        """The same log-odds z-score computed on how many speakers used the term."""
        b = self.baseline(p)
        y_i, y_j = self.speakers[:, self.col(p)], self.speakers[:, b].sum(axis=1)
        n_i, n_j = self.talks[self.col(p)], self.talks[b].sum()
        prior = 10.0
        alpha = prior * (y_i + y_j + 0.5) / (n_i + n_j)
        delta = (np.log((y_i + alpha) / np.maximum(n_i + prior - y_i - alpha, 0.5))
                 - np.log((y_j + alpha) / np.maximum(n_j + prior - y_j - alpha, 0.5)))
        return delta / np.sqrt(1 / (y_i + alpha) + 1 / (y_j + alpha))

    def run_length(self, p):
        """Consecutive conferences ending at p at >= RUN_FACTOR x the pre-window rate."""
        col = self.col(p)
        prior = self.rate[:, max(0, col - 26):max(0, col - 6)]
        prior_rate = prior.mean(axis=1) if prior.shape[1] else np.zeros(len(self.terms))
        run = np.zeros(len(self.terms), dtype=int)
        alive = np.ones(len(self.terms), dtype=bool)
        for k in range(col, max(-1, col - 8), -1):
            alive &= (self.count[:, k] > 0) & (self.rate[:, k] >= RUN_FACTOR * prior_rate)
            run += alive
        return run

    def classes_at(self, p):
        """Boolean arrays for new / revived / continuing / rising at conference p."""
        col, b = self.col(p), self.baseline(p)
        count, speakers = self.count[:, col], self.speakers[:, col]
        base = self.count[:, b].sum(axis=1)
        base_rate = base * 1e4 / max(self.words[b].sum(), 1)
        z = self.z_scores(p)
        new = (self.first == p) & (speakers >= 2)
        revived = (self.first < p) & (base == 0) & (count > 0) & (speakers >= 3)
        run = self.run_length(p)
        cols = np.arange(self.count.shape[1])[None, :]
        run_total = (self.count * ((cols > col - run[:, None]) & (cols <= col))).sum(axis=1)
        continuing = ((run >= 2) & (run <= 7) & (speakers >= 3) & (count >= 4)
                      & (run_total >= 8) & ~new & ~revived)
        zb = self.breadth_z(p)
        strong = (base > 0) & (z >= RISING_Z) & (count >= 4) & (self.rate[:, col] >= 1.5 * base_rate)
        rising = strong & (speakers >= 3) & (zb >= BREADTH_Z) & ~continuing
        narrow = (strong & (speakers < 3)) | ((self.first == p) & (speakers == 1))
        burst = new | revived | continuing | (rising & (self.rate[:, col] >= 3 * base_rate))
        return {"new": new, "revived": revived, "continuing": continuing, "rising": rising,
                "burst": burst & (speakers >= 3), "narrow": narrow & (count >= 5), "zb": zb,
                "z": z, "base_rate": base_rate, "run": run}


class Guards:
    """Deterministic exclusions: speaker names, proper nouns, transcription junk."""

    def __init__(self, con, c, provisional):
        self.c, self.provisional = c, provisional
        names = set()
        for (name,) in con.execute("SELECT name_key FROM speakers"):
            names.update(tok for tok in name.split() if len(tok) > 1)
        self.names = names
        self.vocab = {r[0]: r[1:] for r in con.execute(
            "SELECT word, first_ord, cap_mid, lower_mid FROM vocab")}
        self.scripture_vocab = scripture_shingles()[1]

    def is_name(self, tok):
        """A person or place name: capitalised mid-sentence >= 90% of the time.

        Speaker-name tokens need nothing more; other words must also be absent from the
        dictionary, the scriptures and the allow-list (so Easter, Nephi, Christlike survive).
        """
        tok = tok.removesuffix("'s")
        _, cap, lower = self.vocab.get(tok, (0, 0, 0))
        mostly_cap = cap >= 2 and cap >= 9 * lower
        if tok in self.names:
            return mostly_cap or not in_dictionary(tok)
        if tok.startswith("christ") or tok in PROPER_OK:
            return False
        return mostly_cap and not in_dictionary(tok) and tok not in self.scripture_vocab

    def reject(self, term):
        """Reason this term may not be reported, or None."""
        toks = term.split()
        if any(len(t) == 1 for t in toks) or any(self.is_name(t) for t in toks):
            return "name"
        if any(t in TITLES for t in toks) and any(t.removesuffix("'s") in self.names for t in toks):
            return "name"
        if self.provisional:  # spoken quote markers; unknown words never seen in the corpus
            if any(t in SPOKEN for t in toks):
                return "transcript artefact"
            for t in toks:
                seen_before = self.vocab.get(t, (self.c,))[0] < self.c
                if not seen_before and not in_dictionary(t):
                    return "not a known word"
        return None


def fragments(terms, weight):
    """Terms that are mostly a piece of a longer indexed phrase ('stake high' of 'stake high priests')."""
    best = {}  # sub-phrase -> largest weight of a one-word-longer phrase containing it
    for term, wt in zip(terms, weight):
        if wt > 0 and " " in term:
            for sub in (term.rsplit(" ", 1)[0], term.split(" ", 1)[1]):
                if wt > best.get(sub, 0):
                    best[sub] = wt
    return {t for t, wt in zip(terms, weight) if wt > 0 and best.get(t, 0) >= 0.7 * wt}


def dedupe(records):
    """Drop a term when an already-kept term contains it (or vice versa) in mostly the same talks."""
    kept = []
    for r in records:
        padded = f" {r['term']} "
        clash = any((padded in f" {k['term']} " or f" {k['term']} " in padded)
                    and min(r["key"], k["key"]) >= 0.6 * max(r["key"], k["key"]) for k in kept)
        if not clash:
            kept.append(r)
    return kept


def lexical_signals(con, conf_id, top=TOP, full=False):
    """All six classes plus single-speaker emphasis for conference conf_id.

    full=True returns every qualifying term, unranked cut-offs and de-duplication off.
    """
    c = conf_ordinal(conf_id)
    provisional = con.execute("SELECT provisional FROM conferences WHERE conf_id=?",
                              (conf_id,)).fetchone()[0]
    w = Window(con, c)
    guards = Guards(con, c, provisional)
    col, b = w.col(c), w.baseline(c)
    now = w.classes_at(c)
    count, speakers, rate = w.count[:, col], w.speakers[:, col], w.rate[:, col]
    base_confs = (w.count[:, b] > 0).sum(axis=1)
    expected = now["base_rate"] * w.words[col] / 1e4

    # fading: a recent burst that has fallen back
    burst = np.zeros(len(w.terms), dtype=bool)
    for p in range(max(w.lo + 4, c - FADE_LOOKBACK), c):
        burst |= w.classes_at(p)["burst"]
    recent = w.rate[:, max(0, col - FADE_LOOKBACK):col]
    peak = recent.max(axis=1) if recent.shape[1] else np.zeros(len(w.terms))
    current = now["new"] | now["revived"] | now["continuing"] | now["rising"]
    fading = burst & (rate <= FADE_RATIO * peak) & ~current
    absent = (count == 0) & (base_confs >= min(8, b.stop - b.start)) & (expected >= 3) & ~fading
    single = now["narrow"]

    order = {
        "new": speakers * 1000 + count, "revived": speakers * 1000 + count,
        "continuing": now["z"], "rising": now["zb"] + now["z"] / 100,
        "fading": (peak - rate) * w.words[col] / 1e4, "absent": expected, "single": count,
    }
    masks = dict(now, fading=fading, absent=absent, single=single)
    base_sum = w.count[:, b].sum(axis=1)
    out = {}
    for cls in CLASSES + ("single",):
        weight = base_sum if cls in ("fading", "absent") else count
        fragment = fragments(w.terms, weight)
        idx = np.flatnonzero(masks[cls])
        idx = idx[np.argsort(-order[cls][idx], kind="stable")]
        records = []
        for i in idx:
            if not full and len(records) >= top * 3:
                break
            term = w.terms[i]
            if term in fragment or guards.reject(term):
                continue
            if provisional and cls in ("fading", "absent") and "'" in term:
                continue  # possessives are spelled differently in transcripts
            base_speakers = w.speakers[i, b]
            records.append({
                "term": term, "n": int(w.n[i]), "class": cls,
                "count": int(count[i]), "speakers": int(speakers[i]),
                "rate": round(float(rate[i]), 3),
                "base_count": int(w.count[i, b].sum()),
                "base_rate": round(float(now["base_rate"][i]), 3),
                "base_confs": int(base_confs[i]),
                "peak_rate": round(float(peak[i]), 3),
                "expected": round(float(expected[i]), 1),
                "z": round(float(now["z"][i]), 2), "zb": round(float(now["zb"][i]), 2), "run": int(now["run"][i]),
                "first_ord": int(w.first[i]),
                "key": float(max(speakers[i], base_speakers.max() if base_speakers.size else 0)),
            })
        out[cls] = records if full else dedupe(records)[:top]
    return out


def term_class(con, conf_id, term):
    """Class of one term as of conf_id (used by backtests), or None."""
    for cls, records in lexical_signals(con, conf_id, full=True).items():
        if any(r["term"] == term for r in records):
            return cls
    return None


def signals_path(conf_id):
    return DATA / "signals" / f"{conf_id}.json"


def compute_signals(conf_id, log=print):
    """Compute every layer's signals for a conference and cache them as JSON."""
    con = connect()
    result = {"conf_id": conf_id, "lexical": lexical_signals(con, conf_id)}
    path = signals_path(conf_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1))
    return result


def print_signals(conf_id):
    result = compute_signals(conf_id)
    for cls, records in result["lexical"].items():
        print(f"\n== {cls.upper()} ({len(records)}) ==")
        for r in records[:20]:
            print(f"  {r['term']:<40} uses {r['count']:>3}  speakers {r['speakers']:>2}  "
                  f"rate {r['rate']:>6.2f}  baseline {r['base_rate']:>6.2f}  z {r['z']:>5.1f}")
