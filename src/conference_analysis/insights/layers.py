"""Signals beyond single words and phrases: topics, quotes, scriptures, speaker groups."""
import sqlite3
from collections import Counter, defaultdict

import numpy as np

from .citations import top_cited
from .config import BASELINE_N, SCRIPTURES_DB
from .db import conf_ordinal
from .ngrams import talk_ngrams
from .quotes import MIN_QUOTED, MIN_WORDS, display_text, leaderboard
from .signals import Guards

TOPIC_Z = 2.0
GROUPS = ("First Presidency", "Twelve", "Other")


def log_odds_z(y_i, n_i, y_j, n_j, prior_share, prior=50.0):
    """Monroe et al. log-odds z-score of y_i/n_i vs y_j/n_j with an informative prior."""
    alpha = prior * prior_share
    delta = (np.log((y_i + alpha) / (n_i + prior - y_i - alpha))
             - np.log((y_j + alpha) / (n_j + prior - y_j - alpha)))
    return delta / np.sqrt(1 / (y_i + alpha) + 1 / (y_j + alpha))


# ---------------------------------------------------------------- topics

def topic_counts(con, upto):
    """(topic ids, ordinals, passages[topic, conf], talks[topic, conf], totals per conf)."""
    rows = con.execute(
        "SELECT c.ordinal, k.topic_id, COUNT(*), COUNT(DISTINCT k.talk_id) FROM chunk_topics k "
        "JOIN talks t USING (talk_id) JOIN conferences c USING (conf_id) "
        "WHERE c.ordinal <= ? GROUP BY 1, 2", (upto,)).fetchall()
    ords = sorted({r[0] for r in rows})
    topics = sorted({r[1] for r in rows})
    oi, ti = {o: i for i, o in enumerate(ords)}, {t: i for i, t in enumerate(topics)}
    passages = np.zeros((len(topics), len(ords)))
    talks = np.zeros((len(topics), len(ords)))
    for o, t, n, m in rows:
        passages[ti[t], oi[o]] = n
        talks[ti[t], oi[o]] = m
    return topics, ords, passages, talks, passages.sum(axis=0)


def topic_signals(con, conf_id, model_topics):
    """Per-topic share history and rising / fading / continuing / absent for conference C."""
    c = conf_ordinal(conf_id)
    topics, ords, passages, talks, totals = topic_counts(con, c)
    col = ords.index(c)
    base = slice(max(0, col - BASELINE_N), col)
    older = slice(max(0, col - 30), max(0, col - BASELINE_N))
    share = passages / totals
    n_talks = con.execute("SELECT COUNT(*) FROM talks WHERE conf_id=? AND kind='address'",
                          (conf_id,)).fetchone()[0]
    info = {t["topic_id"]: t for t in model_topics}
    out = []
    for i, topic_id in enumerate(topics):
        if topic_id < 0:
            continue
        y_i, y_j = passages[i, col], passages[i, base].sum()
        base_share = y_j / totals[base].sum()
        older_share = passages[i, older].sum() / max(totals[older].sum(), 1)
        z = float(log_odds_z(y_i, totals[col], y_j, totals[base].sum(),
                             passages[i, :col + 1].sum() / totals[:col + 1].sum()))
        # seasonal topics (Easter in April) are judged against same-month conferences only
        same = [k for k in range(col - 2, max(-1, col - BASELINE_N - 1), -2)]
        off = [k for k in range(col - 1, max(-1, col - BASELINE_N - 1), -2)]
        same_share = passages[i, same].sum() / max(totals[same].sum(), 1)
        off_share = passages[i, off].sum() / max(totals[off].sum(), 1)
        seasonal = bool((same_share < 0.5 * off_share or off_share < 0.5 * same_share) and y_j >= 20)
        if seasonal:
            y_j, base_share = passages[i, same].sum(), same_share
            z = float(log_odds_z(y_i, totals[col], y_j, totals[same].sum(),
                                 passages[i, :col + 1].sum() / totals[:col + 1].sum()))
        if y_i == 0 and base_share * totals[col] >= 3:
            cls = "absent"
        elif z >= TOPIC_Z and talks[i, col] >= 3:
            cls = "rising"
        elif z <= -TOPIC_Z:
            cls = "fading"
        elif share[i, col] >= 1.5 * older_share and base_share >= 1.5 * older_share \
                and talks[i, col] >= 3:
            cls = "continuing"
        else:
            cls = "steady"
        out.append({
            "topic_id": topic_id, "label": info[topic_id]["label"], "junk": info[topic_id]["junk"],
            "terms": info[topic_id]["terms"][:8], "class": cls,
            "passages": int(passages[i, col]), "talks": int(talks[i, col]),
            "share": round(float(share[i, col]), 5), "talk_share": round(talks[i, col] / n_talks, 4),
            "base_passages": int(y_j), "base_share": round(float(base_share), 5),
            "older_share": round(float(older_share), 5), "z": round(z, 2), "seasonal": seasonal,
            "history": [round(float(s), 5) for s in share[i]],
        })
    return {"total_passages": int(totals[col]), "base_total_passages": int(totals[base].sum()),
            "no_topic_passages": int(passages[topics.index(-1), col]) if -1 in topics else 0,
            "first_conf_ord": ords[0], "talks": n_talks,
            "topics": sorted(out, key=lambda t: -t["passages"])}


