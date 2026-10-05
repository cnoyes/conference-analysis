"""Word and phrase signals for a target conference C (SPEC F1, blueprint 4.1).

Counts are read only from conferences with ordinal <= C, so running it "as of" a past
conference is an honest backtest of the classes. Two all-time inputs remain, and only
affect which candidates pass the guards: the index keeps n-grams that at least two talks
ever used, and the name guard uses the full speaker list and all-time capitalisation
counts.

Classes (precedence in this order; a term gets exactly one):
  new        never used before C, >= 2 speakers in C
  revived    used before, absent from the 10-conference baseline, >= 3 speakers in C
  continuing barely used before (<= 0.25 uses per 10k words), then a run of 2-7 consecutive
             conferences ending at C at >= 3x that earlier rate (it entered recently and
             stuck), >= 3 speakers in C
  rising     log-odds z-score (C vs baseline, informative Dirichlet prior) >= RISING_Z on
             use counts and >= BREADTH_Z on speaker counts, rate >= 1.5x baseline,
             >= 3 speakers in C
  fading     was a burst (new, revived, continuing, or rising at >= 3x baseline, >= 5
             speakers, no single talk supplying most uses) in one of the previous 6 conferences and is now at <= 40% of its
             recent peak rate; seasonal words (low every other conference) are excluded
  absent     used in >= 8 of the 10 baseline conferences, expected >= 3 uses in C, used 0 times
Terms that would be new or rising but are not broad enough (1 speaker for new; too few
speakers for rising), and terms of any class whose uses come mostly (> 60%) from one
talk, are reported apart as "single-speaker emphasis" (key 'single').
"""
import json

import numpy as np

from .config import BASELINE_N, DATA
from .db import conf_ordinal, connect
from .ngrams import count_occurrences
from .lexicon import in_dictionary
from .text import scripture_shingles

