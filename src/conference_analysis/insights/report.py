"""Render reports/<conf>.html: one self-contained page (SPEC F4).

Numbers come from the signals (data/signals/<conf>.json) and corpus.db; sentences come
from `claude -p` (cached) and are rejected if they contain a digit.
"""
import html
import json
import re
from datetime import date

from .config import BASELINE_N, REPORTS
from .db import conf_ordinal, connect
from .llm import ask_json
from .ngrams import count_occurrences
from .signals import compute_signals

SESSION_SHORT = {"Saturday Morning Session": "Sat. morning", "Saturday Afternoon Session": "Sat. afternoon",
                 "Sunday Morning Session": "Sun. morning", "Sunday Afternoon Session": "Sun. afternoon"}
LEX_SHOWN = 10   # rows shown per phrase class
PROPER = {"jesus": "Jesus", "christ": "Christ", "christ's": "Christ's", "god": "God", "god's": "God's",
          "lord": "Lord", "lord's": "Lord's", "savior": "Savior", "savior's": "Savior's",
          "heavenly": "Heavenly", "holy": "Holy", "ghost": "Ghost", "spirit": "Spirit",
          "mormon": "Mormon", "easter": "Easter", "sabbath": "Sabbath", "zion": "Zion",
          "israel": "Israel", "redeemer": "Redeemer"}
GROUP_NAMES = {"First Presidency": "First Presidency", "Twelve": "Quorum of the Twelve Apostles",
               "Other": "Other speakers (Seventies, Presiding Bishopric, general officers)"}
esc = html.escape


def ord_name(ordinal):
    """Conference ordinal -> 'October 2026' (1 = April 1971; earlier ordinals run backwards)."""
    return f"{'April' if (ordinal - 1) % 2 == 0 else 'October'} {1971 + (ordinal - 1) // 2}"


def conf_name(conf_id):
    return ord_name(conf_ordinal(conf_id))


def num(x, digits=1):
    return f"{x:,.{digits}f}" if isinstance(x, float) else f"{x:,}"


def plural(n, word):
    return f"{n:,} {word}" if n == 1 else f"{n:,} {word}s"


def pct(x):
    return f"{100 * x:.1f}%"


def show_term(term):
    """A lower-cased index term with sacred names capitalised for display."""
    shown = " ".join(PROPER.get(w, w) for w in term.split())
    return shown.replace("Heavenly father", "Heavenly Father")


def unstutter(text):
    """Remove immediately doubled words from a transcript excerpt ("is is" -> "is")."""
    return re.sub(r"\b([\w']+)(,? )\1\b", r"\1", text, flags=re.I)


# ------------------------------------------------------------------ evidence from the database

class Evidence:
    """Look-ups that back each insight with talks and counts."""

    def __init__(self, con, conf_id):
        self.con, self.conf_id, self.c = con, conf_id, conf_ordinal(conf_id)
        self.talks = {r["talk_id"]: dict(r) for r in con.execute(
            "SELECT t.talk_id, t.title, t.session, t.calling_group, s.name AS speaker FROM talks t "
            "LEFT JOIN speakers s USING (speaker_id) WHERE t.conf_id=? AND t.kind='address'",
            (conf_id,))}
        self.clean = {}
        for talk_id, clean in con.execute(
                "SELECT n.talk_id, n.clean FROM para_norm n JOIN talks t USING (talk_id) "
                "WHERE t.conf_id=?", (conf_id,)):
            self.clean.setdefault(talk_id, []).append(f" {clean} ")
        self.words = dict(con.execute("SELECT ord, words FROM conf_stats"))
        self.first_ord = min(self.words)
        self.total_passages = con.execute(
            "SELECT COUNT(*) FROM chunk_topics k JOIN talks t USING (talk_id) WHERE t.conf_id=?",
            (conf_id,)).fetchone()[0]

    def talk_label(self, talk_id):
        t = self.talks[talk_id]
        if t["title"]:
            return f"{t['speaker']}, “{t['title']}”"
        return f"{t['speaker']} ({SESSION_SHORT.get(t['session'], t['session'])})"

    def term_talks(self, term):
        """[(talk label, uses)] for every talk of C using the term, most uses first."""
        needle = f" {term} "
        rows = []
        for talk_id, paras in self.clean.items():
            n = sum(count_occurrences(p, needle) for p in paras)
            if n:
                rows.append((self.talk_label(talk_id), n))
        return sorted(rows, key=lambda r: (-r[1], r[0]))

    def term_counts(self, term):
        """{ordinal: (uses, speakers)} for every conference up to C that used the term."""
        return {r[0]: r[1:] for r in self.con.execute(
            "SELECT tc.ord, tc.count, tc.speakers FROM term_conf tc JOIN terms USING (term_id) "
            "WHERE term=? AND tc.ord <= ?", (term, self.c))}

    def topic_talks(self, topic_id):
        rows = self.con.execute(
            "SELECT k.talk_id, COUNT(*) FROM chunk_topics k JOIN talks t USING (talk_id) "
            "WHERE t.conf_id=? AND k.topic_id=? GROUP BY 1 ORDER BY 2 DESC, 1",
            (self.conf_id, topic_id)).fetchall()
        return [(self.talk_label(t), n) for t, n in rows]


# ------------------------------------------------------------------ words from the LLM

def no_digits(text):
    return isinstance(text, str) and bool(text.strip()) and not re.search(r"\d", text)


def label_new_topics(candidates):
    """Short label per new-topic candidate, and whether it is a subject or one talk's story."""
    if not candidates:
        return
    blocks = [f"Cluster {i}\n" + "\n".join("  - " + s for s in c["samples"][:4])
              for i, c in enumerate(candidates)]
    prompt = (
        "Each cluster below is a group of similar passages from one General Conference that "
        "did not match any long-running topic. For each, write a short plain-English label "
        "(2 to 5 words, title case) and classify it: \"subject\" if the passages teach about a "
        "distinct subject (for example a warning against some practice), \"story\" if they are "
        "one narrative or anecdote.\n\n" + "\n\n".join(blocks) +
        "\n\nReply with only a JSON array: [{\"cluster\": 0, \"label\": \"...\", \"kind\": \"subject\"}]")
    for item in ask_json(prompt):
        candidates[item["cluster"]].update(label=item["label"], kind=item["kind"])
    for c in candidates:
        c.setdefault("label", "Unlabelled group")
        c.setdefault("kind", "story")