def new_topic_candidates(con, conf_id, cache):
    """Clusters among C's passages that fit no frozen topic (cosine distance < 0.35)."""
    from sklearn.cluster import AgglomerativeClustering
    rows = con.execute(
        "SELECT k.chunk_id, k.talk_id, s.name, h.sha, h.text FROM chunk_topics k "
        "JOIN chunks h USING (chunk_id) JOIN talks t ON t.talk_id = k.talk_id "
        "LEFT JOIN speakers s USING (speaker_id) "
        "WHERE t.conf_id=? AND k.topic_id=-1 ORDER BY k.chunk_id", (conf_id,)).fetchall()
    if len(rows) < 3:
        return []
    X = np.stack([cache[r[3]] for r in rows]).astype(np.float32)
    labels = AgglomerativeClustering(n_clusters=None, distance_threshold=0.35, metric="cosine",
                                     linkage="average").fit_predict(X)
    out = []
    for label in set(labels):
        members = [rows[i] for i in np.flatnonzero(labels == label)]
        if len(members) < 3:
            continue
        speakers = sorted({m[2] for m in members})
        out.append({"passages": len(members), "speakers": speakers,
                    "talk_ids": sorted({m[1] for m in members}),
                    "chunk_ids": [m[0] for m in members],
                    "samples": [" ".join(m[4].split()[:60]) for m in members[:8]]})
    return sorted(out, key=lambda c: (-len(c["speakers"]), -c["passages"]))


# ---------------------------------------------------------------- quotes

def quote_signals(con, conf_id):
    """Established quotes repeated in C, leaderboards, and (official text only) cited talks."""
    c = conf_ordinal(conf_id)
    rows = con.execute(
        "SELECT q.*, t.title, t.conf_id AS origin_conf, s.name AS origin_speaker "
        "FROM quotes q JOIN talks t ON t.talk_id = q.origin_talk_id "
        "LEFT JOIN speakers s USING (speaker_id) "
        "WHERE q.origin_ord < ? AND q.quoted_share >= ? AND q.quote_id IN "
        "(SELECT u.quote_id FROM quote_uses u JOIN talks t2 USING (talk_id) "
        " WHERE t2.conf_id=? AND u.words >= ?) "
        "ORDER BY q.later_speakers DESC, q.later_talks DESC, q.quote_id",
        (c, MIN_QUOTED, conf_id, MIN_WORDS))
    repeated, seen = [], []
    for q in map(dict, rows.fetchall()):
        lineage = [dict(r) for r in con.execute(
            "SELECT t.talk_id, t.conf_id, s.name AS speaker, t.title, t.session, u.words "
            "FROM quote_uses u JOIN talks t USING (talk_id) LEFT JOIN speakers s USING (speaker_id) "
            "WHERE u.quote_id=? ORDER BY t.talk_id", (q["quote_id"],))]
        here = {u["talk_id"] for u in lineage if u["conf_id"] == conf_id and u["words"] >= MIN_WORDS}
        grams = {" ".join(q["text"].split()[i:i + 5]) for i in range(len(q["text"].split()) - 4)}
        if any(here <= h and (grams & g or o == q["origin_talk_id"]) for o, h, g in seen):
            continue  # another piece of a passage already listed for the same talks
        seen.append((q["origin_talk_id"], here, grams))
        repeated.append(quote_record(con, q, lineage, conf_id))
    board = [quote_record(con, q) for q in leaderboard(con, 15, until_ord=c)]
    recent = [quote_record(con, q) for q in leaderboard(con, 8, since_ord=c - BASELINE_N, until_ord=c)]
    cited = top_cited(con, 10, conf_id, conf_id)
    return {"repeated": repeated, "all_time": board, "recent": recent, "cited_talks": cited}