WINDOW = 33          # conferences of history loaded before C
PRIOR_WORDS = 1000   # alpha_0 of the Dirichlet prior, in pseudo-words
RISING_Z = 3.0       # on use counts
BREADTH_Z = 2.0      # on the number of speakers using the term
RUN_FACTOR = 3.0     # "continuing": each run conference is >= this multiple of the earlier rate
ENTRY_RATE = 0.25    # "continuing": earlier rate at most this (uses per 10k words, ~1 per conference)
FADE_LOOKBACK = 6
BURST_SPEAKERS = 5   # a past surge counts for "fading" only if this many speakers took part
FADE_RATIO = 0.4
MAX_TALK_SHARE = 0.6 # above this share of uses from one talk, a term is one talk's emphasis
TOP = 40             # terms kept per class
TITLES = {"president", "elder", "sister", "brother", "bishop", "presidents", "elders"}
SPOKEN = {"quote", "unquote"}
HONORIFICS = {"mr", "mrs", "ms", "dr"}
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
        """Consecutive conferences ending at p at >= RUN_FACTOR x the pre-window rate.

        Zero for terms that were already in regular use before the window.
        """
        col = self.col(p)
        prior = self.rate[:, max(0, col - 26):max(0, col - 6)]
        prior_rate = prior.mean(axis=1) if prior.shape[1] else np.zeros(len(self.terms))
        run = np.zeros(len(self.terms), dtype=int)
        alive = prior_rate <= ENTRY_RATE  # "entered recently" means it was barely used before
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
        continuing = ((run >= 2) & (run <= 7) & (speakers >= 3) & (count >= 5)
                      & (run_total >= 10) & ~new & ~revived)
        zb = self.breadth_z(p)
        strong = (base > 0) & (z >= RISING_Z) & (count >= 4) & (self.rate[:, col] >= 1.5 * base_rate)
        rising = strong & (speakers >= 3) & (zb >= BREADTH_Z) & ~continuing
        narrow = (strong & ~rising & ~continuing) | ((self.first == p) & (speakers == 1))
        burst = new | revived | continuing | (rising & (self.rate[:, col] >= 3 * base_rate))
        return {"new": new, "revived": revived, "continuing": continuing, "rising": rising,
                "burst": burst & (speakers >= BURST_SPEAKERS), "narrow": narrow & (count >= 5), "zb": zb,
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
        if any(len(t) == 1 or t in HONORIFICS for t in toks) or any(self.is_name(t) for t in toks):
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


class ConfText:
    """The tokenised talks of a conference, loaded on demand, for per-talk checks."""

    def __init__(self, con):
        self.con, self.cache, self.norm = con, {}, {}

    def talks(self, ordinal):
        if ordinal not in self.cache:
            talks = {}
            for talk_id, clean in self.con.execute(
                    "SELECT n.talk_id, n.clean FROM para_norm n JOIN talks t USING (talk_id) "
                    "JOIN conferences c USING (conf_id) WHERE c.ordinal=?", (ordinal,)):
                talks[talk_id] = talks.get(talk_id, "") + f" {clean} |"
            self.cache[ordinal] = talks
        return self.cache[ordinal]

    def spoken(self, ordinal, term):
        """True if the term occurs anywhere in the conference, scripture quotations and
        near-identical spellings (fulness / fullness) included. Guards "absent"."""
        if ordinal not in self.norm:
            rows = self.con.execute(
                "SELECT n.norm FROM para_norm n JOIN talks t USING (talk_id) "
                "JOIN conferences c USING (conf_id) WHERE c.ordinal=?", (ordinal,))
            text = " " + " | ".join(r[0] for r in rows) + " "
            self.norm[ordinal] = (text, set(text.split()))
        text, vocab = self.norm[ordinal]
        if f" {term} " in text:
            return True
        return " " not in term and len(term) >= 5 and any(
            abs(len(w) - len(term)) <= 1 and one_edit(w, term)
            and w != term + "s" and term != w + "s"  # a plural is a different word
            for w in vocab)

    def top_share(self, ordinal, term):
        """Share of the conference's uses of term that come from its heaviest talk."""
        needle = f" {term} "
        uses = [count_occurrences(text, needle) for text in self.talks(ordinal).values()]
        return max(uses) / sum(uses) if sum(uses) else 0.0

    def shared_passage(self, ordinal, term):
        """True when every talk using the term uses it inside one shared 7-word passage."""
        needle, shared = f" {term} ", None
        for text in self.talks(ordinal).values():
            toks = text.split()
            grams = set()
            for i in range(len(toks)):
                if " ".join(toks[i:i + needle.count(" ") - 1]) == term:
                    lo = max(0, i - 6)
                    grams.update(" ".join(toks[j:j + 7]) for j in range(lo, i + 1)
                                 if "|" not in toks[j:j + 7] and len(toks[j:j + 7]) == 7)
            if needle in f" {text} " or grams:
                shared = grams if shared is None else shared & grams
        return bool(shared)


def one_edit(a, b):
    """True if a and b differ by exactly one inserted, deleted or changed letter."""
    if a == b:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:] if len(a) < len(b) else a[i + 1:] == b[i + 1:]


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
    peak = np.zeros(len(w.terms))          # highest rate among the burst conferences
    peak_ord = np.zeros(len(w.terms), dtype=int)
    for p in range(max(w.lo + 4, c - FADE_LOOKBACK), c):
        here = w.classes_at(p)["burst"]
        higher = here & (w.rate[:, w.col(p)] > peak)
        peak[higher], peak_ord[higher] = w.rate[higher, w.col(p)], p
        burst |= here
    current = now["new"] | now["revived"] | now["continuing"] | now["rising"]
    # seasonal words (Easter in April, Christmas in October) are not "fading" in the off season
    same = w.rate[:, [k for k in (col - 2, col - 4, col - 6) if k >= 0]].mean(axis=1)
    other = w.rate[:, [k for k in (col - 1, col - 3, col - 5) if k >= 0]].mean(axis=1)
    seasonal = same < FADE_RATIO * other
    fading = burst & (rate <= FADE_RATIO * peak) & ~current & ~seasonal
    absent = (count == 0) & (base_confs >= min(8, b.stop - b.start)) & (expected >= 3) & ~fading
    single = now["narrow"]

    order = {
        "new": speakers * 1000 + count, "revived": speakers * 1000 + count,
        "continuing": now["z"], "rising": now["zb"] + now["z"] / 100,
        # how surprising the drop is: shortfall against the peak rate, in Poisson standard errors
        "fading": (peak - rate) * w.words[col] / 1e4 / np.sqrt(np.maximum(peak * w.words[col] / 1e4, 1)),
        "absent": expected, "single": count,
    }
    masks = dict(now, fading=fading, absent=absent, single=single)
    base_sum = w.count[:, b].sum(axis=1)
    out, demoted = {}, []
    texts = ConfText(con)
    for cls in CLASSES + ("single",):
        weight = base_sum if cls in ("fading", "absent") else count
        fragment = fragments(w.terms, weight)
        idx = np.flatnonzero(masks[cls])
        if cls == "single":  # plus terms of other classes whose uses were mostly one talk
            idx = np.union1d(idx, np.array(demoted, dtype=int))
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
            if cls == "absent" and texts.spoken(c, term):
                continue  # said after all: inside a scripture quotation or spelled differently
            if cls == "fading" and texts.top_share(int(peak_ord[i]), term) > MAX_TALK_SHARE:
                continue  # the "surge" was one talk
            if cls in ("new", "revived") and texts.shared_passage(c, term):
                continue  # speakers quoting the same sentence, not adopting a phrase
            share = texts.top_share(c, term) if count[i] else 0.0
            if cls in ("new", "revived", "continuing", "rising") and share > MAX_TALK_SHARE:
                demoted.append(i)
                continue  # most uses come from one talk: reported as single-speaker emphasis
            if cls == "single" and speakers[i] >= 3 and share < 0.5:
                continue  # broad but below the rising bar: not an emphasis, not a trend
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
                "first_ord": int(w.first[i]), "top_talk_share": round(share, 2),
                "peak_ord": int(peak_ord[i]),
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