def name_sources(quotes):
    """For quotations whose earliest conference use was itself a quotation, ask who is quoted."""
    todo = [q for q in quotes if q["origin_quoted"]]
    if not todo:
        return
    prompt = (
        "Each line below is a passage that speakers at Latter-day Saint General Conference "
        "have quoted many times, quoting an earlier source. Name the original source in a few "
        "words (for example \"Joseph Smith\", \"The Family: A Proclamation to the World\", "
        "\"the hymn 'I Am a Child of God'\", \"Spencer W. Kimball\"). Answer \"unknown\" unless "
        "you are confident.\n\n"
        + "\n".join(f"{i}: {q['text']}" for i, q in enumerate(todo)) +
        "\n\nReply with only a JSON array of strings, one per line, same order.")
    try:
        names = ask_json(prompt)
    except Exception:
        names = []
    for q, name in zip(todo, names):
        if isinstance(name, str) and name.strip().lower() != "unknown" and not re.search(r"\d", name):
            q["likely_source"] = name.strip()


def narrate(facts, conf_id):
    """One sentence per fact, written by the LLM from the fact's fields. No digits allowed."""
    prompt = (
        f"You are writing the headline list for a report on the {conf_name(conf_id)} General "
        "Conference of The Church of Jesus Christ of Latter-day Saints, for ordinary church "
        "members. Each item below is a finding computed from the talk texts, compared with the "
        "ten conferences before it. Write exactly one plain sentence per item (at most 30 "
        "words). Rules: do NOT include any number, digit, count or percentage - the page shows "
        "the numbers next to your sentence; no statistics jargon; do not exaggerate - say "
        "\"more than usual\" or \"less than usual\", not \"dominated\"; name speakers only when "
        "the item lists them; when an item is marked single_speaker, say plainly that it comes "
        "from one talk; when an item names a likely_source, say the quotation comes from that "
        "source.\n\n"
        + json.dumps([{k: v for k, v in f.items() if k not in ("stats", "fallback")} for f in facts],
                     indent=1) +
        "\n\nReply with only a JSON array of strings, one sentence per item, same order.")
    try:
        sentences = ask_json(prompt)
    except Exception:
        sentences = []
    return [sentences[i] if i < len(sentences) and no_digits(sentences[i]) else f["fallback"]
            for i, f in enumerate(facts)]


def overview(signals, facts, conf_id):
    """A short paragraph tying the findings together (LLM, no digits); '' if it fails."""
    lex, sc = signals["lexical"], signals["scriptures"]
    topics = [t for t in signals["topics"]["topics"] if not t["junk"]]
    material = {
        "headline_findings": [{k: v for k, v in f.items() if k not in ("stats", "fallback")} for f in facts],
        "topics_discussed_more_than_usual": [t["label"] for t in movers(topics, up=True)],
        "topics_discussed_less_than_usual": [t["label"] for t in movers(topics, up=False)],
        "subjects_matching_no_long_running_topic": [
            {"subject": c["label"], "speakers": c["speakers"]} for c in signals["new_topics"]
            if c.get("kind") == "subject"],
        "words_emphasised_by_only_one_or_two_speakers": [
            {"word": r["term"], "speakers": r["speakers"]} for r in lex["single"][:10]],
        "phrases_rising": [r["term"] for r in lex["rising"][:8]],
        "phrases_fading": [r["term"] for r in lex["fading"][:6]],
        "books_of_scripture_quoted_more_than_usual": [
            v["volume"] for v in sc["volumes"]
            if v["quotes"] / max(sc["total_quotes"], 1)
            > 1.3 * v["base_quotes"] / max(sc["base_total_quotes"], 1)],
        "what_each_talk_emphasised": [
            {"speaker": t["speaker"], "words": [d["term"] for d in t["distinctive"]]}
            for t in signals["talks"]],
    }
    prompt = (
        f"Below are findings computed from the texts of the {conf_name(conf_id)} General "
        "Conference of The Church of Jesus Christ of Latter-day Saints, compared with earlier "
        "conferences. Write a short overview paragraph (three or four plain sentences, at most "
        "ninety words) for ordinary church members that ties related findings together - for "
        "example several findings about the same theme. Rules: use ONLY what is listed; do not "
        "include any number or digit; no statistics jargon; do not overstate - these are "
        "modest shifts in emphasis; say \"one talk\" when something comes from a single "
        "speaker.\n\n" + json.dumps(material, indent=1) +
        "\n\nReply with only a JSON array containing one string: the paragraph.")
    try:
        text = ask_json(prompt)[0]
    except Exception:
        return ""
    return text if no_digits(text) else ""


# ------------------------------------------------------------------ small HTML pieces

def spark(values, label, unit, first_ord, width=132, height=40):
    """Inline SVG sparkline: history in grey, the latest conference as an accent dot."""
    top = max(max(values), 1e-9)
    n = len(values)
    xs = [2 + i * (width - 6) / max(n - 1, 1) for i in range(n)]
    ys = [27 - v / top * 23 for v in values]
    path = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in zip(xs, ys))
    data = esc(json.dumps({"v": values, "o": first_ord, "u": unit}))
    first_year = 1971 + (first_ord - 1) // 2
    return (f'<svg class="spark" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            f'role="img" aria-label="{esc(label)}" data-s="{data}" tabindex="0">'
            f'<path d="{path}" /><circle cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="3" />'
            f'<text x="2" y="38">{first_year}</text>'
            f'<text x="{width - 2}" y="38" text-anchor="end">now</text></svg>')


def details(summary, body):
    return f'<details><summary>{esc(summary)}</summary><div class="ev">{body}</div></details>'


def talk_list(rows, unit="use"):
    if not rows:
        return ""
    return "<ul>" + "".join(f"<li>{esc(label)} — {plural(n, unit)}</li>" for label, n in rows) + "</ul>"