def quote_record(con, q, lineage=None, conf_id=None):
    if lineage is None:
        lineage = [dict(r) for r in con.execute(
            "SELECT t.talk_id, t.conf_id, s.name AS speaker, t.title, t.session, u.words "
            "FROM quote_uses u JOIN talks t USING (talk_id) LEFT JOIN speakers s USING (speaker_id) "
            "WHERE u.quote_id=? ORDER BY t.talk_id", (q["quote_id"],))]
    origin = con.execute(
        "SELECT t.title, t.conf_id, s.name FROM talks t LEFT JOIN speakers s USING (speaker_id) "
        "WHERE t.talk_id=?", (q.get("origin_talk_id") or q["talk_id"],)).fetchone()
    return {
        "quote_id": q["quote_id"],
        "text": display_text(con, q["origin_para_id"], q["tok_start"], q["tok_end"]),
        "origin_title": origin[0], "origin_conf": origin[1], "origin_speaker": origin[2],
        "origin_quoted": q["origin_quoted"],
        "later_talks": len(lineage), "later_speakers": len({u["speaker"] for u in lineage}),
        "first_use": lineage[0]["conf_id"], "last_use": lineage[-1]["conf_id"],
        "here": [u for u in lineage if u["conf_id"] == conf_id and u["words"] >= MIN_WORDS]
        if conf_id else [],
        "lineage": lineage,
    }


# ---------------------------------------------------------------- scriptures

def volumes():
    """book title -> volume title, from the scriptures database."""
    con = sqlite3.connect(f"file:{SCRIPTURES_DB}?mode=ro", uri=True)
    return dict(con.execute(
        "SELECT b.book_title, v.volume_title FROM books b JOIN volumes v ON v.id = b.volume_id"))


def scripture_signals(con, conf_id):
    """Verses quoted verbatim in C: top chapters and verses, movers vs baseline, by volume."""
    c = conf_ordinal(conf_id)
    lo = c - BASELINE_N
    rows = con.execute(
        "SELECT cf.ordinal, q.talk_id, q.book, q.chapter, q.verse FROM scripture_quotes q "
        "JOIN talks t USING (talk_id) JOIN conferences cf USING (conf_id) "
        "WHERE cf.ordinal BETWEEN ? AND ?", (lo, c)).fetchall()
    n_talks = dict(con.execute(
        "SELECT c.ordinal, COUNT(*) FROM talks t JOIN conferences c USING (conf_id) "
        "WHERE t.kind='address' AND c.ordinal BETWEEN ? AND ? GROUP BY 1", (lo, c)))
    base_talks = sum(n for o, n in n_talks.items() if o < c)
    vol = volumes()
    chapters = defaultdict(lambda: [set(), set()])   # (book, chapter) -> [C talks, baseline talks]
    verses = defaultdict(lambda: [set(), set()])
    by_volume = defaultdict(lambda: [0, 0])          # volume -> [C verse quotes, baseline]
    for ordinal, talk_id, book, chapter, verse in rows:
        side = 0 if ordinal == c else 1
        chapters[(book, chapter)][side].add(talk_id)
        verses[(book, chapter, verse)][side].add(talk_id)
        by_volume[vol.get(book, "Other")][side] += 1

    def record(key, sides):
        here, before = len(sides[0]), len(sides[1])
        z = float(log_odds_z(here, n_talks[c], before, base_talks,
                             (here + before) / (n_talks[c] + base_talks), prior=10.0))
        book = key[0].replace("--", "—")
        ref = f"{book} {key[1]}" + (f":{key[2]}" if len(key) > 2 else "")
        if book == "Articles of Faith":  # one chapter; its "verses" are the thirteen articles
            ref = book + (f" {key[2]}" if len(key) > 2 else "")
        return {"ref": ref, "book": key[0], "chapter": key[1], "verse": key[2] if len(key) > 2 else None,
                "talks": here, "talk_ids": sorted(sides[0]), "base_talks": before,
                "base_per_conf": round(before / BASELINE_N, 2), "z": round(z, 2)}

    chapter_rows = [record(k, v) for k, v in chapters.items()]
    verse_rows = [record(k, v) for k, v in verses.items()]
    top = lambda rs: sorted((r for r in rs if r["talks"]),
                            key=lambda r: (-r["talks"], r["book"], r["chapter"], r["verse"] or 0))
    return {
        "talks": n_talks[c], "base_talks": base_talks,
        "top_chapters": top(chapter_rows)[:12], "top_verses": top(verse_rows)[:12],
        "up": sorted((r for r in chapter_rows if r["talks"] >= 3 and r["z"] >= 0.8),
                     key=lambda r: -r["z"])[:8],
        "down": sorted((r for r in chapter_rows if r["talks"] == 0 and r["base_talks"] >= 8),
                       key=lambda r: -r["base_talks"])[:8],
        "volumes": [{"volume": v, "quotes": n[0], "base_quotes": n[1]}
                    for v, n in sorted(by_volume.items(), key=lambda kv: -kv[1][0])],
        "total_quotes": sum(n[0] for n in by_volume.values()),
        "base_total_quotes": sum(n[1] for n in by_volume.values()),
    }


# ---------------------------------------------------------------- speaker groups