def screen_terms(lexical):
    """Ask the LLM which listed terms are names, places or transcript noise; drop those.

    Deterministic guards run first (see Guards); this catches what they cannot know, such
    as a country name that is also a dictionary word. Returns {term: reason}. Cached.
    """
    from .llm import ask_json
    terms = sorted({r["term"] for records in lexical.values() for r in records})
    prompt = (
        "These words and phrases were extracted automatically from talks at a Latter-day "
        "Saint General Conference (possibly from a machine transcript). Mark each one:\n"
        "  ok - a real word or phrase that could describe what a talk is about\n"
        "  name - a person's name or part of one, including scripture names that are also "
        "everyday first names (Luke, Adam, Mark, Ruth) and titles such as \"mr\"\n"
        "  place - a city, country or other place name\n"
        "  transcript - a speech-recognition error or a fragment that is not a real phrase\n"
        "  filler - a spoken interjection (\"okay\") or a multi-word sentence fragment that is "
        "not a phrase on its own (e.g. \"feel that way\", \"also revealed\", \"means we choose\")\n"
        "Be conservative: when unsure, answer ok. Every ordinary single word (\"knows\", "
        "\"helped\", \"simple\") is ok. Religious terms, titles of Church materials and "
        "scripture place or people names used as subjects (Nephi, Alma, Zion) are ok.\n\n"
        + "\n".join(terms) +
        "\n\nReply with only a JSON object mapping every term to its mark.")
    marks = ask_json(prompt)
    dropped = {t: m for t, m in marks.items() if m != "ok" and t in terms}
    for cls in lexical:
        lexical[cls] = [r for r in lexical[cls] if r["term"] not in dropped]
    return dropped


def compute_signals(conf_id, log=print):
    """Compute every layer's signals for a conference and cache them as JSON."""
    from . import layers, topics
    con = connect()
    centroids, model_topics, meta = topics.load_model()
    result = {
        "conf_id": conf_id,
        "provisional": con.execute("SELECT provisional FROM conferences WHERE conf_id=?",
                                   (conf_id,)).fetchone()[0],
        "lexical": lexical_signals(con, conf_id),
        "screened_out": {},
        "topics": layers.topic_signals(con, conf_id, model_topics),
        "new_topics": layers.new_topic_candidates(con, conf_id, topics.load_cache()),
        "quotes": layers.quote_signals(con, conf_id),
        "scriptures": layers.scripture_signals(con, conf_id),
        **layers.group_signals(con, conf_id),
        "topic_model": meta,
    }
    result["screened_out"] = screen_terms(result["lexical"])
    path = signals_path(conf_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1))
    log(f"wrote {path}")
    return result


def print_signals(conf_id):
    result = compute_signals(conf_id)
    for cls, records in result["lexical"].items():
        print(f"\n== {cls.upper()} ({len(records)}) ==")
        for r in records[:20]:
            print(f"  {r['term']:<40} uses {r['count']:>3}  speakers {r['speakers']:>2}  "
                  f"rate {r['rate']:>6.2f}  baseline {r['base_rate']:>6.2f}  z {r['z']:>5.1f}")
    topics = [t for t in result["topics"]["topics"] if not t["junk"]]
    for cls in ("rising", "fading", "continuing", "absent"):
        rows = sorted((t for t in topics if t["class"] == cls), key=lambda t: -abs(t["z"]))
        print(f"\n== TOPICS {cls.upper()} ({len(rows)}) ==")
        for t in rows[:12]:
            print(f"  {t['label']:<40} passages {t['passages']:>3}  talks {t['talks']:>2}  "
                  f"share {t['share']:.1%}  baseline {t['base_share']:.1%}  z {t['z']:>5.1f}")
    print(f"\n== NEW-TOPIC CANDIDATES ({len(result['new_topics'])}) ==")
    for cand in result["new_topics"]:
        print(f"  {cand['passages']} passages, {', '.join(cand['speakers'])}: {cand['samples'][0][:90]}")
    print(f"\n== QUOTES REPEATED ({len(result['quotes']['repeated'])}) ==")
    for q in result["quotes"]["repeated"][:15]:
        print(f"  {q['origin_speaker']} {q['origin_conf']} ({q['later_talks']} later talks): "
              f"{q['text'][:90]}")
    print("\n== SCRIPTURE CHAPTERS MOST QUOTED ==")
    for r in result["scriptures"]["top_chapters"]:
        print(f"  {r['ref']:<28} talks {r['talks']:>2}  baseline/conf {r['base_per_conf']}")