def bar(share, base_share, top):
    """A share bar with a tick at the comparison share."""
    w, b = 100 * share / top, 100 * base_share / top
    return (f'<div class="bar" aria-hidden="true"><i style="width:{min(w, 100):.1f}%"></i>'
            f'<b style="left:{min(b, 100):.1f}%"></b></div>')


def tidy_quote(text):
    """Trim a matched span to whole sentences where it can; mark open ends with …"""
    starts = [m.end() for m in re.finditer(r"[.!?]”?\s+(?=[A-Z“])", text)]
    if text[:1].islower() and starts and starts[0] <= 0.45 * len(text):
        text = text[starts[0]:]
    ends = [m.end() for m in re.finditer(r"[.!?]", text)]
    if ends and ends[-1] >= 0.5 * len(text):
        text = text[:ends[-1]]
    elif "”" in text[-20:]:
        text = text[:text.rindex("”")].rstrip(" ,")
    return ("… " if text[:1].islower() else "") + text + ("" if text[-1:] in ".!?" else " …")


# ------------------------------------------------------------------ sections

def term_row(r, ev, kind):
    """One phrase row: term, sparkline, plain numbers, evidence."""
    counts = ev.term_counts(r["term"])
    history = [round(counts.get(o, (0, 0))[0] * 1e4 / ev.words[o], 3)
               for o in range(ev.first_ord, ev.c + 1)]
    talks = ev.term_talks(r["term"])
    baseline = [(o, *counts.get(o, (0, 0))) for o in range(ev.c - BASELINE_N, ev.c)]
    base_uses = sum(b[1] for b in baseline)
    usual = f"usually about {num(r['expected'])} per conference of this length"
    if kind == "absent":
        figures = f"Not used this time · {usual}"
    elif kind == "fading":
        peak_uses, peak_speakers = counts.get(r["peak_ord"], (0, 0))
        figures = (f"{plural(r['count'], 'use')} this time · peak of {peak_uses} uses by "
                   f"{plural(peak_speakers, 'speaker')} in {ord_name(r['peak_ord'])}")
    elif kind == "new":
        figures = f"{plural(r['count'], 'use')} · {plural(r['speakers'], 'speaker')}"
    else:
        figures = f"{plural(r['count'], 'use')} · {plural(r['speakers'], 'speaker')} · {usual}"
    now = (f"<p>In {esc(conf_name(ev.conf_id))}: {plural(r['count'], 'use')} by "
           f"{plural(r['speakers'], 'speaker')}.</p>" + talk_list(talks)
           if r["count"] else f"<p>Not used in {esc(conf_name(ev.conf_id))}.</p>")
    first = min(counts) if counts else ev.c
    before = (f"<p>Previous {BASELINE_N} conferences: {base_uses} uses in all.</p><ul class='cols'>"
              + "".join(f"<li>{esc(ord_name(o))}: {plural(n, 'use')}, {plural(s, 'speaker')}</li>"
                        for o, n, s in baseline) + "</ul>"
              if base_uses else f"<p>Not used in any of the previous {BASELINE_N} conferences.</p>")
    body = now + before + f"<p>First used in a conference talk in our records: {esc(ord_name(first))}.</p>"
    speakers = ", ".join(t[0].split(" (")[0] for t in talks[:6]) + (" …" if len(talks) > 6 else "")
    who = f'<div class="who">{esc(speakers)}</div>' if kind in ("new", "revived", "single") and talks else ""
    return (f'<div class="row"><div class="term">{esc(show_term(r["term"]))}{who}</div>'
            + spark(history, f"How often “{r['term']}” was used in each conference",
                    "per 10,000 words", ev.first_ord)
            + f'<div class="fig">{esc(figures)}</div>' + details("Evidence", body) + "</div>")


def lexical_block(title, blurb, records, ev, kind, shown=LEX_SHOWN):
    rows = "".join(term_row(r, ev, kind) for r in records[:shown]) or "<p class='none'>None this time.</p>"
    return f"<h3>{esc(title)}</h3><p class='blurb'>{esc(blurb)}</p>{rows}"


def base_words(t):
    """Name of the comparison a topic's earlier share comes from."""
    if t.get("seasonal"):
        return "Previous 5 conferences held in the same month"
    return f"Previous {BASELINE_N} conferences"


def movers(topics, up):
    """Topics whose share moved most (in percentage points) against the comparison share."""
    if up:
        rows = [t for t in topics if t["z"] >= 1.0 and t["talks"] >= 2]
        return sorted(rows, key=lambda t: t["base_share"] - t["share"])[:6]
    rows = [t for t in topics if t["z"] <= -1.0 and t["passages"] > 0]
    return sorted(rows, key=lambda t: t["share"] - t["base_share"])[:6]


def topic_row(t, ev, top_share, first_ord):
    body = (f"<p>{t['passages']} of {ev.total_passages} passages ({pct(t['share'])}) in "
            f"{plural(t['talks'], 'talk')}. {base_words(t)}: {t['base_passages']} passages "
            f"({pct(t['base_share'])}).</p>" + talk_list(ev.topic_talks(t["topic_id"]), "passage"))
    return (f'<div class="row"><div class="term">{esc(t["label"])}</div>'
            + spark([round(100 * h, 3) for h in t["history"]],
                    f"Share of each conference spent on “{t['label']}”", "% of passages", first_ord)
            + f'<div class="fig">{pct(t["share"])} of passages · {plural(t["talks"], "talk")} '
              f'({esc(base_words(t).lower())}: {pct(t["base_share"])})'
            + bar(t["share"], t["base_share"], top_share) + "</div>"
            + details("Evidence", body) + "</div>")