def talk_counts(con, conf_id):
    """Per talk of C: (row, Counter of 1-2-word terms, word total) from the tokenised text."""
    talks = [dict(r) for r in con.execute(
        "SELECT t.talk_id, t.calling_group, t.speaker_id, s.name AS speaker, t.word_count, "
        "t.session, t.title FROM talks t LEFT JOIN speakers s USING (speaker_id) "
        "WHERE t.conf_id=? AND t.kind='address' ORDER BY t.talk_id", (conf_id,))]
    out = []
    for t in talks:
        paras = [r[0] for r in con.execute(
            "SELECT clean FROM para_norm WHERE talk_id=? ORDER BY para_id", (t["talk_id"],))]
        counts = Counter({term: n for term, n in talk_ngrams(paras).items() if term.count(" ") < 2})
        out.append((t, counts, sum(len(p.replace("|", " ").split()) for p in paras)))
    return out


def talk_signals(con, conf_id, guards, per_talk):
    """One line per talk of C: its leading topics and the words it used far more than the rest."""
    total = sum((c for _, c, _ in per_talk), Counter())
    all_words = sum(w for _, _, w in per_talk)
    out = []
    for t, counts, words in per_talk:
        scored = []
        for term, n in counts.items():
            if n < 3 or words < 500:  # too short a talk (closing remarks) to characterise
                continue
            z = float(log_odds_z(n, words, total[term] - n, all_words - words,
                                 total[term] / all_words, prior=5000.0))
            if z >= 2.5 and not guards.reject(term):
                scored.append((z, term, n))
        distinctive, used = [], set()
        for z, term, n in sorted(scored, reverse=True):
            if not (set(term.split()) & used):  # skip "law of tithing" after "tithing"
                distinctive.append({"term": term, "count": n})
                used |= set(term.split())
            if len(distinctive) == 4:
                break
        topics = [dict(r) for r in con.execute(
            "SELECT topic_id, COUNT(*) AS passages FROM chunk_topics WHERE talk_id=? "
            "AND topic_id >= 0 GROUP BY 1 ORDER BY 2 DESC, 1", (t["talk_id"],))]
        out.append({"talk_id": t["talk_id"], "speaker": t["speaker"], "session": t["session"],
                    "group": t["calling_group"], "words": t["word_count"],
                    "topics": topics, "distinctive": distinctive})
    return out


def group_signals(con, conf_id):
    """Per calling group in C: size, leading topics, distinctive words; plus one line per talk."""
    c = conf_ordinal(conf_id)
    provisional = con.execute("SELECT provisional FROM conferences WHERE conf_id=?",
                              (conf_id,)).fetchone()[0]
    guards = Guards(con, c, provisional)
    per_talk = talk_counts(con, conf_id)
    counts = {g: Counter() for g in GROUPS}
    users = {g: defaultdict(set) for g in GROUPS}
    words, raw_words = Counter(), Counter()
    for t, talk_terms, n_words in per_talk:
        group = t["calling_group"]
        words[group] += n_words
        raw_words[group] += t["word_count"]
        for term, n in talk_terms.items():
            counts[group][term] += n
            users[group][term].add(t["speaker_id"])
    total = sum(counts.values(), Counter())
    all_words = sum(words.values())
    out = []
    for group in GROUPS:
        members = [t for t, _, _ in per_talk if t["calling_group"] == group]
        distinctive = []
        for term, n in counts[group].items():
            if len(users[group][term]) < 2 or n < 4:
                continue
            z = float(log_odds_z(n, words[group], total[term] - n, all_words - words[group],
                                 total[term] / all_words, prior=5000.0))
            if z >= 2.5 and not guards.reject(term):
                distinctive.append({"term": term, "count": n, "speakers": len(users[group][term]),
                                    "rest_count": total[term] - n, "z": round(z, 2)})
        topics = [dict(r) for r in con.execute(
            "SELECT k.topic_id, COUNT(*) AS passages, COUNT(DISTINCT k.talk_id) AS talks "
            "FROM chunk_topics k JOIN talks t USING (talk_id) "
            "WHERE t.conf_id=? AND t.calling_group=? AND k.topic_id >= 0 "
            "GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 12", (conf_id, group))]
        passages = con.execute(
            "SELECT COUNT(*) FROM chunk_topics k JOIN talks t USING (talk_id) "
            "WHERE t.conf_id=? AND t.calling_group=?", (conf_id, group)).fetchone()[0]
        out.append({"group": group, "talks": len(members), "words": raw_words[group],
                    "speakers": sorted({m["speaker"] for m in members}), "passages": passages,
                    "distinctive": sorted(distinctive, key=lambda d: -d["z"])[:12],
                    "topics": topics})
    return {"groups": out, "talks": talk_signals(con, conf_id, guards, per_talk)}