def quote_block(q, conf_id, show_here=True):
    title = q["origin_title"].strip("“”")
    origin = f"{q['origin_speaker']}, “{title}”, {conf_name(q['origin_conf'])}"
    if q["origin_quoted"]:
        source = (f"Source: {q['likely_source']} (named by an AI model). " if q.get("likely_source")
                  else "The speaker was quoting an earlier source. ")
        source += f"Earliest use in conference since 1971: {origin}"
    else:
        source = f"First said by {origin}"
    here = ""
    if show_here and q["here"]:
        here = ("<p class='who'>Repeated this conference by "
                + esc(", ".join(sorted({u["speaker"] for u in q["here"]}))) + ".</p>")
    lineage = "<ul>" + "".join(
        f"<li>{esc(conf_name(u['conf_id']))} — {esc(u['speaker'] or '')}"
        + (f", “{esc(u['title'].strip('“”'))}”" if u["title"] else "") + "</li>"
        for u in q["lineage"]) + "</ul>"
    return (f'<div class="quote"><blockquote>“{esc(tidy_quote(q["text"]))}”</blockquote>'
            f'<p class="src">{esc(source)}</p>{here}'
            f'<div class="fig">Used in {plural(q["later_talks"], "other talk")} by '
            f'{plural(q["later_speakers"], "speaker")}, '
            f'{esc(conf_name(q["first_use"]))} to {esc(conf_name(q["last_use"]))}</div>'
            + details("Every other talk that used it", lineage) + "</div>")


def scripture_table(rows, ev, label):
    body = "".join(
        f"<tr><td>{esc(r['ref'])}</td><td>{r['talks']}</td><td>{num(r['base_per_conf'], 1)}</td><td>"
        + details("Talks", "<ul>" + "".join(f"<li>{esc(ev.talk_label(t))}</li>" for t in r["talk_ids"])
                  + "</ul>") + "</td></tr>" for r in rows)
    return (f'<div class="scroll"><table><thead><tr><th>{label}</th><th>Talks quoting it</th>'
            f'<th>Usual number of talks per conference</th><th></th></tr></thead>'
            f"<tbody>{body}</tbody></table></div>")


def headline_facts(signals):
    """Pick the strongest finding of each layer; each has stats (numbers) and a fallback sentence."""
    lex, sc = signals["lexical"], signals["scriptures"]
    topics = [t for t in signals["topics"]["topics"] if not t["junk"]]
    facts = []
    for t in [t for t in movers(topics, up=True) if t["talks"] >= 3][:1]:
        facts.append({"finding": "topic discussed more than usual", "topic": t["label"],
                      "fallback": f"“{t['label']}” was discussed more than usual.",
                      "stats": f"{pct(t['share'])} of passages in {t['talks']} talks; "
                               f"{base_words(t).lower()} {pct(t['base_share'])}"})
    for t in movers(topics, up=False)[:1]:
        facts.append({"finding": "topic discussed less than usual", "topic": t["label"],
                      "fallback": f"“{t['label']}” was discussed less than usual.",
                      "stats": f"{pct(t['share'])} of passages; {base_words(t).lower()} "
                               f"{pct(t['base_share'])}"})
    for cand in [c for c in signals["new_topics"] if c.get("kind") == "subject"][:1]:
        facts.append({"finding": "a subject that matched no long-running topic",
                      "subject": cand["label"], "speakers": cand["speakers"],
                      "single_speaker": len(cand["speakers"]) == 1,
                      "fallback": f"{', '.join(cand['speakers'])} spoke about {cand['label'].lower()}, "
                                  "a subject that matched no long-running topic.",
                      "stats": f"{cand['passages']} passages, {plural(len(cand['speakers']), 'speaker')}"})
    covered = " ".join(f.get("subject", "") for f in facts).lower()
    picks = (("phrase that was rare, picked up in the last few conferences, and is still in use",
              lex["continuing"]),
             ("phrase used by more speakers than usual", [r for r in lex["rising"][:8] if r["n"] > 1]),
             ("phrase never used in conference before", [r for r in lex["new"] if r["speakers"] >= 3]),
             ("a word one speaker used again and again",
              [r for r in lex["single"] if r["speakers"] == 1 and r["term"] not in covered]),
             ("phrase that surged in an earlier conference and has now dropped away",
              sorted(lex["fading"][:8], key=lambda r: r["n"] == 1)))  # stable: phrases lead
    for finding, records in picks:
        for r in records[:1]:
            now = (f"{plural(r['count'], 'use')} by {plural(r['speakers'], 'speaker')}"
                   if r["count"] else "not used this time")
            fact = {"finding": finding, "phrase": r["term"],
                    "fallback": f"“{show_term(r['term'])}”: {finding}.",
                    "stats": f"{now}; previous {BASELINE_N} conferences {r['base_count']} uses in all"}
            if "surged" in finding:
                fact["stats"] += f"; peak {ord_name(r['peak_ord'])}"
            if "one speaker" in finding:
                fact["single_speaker"] = True
            facts.append(fact)
    for q in signals["quotes"]["repeated"][:1]:
        facts.append({"finding": "a long-established quotation repeated again this conference",
                      "quote_first_words": " ".join(q["text"].split()[:14]),
                      "likely_source": q.get("likely_source") or q["origin_speaker"],
                      "repeated_by": sorted({u["speaker"] for u in q["here"]}),
                      "fallback": "A long-established quotation was repeated again.",
                      "stats": f"used in {q['later_talks']} talks since {conf_name(q['origin_conf'])}"})
    shares = [(v, v["quotes"] / max(sc["total_quotes"], 1), v["base_quotes"] / max(sc["base_total_quotes"], 1))
              for v in sc["volumes"] if v["quotes"] >= 15]
    for v, now, before in sorted(shares, key=lambda s: s[2] / max(s[1], 1e-9))[:1]:
        if now >= 1.3 * before:
            facts.append({"finding": "a book of scripture quoted word-for-word more than usual",
                          "book_of_scripture": v["volume"],
                          "fallback": f"The {v['volume']} was quoted more than usual.",
                          "stats": f"{pct(now)} of verse quotations; previous {BASELINE_N} "
                                   f"conferences {pct(before)}"})
    return facts


CSS = """
:root{--bg:#fcfcfb;--surface:#f3f2ee;--line:#dddbd3;--text:#0b0b0b;--text2:#52514e;--muted:#807e77;
--accent:#2a78d6;--down:#c9521f;--hist:#a3a199}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#1a1a19;--surface:#242422;
--line:#3a3a37;--text:#ffffff;--text2:#c3c2b7;--muted:#8f8e85;--accent:#3987e5;--down:#e2733f;--hist:#6f6e67}}
:root[data-theme="dark"]{--bg:#1a1a19;--surface:#242422;--line:#3a3a37;--text:#ffffff;--text2:#c3c2b7;
--muted:#8f8e85;--accent:#3987e5;--down:#e2733f;--hist:#6f6e67}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;overflow-x:hidden}
main{max-width:860px;margin:0 auto;padding:16px}
h1{font-size:1.7rem;line-height:1.2;margin:.6em 0 .2em}
h2{font-size:1.3rem;margin:2.2em 0 .3em;padding-top:.8em;border-top:1px solid var(--line)}
h3{font-size:1.05rem;margin:1.6em 0 .2em}
p{margin:.5em 0}.sub,.blurb,.src,.who,.none{color:var(--text2)}.blurb,.src{font-size:.93rem}
.lead{font-size:1.05rem}
.note{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:10px 14px;font-size:.93rem}
nav{display:flex;flex-wrap:wrap;gap:6px;margin:14px 0}
nav a{color:var(--text);text-decoration:none;border:1px solid var(--line);border-radius:999px;padding:3px 11px;font-size:.85rem}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin:14px 0}
.tile{background:var(--surface);border-radius:8px;padding:10px 12px}.tile b{display:block;font-size:1.4rem}
.tile span{color:var(--text2);font-size:.82rem}
ol.head{padding-left:1.3em}ol.head li{margin:.9em 0}
.fig{color:var(--text2);font-size:.86rem}
.row{display:grid;grid-template-columns:minmax(0,1fr) 132px;gap:2px 12px;align-items:center;padding:9px 0;border-bottom:1px solid var(--line)}
.row .term{font-weight:600;overflow-wrap:anywhere}.row .who{font-weight:400;font-size:.85rem}
.row .fig,.row details{grid-column:1/-1}
.spark path{fill:none;stroke:var(--hist);stroke-width:1.5;stroke-linejoin:round}.spark circle{fill:var(--accent)}
.spark text{font-size:8px;fill:var(--muted)}
.spark{cursor:crosshair;outline-offset:2px}
.bar{position:relative;height:6px;background:var(--surface);border-radius:3px;margin-top:5px;max-width:320px}
.bar i{position:absolute;left:0;top:0;bottom:0;background:var(--accent);border-radius:3px}
.bar b{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--text)}
details{font-size:.88rem}summary{cursor:pointer;color:var(--accent)}
.ev{background:var(--surface);border-radius:8px;padding:8px 14px;margin:6px 0;overflow-wrap:anywhere}
.ev ul{margin:.3em 0;padding-left:1.2em}.ev ul.cols{columns:2 220px}
.quote{padding:10px 0;border-bottom:1px solid var(--line)}
blockquote{margin:0 0 .3em;padding-left:12px;border-left:3px solid var(--accent);font-size:1.02rem}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--text2);font-weight:600}
.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:0 28px}
.up::before{content:"▲ ";color:var(--accent)}.dn::before{content:"▼ ";color:var(--down)}
.chips span{display:inline-block;background:var(--surface);border-radius:999px;padding:2px 10px;margin:2px 4px 2px 0;font-size:.88rem}
#tip{position:fixed;pointer-events:none;background:var(--text);color:var(--bg);font-size:.78rem;padding:3px 8px;border-radius:5px;display:none;z-index:9;white-space:nowrap}
footer{color:var(--muted);font-size:.82rem;margin:3em 0 2em}
code{font-size:.85em;background:var(--surface);padding:1px 4px;border-radius:4px;overflow-wrap:anywhere}
"""

JS = """
(function(){var tip=document.getElementById('tip');
function name(o){var y=1971+Math.floor((o-1)/2);return (((o-1)%2+2)%2?'October ':'April ')+y}
function show(svg,x,cx,cy){var d=JSON.parse(svg.dataset.s),n=d.v.length,r=svg.getBoundingClientRect();
var i=Math.max(0,Math.min(n-1,Math.round((x-r.left-2)/(r.width-6)*(n-1))));
tip.textContent=name(d.o+i)+': '+d.v[i]+' '+d.u;tip.style.display='block';
var w=tip.offsetWidth;tip.style.left=Math.max(4,Math.min(window.innerWidth-w-4,cx-w/2))+'px';tip.style.top=(cy-30)+'px'}
document.querySelectorAll('svg.spark').forEach(function(s){
s.addEventListener('pointermove',function(e){show(s,e.clientX,e.clientX,e.clientY)});
s.addEventListener('pointerleave',function(){tip.style.display='none'});
s.addEventListener('focus',function(){var r=s.getBoundingClientRect();show(s,r.right,r.right,r.top)});
s.addEventListener('blur',function(){tip.style.display='none'})})})();
"""


def build_html(signals, ev):
    conf_id = signals["conf_id"]
    lex, tp, qs, sc = signals["lexical"], signals["topics"], signals["quotes"], signals["scriptures"]
    dropped = signals["screened_out"]
    con = ev.con
    n_talks, n_words = con.execute(
        "SELECT COUNT(*), SUM(word_count) FROM talks WHERE conf_id=? AND kind='address'",
        (conf_id,)).fetchone()
    n_speakers = con.execute("SELECT COUNT(DISTINCT speaker_id) FROM talks WHERE conf_id=? "
                             "AND kind='address'", (conf_id,)).fetchone()[0]
    n_confs, n_all, first_conf = con.execute(
        "SELECT COUNT(DISTINCT conf_id), COUNT(*), MIN(conf_id) FROM talks "
        "WHERE kind='address' AND conf_id < ?", (conf_id,)).fetchone()
    since = conf_name(first_conf)
    topics = [t for t in tp["topics"] if not t["junk"]]
    labels = {t["topic_id"]: t for t in tp["topics"]}
    first = tp["first_conf_ord"]
    name_sources(qs["repeated"] + qs["all_time"] + qs["recent"])
    out = []
    add = out.append

    # ---- header
    add(f"<h1>{esc(conf_name(conf_id))} General Conference: what stood out</h1>")
    add(f"<p class='sub'>What was new, rising, continuing, fading and missing in the words, topics, "
        f"quotations and scriptures of this conference, measured against the {n_confs} conferences "
        f"({num(n_all)} talks) since {esc(since)}.</p>")
    if signals["provisional"]:
        add("<p class='note'><strong>Provisional.</strong> The Church has not yet published the "
            "text of these talks. This page is built from automatic transcripts of the broadcast "
            "audio, so small wording errors are possible and the talks have no titles or footnotes "
            "yet. It will be rebuilt from the official text when that is published.</p>")
    add(f'<div class="tiles"><div class="tile"><b>{n_talks}</b><span>talks</span></div>'
        f'<div class="tile"><b>{n_speakers}</b><span>speakers</span></div>'
        f'<div class="tile"><b>{num(n_words)}</b><span>words spoken</span></div>'
        f'<div class="tile"><b>{n_confs}</b><span>earlier conferences compared</span></div></div>')
    add('<nav aria-label="Sections">' + "".join(
        f'<a href="#s{i}">{t}</a>' for i, t in enumerate(
            ["Headlines", "Topics", "New words", "Phrases", "Quotations", "Scriptures",
             "Who said what", "Method"], 1)) + "</nav>")
    add(f"<p class='blurb'><strong>How to read this page.</strong> Each small grey chart runs from "
        f"{esc(since.split()[-1])} on the left to this conference on the right (the blue dot); "
        "higher means used or discussed more. Point at or tap a chart to read any conference's "
        "value. “Evidence” opens the counts and the talks behind a line. “Previous 10 conferences” "
        f"means {esc(ord_name(ev.c - BASELINE_N))} through {esc(ord_name(ev.c - 1))}. With only "
        f"{n_talks} talks in a conference, most shifts are modest; one or two talks can move a number.</p>")

    # ---- 1 headline
    facts = headline_facts(signals)
    sentences = narrate(facts, conf_id)
    lead = overview(signals, facts, conf_id)
    add('<section id="s1"><h2>1. Headlines</h2>'
        + (f"<p class='lead'>{esc(lead)}</p>" if lead else "") + '<ol class="head">' + "".join(
            f"<li>{esc(s)}<div class='fig'>{esc(f['stats'])}</div></li>"
            for s, f in zip(sentences, facts)) + "</ol></section>")

    # ---- 2 topics
    add('<section id="s2"><h2>2. Topics</h2>')
    add(f"<p class='blurb'>To measure topics, every talk was cut into short passages of a few "
        f"sentences each ({tp['total_passages']} this conference, about a dozen per talk). Each "
        f"passage was matched to the closest of {sum(not t['junk'] for t in tp['topics'])} subjects "
        "that recur in conference talks since 1971. “2% of passages” means about one passage in "
        "fifty was on that subject. On each bar, the black tick marks the share in earlier "
        "conferences.</p><h3>Most-discussed topics</h3>")
    top_share = max(t["share"] for t in topics[:12]) * 1.05
    add("".join(topic_row(t, ev, top_share, first) for t in topics[:12]))
    line = lambda t, cls: (
        f"<p class='{cls}'><strong>{esc(t['label'])}</strong> <span class='fig'>{pct(t['share'])} of "
        f"passages, usually {pct(t['base_share'])} · {plural(t['talks'], 'talk')}</span></p>")
    add("<h3>Biggest changes from the previous ten conferences</h3><p class='blurb'>Largest change "
        "first. A topic raised by only two talks is included when those talks dwelt on it.</p>"
        "<div class='two'><div><p class='blurb'>Discussed more than usual</p>"
        + ("".join(line(t, "up") for t in movers(topics, up=True)) or "<p class='none'>None.</p>")
        + "</div><div><p class='blurb'>Discussed less than usual</p>"
        + ("".join(line(t, "dn") for t in movers(topics, up=False)) or "<p class='none'>None.</p>")
        + "</div></div>")
    absent = [t for t in topics if t["class"] == "absent"]
    if absent:
        add("<h3>Regular topics not touched this time</h3><p class='chips'>" + "".join(
            f"<span>{esc(t['label'])} <span class='fig'>(usually {pct(t['base_share'])} of passages)"
            "</span></span>" for t in absent) + "</p>")
    add(f"<h3>Subjects that fit none of the recurring topics</h3><p class='blurb'>{tp['no_topic_passages']} "
        f"of {tp['total_passages']} passages were not close to any recurring topic. Where several "
        "of them resembled each other they are grouped here: either a subject being taught, or one "
        "long story told in a talk.</p>")
    cands = sorted(signals["new_topics"], key=lambda c: (c.get("kind") != "subject", -c["passages"]))
    for cand in cands:
        kind = "A subject taught" if cand.get("kind") == "subject" else "A story told"
        add(f"<div class='row'><div class='term'>{esc(cand['label'])}"
            f"<div class='who'>{esc(', '.join(cand['speakers']))}</div></div><div></div>"
            f"<div class='fig'>{kind} · {cand['passages']} passages · "
            f"{plural(len(cand['speakers']), 'speaker')}</div>"
            + details("Evidence", "<p>How each passage begins (from the transcript):</p><ul>" + "".join(
                f"<li>“{esc(unstutter(' '.join(s.split()[:28])))} …”</li>" for s in cand["samples"])
                + "</ul>") + "</div>")
    if not cands:
        add("<p class='none'>None this time.</p>")
    add("</section>")

    # ---- 3 new and revived
    add('<section id="s3"><h2>3. New and revived words and phrases</h2>')
    add(lexical_block("New", f"Never used in a conference talk since {since.split()[-1]}, and used "
                      "by at least two speakers this time. Wholly new phrases shared by several "
                      "speakers are rare, so this list is usually short.", lex["new"], ev, "new"))
    add(lexical_block("Revived", f"Used in the past, absent from all of the previous {BASELINE_N} "
                      "conferences, and back with at least three speakers.", lex["revived"], ev, "revived"))
    add("</section>")

    # ---- 4 rising / continuing / fading / absent
    add('<section id="s4"><h2>4. Rising, continuing, fading and absent phrases</h2>')
    add("<p class='blurb'>“Usually about N per conference” is how often the word was used in the "
        f"previous {BASELINE_N} conferences, scaled to a conference of this one's length.</p>")
    add(lexical_block("Rising", "Used clearly more than in the previous ten conferences, by at "
                      "least three speakers, with no single talk supplying most of the uses. Many "
                      "are everyday words; together they hint at the tone of the conference.",
                      lex["rising"], ev, "rising"))
    add(lexical_block("Continuing: picked up recently and stuck", "Rare for years, took off "
                      "within the last few conferences, and still used this time by at least "
                      "three speakers.", lex["continuing"], ev, "continuing"))
    add(lexical_block("Emphasised by only a few speakers", "Stood out strongly, but mostly in one "
                      "or two talks: a speaker's theme, not a conference-wide trend.",
                      lex["single"], ev, "single", shown=14))
    add(lexical_block("Fading", "Surged across several talks in one of the previous six "
                      "conferences and is now well under half of that peak.", lex["fading"], ev, "fading"))
    add(lexical_block("Absent", f"Used in at least eight of the previous {BASELINE_N} conferences, "
                      "but not once this time.", lex["absent"], ev, "absent", shown=8))
    add("</section>")

    # ---- 5 quotes
    add('<section id="s5"><h2>5. Quotations</h2>')
    add("<p class='blurb'>Found by looking for the same run of seven or more words in talks by "
        "different speakers, leaving out scripture. Where the earliest speaker we have was "
        "already quoting someone, the page says so.</p>")
    add("<h3>Established quotations repeated this conference</h3>")
    add("".join(quote_block(q, conf_id) for q in qs["repeated"][:12]) or "<p class='none'>None found.</p>")
    add("<h3>For context</h3>")
    add(details("The most-repeated quotations since 1971",
                "<p>The passages repeated by the most different speakers across every conference "
                "since 1971.</p>" + "".join(quote_block(q, conf_id, show_here=False) for q in qs["all_time"])))
    add(details(f"The most-repeated lines first said in the last {BASELINE_N} conferences",
                "".join(quote_block(q, conf_id, show_here=False) for q in qs["recent"])
                or "<p>None yet.</p>"))
    if signals["provisional"]:
        add("<p class='note'>Which earlier talks were cited most in footnotes cannot be shown yet: "
            "transcripts have no footnotes. That list will appear when the official text is published.</p>")
    elif qs["cited_talks"]:
        add("<h3>Earlier talks cited most in footnotes</h3><ul>" + "".join(
            f"<li>{esc(r['speaker'] or '')}, “{esc(r['title'] or r['target_uri'])}” "
            f"({esc(conf_name(r['conf_id'])) if r['conf_id'] else ''}) — cited by {r['citing_talks']} talks</li>"
            for r in qs["cited_talks"]) + "</ul>")
    add("</section>")

    # ---- 6 scriptures
    add('<section id="s6"><h2>6. Scriptures</h2>')
    add(f"<p class='blurb'>Counted from verses quoted word-for-word in the talks (eight or more words "
        f"in a row matching the scriptures): {sc['total_quotes']} verse quotations this conference. "
        "A verse a speaker only mentions without quoting is not counted. A passage that appears in "
        "two books (Malachi 3 is repeated in 3 Nephi 24) is listed under both.</p>")
    add("<h3>Chapters quoted by the most talks</h3>" + scripture_table(sc["top_chapters"], ev, "Chapter"))
    add("<h3>Verses quoted by the most talks</h3>" + scripture_table(sc["top_verses"], ev, "Verse"))
    add("<h3>Changes</h3><div class='two'><div><p class='blurb'>Quoted by more talks than usual</p>"
        + ("".join(f"<p class='up'><strong>{esc(r['ref'])}</strong> <span class='fig'>{r['talks']} talks; "
                   f"usually {num(r['base_per_conf'], 1)} per conference</span></p>"
                   for r in sc["up"]) or "<p class='none'>None.</p>")
        + "</div><div><p class='blurb'>Often quoted before, not quoted this time</p>"
        + "".join(f"<p class='dn'><strong>{esc(r['ref'])}</strong> <span class='fig'>no talks; "
                  f"usually {num(r['base_per_conf'], 1)} per conference</span></p>"
                  for r in sc["down"]) + "</div></div>")
    add("<h3>By book of scripture</h3><div class='scroll'><table><thead><tr><th>Book of scripture</th>"
        f"<th>Verse quotations</th><th>Share this conference</th><th>Share, previous {BASELINE_N}</th>"
        "</tr></thead><tbody>"
        + "".join(f"<tr><td>{esc(v['volume'])}</td><td>{v['quotes']}</td>"
                  f"<td>{pct(v['quotes'] / max(sc['total_quotes'], 1))}</td>"
                  f"<td>{pct(v['base_quotes'] / max(sc['base_total_quotes'], 1))}</td></tr>"
                  for v in sc["volumes"]) + "</tbody></table></div></section>")

    # ---- 7 groups and talks
    add('<section id="s7"><h2>7. Who said what</h2>')
    add("<h3>Talk by talk</h3><p class='blurb'>For each talk: the recurring topics most of its "
        "passages matched, and the words it used far more than the other talks did (with how many "
        "times).</p><div class='scroll'><table><thead><tr><th>Speaker</th><th>Main topics</th>"
        "<th>Distinctive words</th></tr></thead><tbody>")
    for t in signals["talks"]:
        main = [labels[x["topic_id"]]["label"] for x in t["topics"]
                if not labels[x["topic_id"]]["junk"]][:2]
        words = ", ".join(f"{esc(show_term(d['term']))} ({d['count']})" for d in t["distinctive"])
        add(f"<tr><td>{esc(t['speaker'])}<div class='fig'>{esc(SESSION_SHORT.get(t['session'], t['session']))}"
            f"</div></td><td>{esc('; '.join(main)) or '—'}</td><td>{words or '—'}</td></tr>")
    add("</tbody></table></div>")
    add("<h3>By calling</h3><p class='blurb'>The same measures grouped by the speaker's calling at "
        "this conference. “Distinctive words” are words a group used at a much higher rate than "
        "everyone else, allowing for how much each group spoke.</p>")
    for g in signals["groups"]:
        shown = [t for t in g["topics"] if not labels[t["topic_id"]]["junk"]][:5]
        add(f"<p><strong>{esc(GROUP_NAMES[g['group']])}</strong> <span class='fig'>{plural(g['talks'], 'talk')} · "
            f"{num(g['words'])} words</span></p>"
            + details("Speakers", "<p>" + esc(", ".join(g["speakers"])) + "</p>")
            + "<p>Leading topics: " + "; ".join(
                f"{esc(labels[t['topic_id']]['label'])} <span class='fig'>({plural(t['passages'], 'passage')}, "
                f"{plural(t['talks'], 'talk')})</span>" for t in shown) + ".</p>"
            + ("<p>Distinctive words: " + ", ".join(
                f"{esc(show_term(d['term']))} <span class='fig'>({plural(d['count'], 'time')}, by {d['speakers']} of "
                f"this group's speakers; {plural(d['rest_count'], 'time')} in all other talks)</span>"
                for d in g["distinctive"][:6]) + ".</p>" if g["distinctive"] else ""))
    add("</section>")

    # ---- 8 method
    tm = signals["topic_model"]
    add('<section id="s8"><h2>8. Method and caveats</h2><ul>')
    add("<li><strong>Sources.</strong> Conferences from April 1971 through April 2026 come from the "
        "Church's published text. "
        + ("This conference comes from automatic transcripts of the broadcast audio (names were "
           "corrected by hand; immediately repeated words were removed before counting). "
           if signals["provisional"] else "")
        + ("Conferences before 1971 come from the Conference Report text published by the BYU "
           "Scripture Citation Index (1942 onward; October 1957 is missing); charts that start "
           "before 1971 cross that change of source. " if first_conf < "1971-04" else "")
        + f"{num(n_all)} earlier talks in all. Sustainings, audit and statistical reports are left out.</li>")
    add(f"<li><strong>Comparison.</strong> “Previous {BASELINE_N} conferences” is {esc(ord_name(ev.c - BASELINE_N))} "
        f"through {esc(ord_name(ev.c - 1))}. Charts show uses per 10,000 words, so longer and shorter "
        "conferences compare fairly. Scripture quoted by a speaker is not counted as the speaker's "
        f"own words, which is why rates are based on {num(ev.words[ev.c])} words and not the "
        f"{num(n_words)} spoken.</li>")
    add("<li><strong>Phrases.</strong> One- to five-word phrases are counted within sentences. "
        "Phrases that begin or end with a filler word (the, of, and …) are skipped.</li>")
    add("<li><strong>Thresholds.</strong> New: never used before, at least two speakers who are not "
        f"simply quoting the same sentence. Revived: absent for {BASELINE_N} conferences, at least three "
        "speakers. Rising: at least three speakers, at least 1.5 times the earlier rate, and a "
        "log-odds z-score (with an informative Dirichlet prior) of at least 3 on uses and 2 on "
        "speakers. Continuing: hardly used before, then two to seven conferences in a row at three "
        "times the earlier rate. Fading: a recent surge across several talks, now below 40% of "
        "its peak; seasonal words such as Easter are excluded. Absent: used in at least eight of "
        f"the previous {BASELINE_N} conferences, at least three uses expected, none found. Any word whose "
        "uses come mostly (over 60%) from one talk is moved to “Emphasised by only a few speakers”.</li>")
    add("<li><strong>Left out.</strong> Speakers' names, names of people and places in stories, "
        "spoken markers such as “quote”, and words that are neither in a dictionary nor in any "
        "earlier talk (likely transcription errors). An AI model also screened the listed phrases "
        f"for names, places, sentence fragments and transcript noise and removed {len(dropped)}"
        + (": " + esc(", ".join(sorted(dropped))) if dropped else "") + ".</li>")
    add(f"<li><strong>Topics.</strong> {tm['passages']:,} passages from 1971 to April 2026 were grouped by "
        f"meaning with a language model run locally ({esc(tm['model'])}) into {tm['topics']} groups; "
        f"{sum(t['junk'] for t in tp['topics'])} of them are not subjects (greetings, closing "
        "testimonies, passages that mainly quote leaders or scripture) and are hidden. The groups "
        "are frozen so shares stay comparable between conferences. Topic names were written by an "
        "AI model and reviewed. A topic is matched by overall meaning, so a passage can land in a "
        "broad topic such as “Trusting God in Adversity” without using those words. Topic changes "
        "listed use the same z-score (at least 1); with a few hundred passages per conference, "
        "small shifts are within normal variation.</li>")
    add("<li><strong>Quotations.</strong> Matching finds word-for-word reuse only, not paraphrase, "
        "and small spelling differences can split one quotation's history in two. “Earliest use” "
        "means the earliest in conference talks since 1971; when that speaker was already quoting "
        "someone, an AI model was asked to name the well-known source, and that name is not "
        "verified. Counts cover exactly the words shown (40 or fewer).</li>")
    add("<li><strong>Sentences.</strong> The overview paragraph and headline sentences were written by "
        "an AI model from the computed tables. Every number on this page was computed by code from "
        "the talk texts; none was written by an AI model.</li>")
    add("<li><strong>Checking a number.</strong> Each count can be reproduced from the project "
        "database, for example <code>SELECT COUNT(*) FROM para_norm n JOIN talks t USING (talk_id) "
        f"WHERE t.conf_id='{conf_id}' AND instr(' '||n.clean||' ', ' tithing ')&gt;0</code> for the "
        "paragraphs using a word, or <code>python -m conference_analysis.insights phrase "
        "\"tithing\"</code> for its full history.</li>")
    add(f"</ul></section><footer>Generated {date.today().isoformat()} by the Conference Insights "
        "Engine. Talk text belongs to The Church of Jesus Christ of Latter-day Saints; only short "
        "quotations and statistics are shown here.</footer>")

    title = f"{conf_name(conf_id)} Conference Insights"
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>{esc(title)}</title><style>{CSS}</style></head><body><main>"
            + "\n".join(out) + "</main><div id=\"tip\" role=\"status\"></div>"
            f"<script>{JS}</script></body></html>\n")


def write_report(conf_id, log=print):
    """Compute the signals and render reports/<conf>.html."""
    signals = compute_signals(conf_id, log)
    con = connect()
    label_new_topics(signals["new_topics"])
    page = build_html(signals, Evidence(con, conf_id))
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / f"{conf_id}.html"
    out.write_text(page)
    log(f"wrote {out} ({len(page.encode()) / 1024:.0f} KB)")
