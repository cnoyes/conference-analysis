"""Render reports/<conf>.html: one self-contained page (SPEC F4).

Numbers come from data/signals/<conf>.json and corpus.db; sentences come from
`claude -p` (cached) and are rejected if they contain a digit.
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

MONTHS = {4: "April", 10: "October"}
SESSION_SHORT = {"Saturday Morning Session": "Sat. morning", "Saturday Afternoon Session": "Sat. afternoon",
                 "Sunday Morning Session": "Sun. morning", "Sunday Afternoon Session": "Sun. afternoon"}
LEX_SHOWN = 12   # rows shown per phrase class
esc = html.escape


def conf_name(conf_id):
    year, month = conf_id.split("-")
    return f"{MONTHS[int(month)]} {year}"


def ord_name(ordinal):
    year, half = 1971 + (ordinal - 1) // 2, (ordinal - 1) % 2
    return f"{'April' if half == 0 else 'October'} {year}"


def num(x, digits=1):
    return f"{x:,.{digits}f}" if isinstance(x, float) else f"{x:,}"


def plural(n, word):
    return f"{n:,} {word}" if n == 1 else f"{n:,} {word}s"


def pct(x):
    return f"{100 * x:.1f}%"


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

    def talk_label(self, talk_id):
        t = self.talks[talk_id]
        where = SESSION_SHORT.get(t["session"], t["session"])
        return f"{t['speaker']} ({where})" if not t["title"] else f"{t['speaker']}, “{t['title']}”"

    def term_talks(self, term):
        """[(talk label, uses)] for every talk of C using the term, most uses first."""
        needle = f" {term} "
        rows = []
        for talk_id, paras in self.clean.items():
            n = sum(count_occurrences(p, needle) for p in paras)
            if n:
                rows.append((self.talk_label(talk_id), n))
        return sorted(rows, key=lambda r: (-r[1], r[0]))

    def term_history(self, term):
        """Uses per 10,000 words in every conference up to C (0 where unused)."""
        rows = dict(self.con.execute(
            "SELECT tc.ord, tc.count FROM term_conf tc JOIN terms USING (term_id) "
            "WHERE term=? AND tc.ord <= ?", (term, self.c)))
        return [round(rows.get(o, 0) * 1e4 / self.words[o], 3) for o in range(self.first_ord, self.c + 1)]

    def term_baseline(self, term):
        """[(conference, uses, speakers)] for the 10 baseline conferences."""
        rows = {r[0]: r[1:] for r in self.con.execute(
            "SELECT tc.ord, tc.count, tc.speakers FROM term_conf tc JOIN terms USING (term_id) "
            "WHERE term=? AND tc.ord BETWEEN ? AND ?", (term, self.c - BASELINE_N, self.c - 1))}
        return [(ord_name(o), *rows.get(o, (0, 0))) for o in range(self.c - BASELINE_N, self.c)]

    def topic_talks(self, topic_id):
        rows = self.con.execute(
            "SELECT k.talk_id, COUNT(*) FROM chunk_topics k JOIN talks t USING (talk_id) "
            "WHERE t.conf_id=? AND k.topic_id=? GROUP BY 1 ORDER BY 2 DESC, 1",
            (self.conf_id, topic_id)).fetchall()
        return [(self.talk_label(t), n) for t, n in rows]


# ------------------------------------------------------------------ words from the LLM

def screen_terms(signals):
    """Ask the LLM which reported terms are names, places or transcript noise; drop those."""
    lexical = signals["lexical"]
    terms = sorted({r["term"] for records in lexical.values() for r in records})
    prompt = (
        "These words and phrases were extracted automatically from a machine transcript of "
        "talks at a Latter-day Saint General Conference. Mark each one:\n"
        "  ok - a real word or phrase that could describe what a talk is about\n"
        "  name - a person's name or part of one\n"
        "  place - a city, country or other place name\n"
        "  transcript - a speech-recognition error or a fragment that is not a real phrase\n"
        "  filler - a spoken interjection (\"okay\") or a multi-word sentence fragment that is "
        "not a phrase on its own (e.g. \"feel that way\", \"also revealed\", \"means we choose\")\n"
        "Be conservative: when unsure, answer ok. Every ordinary single word (\"knows\", "
        "\"helped\", \"simple\") is ok. Religious terms, titles of Church materials and "
        "scripture names (Nephi, Alma, Zion) are ok.\n\n"
        + "\n".join(terms) +
        "\n\nReply with only a JSON object mapping every term to its mark.")
    marks = ask_json(prompt)
    dropped = {t: m for t, m in marks.items() if m != "ok" and t in terms}
    for cls in lexical:
        lexical[cls] = [r for r in lexical[cls] if r["term"] not in dropped]
    return dropped


def label_new_topics(candidates):
    """Short label per new-topic candidate, and whether it is a subject or one talk's story."""
    if not candidates:
        return
    blocks = [f"Cluster {i}\n" + "\n".join("  - " + s for s in c["samples"])
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
        c.setdefault("label", "Unlabelled cluster")
        c.setdefault("kind", "story")


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
        "from one talk.\n\n"
        + json.dumps([{k: v for k, v in f.items() if k != "stats"} for f in facts], indent=1) +
        "\n\nReply with only a JSON array of strings, one sentence per item, same order.")
    try:
        sentences = ask_json(prompt)
    except Exception:
        sentences = []
    out = []
    for i, fact in enumerate(facts):
        s = sentences[i] if i < len(sentences) and isinstance(sentences[i], str) else ""
        out.append(s if s and not re.search(r"\d", s) else fact["fallback"])
    return out


# ------------------------------------------------------------------ small HTML pieces

def spark(values, label, unit, first_ord, width=132, height=30):
    """Inline SVG sparkline: history in grey, the latest conference as an accent dot."""
    top = max(max(values), 1e-9)
    n = len(values)
    xs = [2 + i * (width - 6) / max(n - 1, 1) for i in range(n)]
    ys = [height - 3 - v / top * (height - 7) for v in values]
    path = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in zip(xs, ys))
    data = esc(json.dumps({"v": values, "o": first_ord, "u": unit}))
    return (f'<svg class="spark" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            f'role="img" aria-label="{esc(label)}" data-s="{data}" tabindex="0">'
            f'<path d="{path}" /><circle cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="3" /></svg>')


def details(summary, body):
    return f'<details><summary>{esc(summary)}</summary><div class="ev">{body}</div></details>'


def talk_list(rows, unit="use"):
    if not rows:
        return "<p>No talks.</p>"
    return "<ul>" + "".join(f"<li>{esc(label)} — {plural(n, unit)}</li>"
                            for label, n in rows) + "</ul>"


def bar(share, base_share, top):
    """A share bar with a tick at the baseline share."""
    w, b = 100 * share / top, 100 * base_share / top
    return (f'<div class="bar" aria-hidden="true"><i style="width:{w:.1f}%"></i>'
            f'<b style="left:{min(b, 100):.1f}%"></b></div>')


# ------------------------------------------------------------------ sections

def term_row(r, ev, kind):
    """One phrase row: term, sparkline, plain numbers, evidence."""
    history = ev.term_history(r["term"])
    talks = ev.term_talks(r["term"])
    baseline = ev.term_baseline(r["term"])
    base_uses = sum(b[1] for b in baseline)
    if kind in ("fading", "absent"):
        figures = (f"{plural(r['count'], 'use')} now · {base_uses} in the previous {BASELINE_N} conferences"
                   + (f" · about {num(r['expected'])} expected" if kind == "absent" else ""))
    else:
        figures = (f"{plural(r['count'], 'use')} · {plural(r['speakers'], 'speaker')} · {num(r['rate'], 2)} per 10,000 words "
                   f"(previous {BASELINE_N} conferences: {num(r['base_rate'], 2)})")
    body = (f"<p>In {esc(conf_name(ev.conf_id))}: {plural(r['count'], 'use')} by {plural(r['speakers'], 'speaker')}.</p>"
            + talk_list(talks)
            + f"<p>Previous {BASELINE_N} conferences: {base_uses} uses in all.</p><ul class='cols'>"
            + "".join(f"<li>{esc(c)}: {plural(n, 'use')}, {plural(s, 'speaker')}</li>" for c, n, s in baseline) + "</ul>"
            + f"<p>First used in conference: {esc(ord_name(r['first_ord']))} (corpus starts 1971).</p>")
    speakers = ", ".join(t[0].split(" (")[0] for t in talks[:6]) + (" …" if len(talks) > 6 else "")
    who = f'<div class="who">{esc(speakers)}</div>' if kind in ("new", "revived", "single") and talks else ""
    return (f'<div class="row"><div class="term">{esc(r["term"])}{who}</div>'
            + spark(history, f"Use of “{r['term']}” per conference", "per 10,000 words", ev.first_ord)
            + f'<div class="fig">{figures}</div>' + details("Evidence", body) + "</div>")


def lexical_block(title, blurb, records, ev, kind, shown=LEX_SHOWN):
    if not records:
        return f"<h3>{esc(title)}</h3><p class='blurb'>{esc(blurb)}</p><p class='none'>Nothing met the bar.</p>"
    rows = "".join(term_row(r, ev, kind) for r in records[:shown])
    return f"<h3>{esc(title)}</h3><p class='blurb'>{esc(blurb)}</p>{rows}"


def topic_row(t, ev, top_share, first_ord):
    body = (f"<p>{t['passages']} of {ev_total(ev)} passages ({pct(t['share'])}) in "
            f"{plural(t['talks'], 'talk')}. {base_words(t)}: {t['base_passages']} passages "
            f"({pct(t['base_share'])}).</p><p>Typical words: {esc(', '.join(t['terms']))}.</p>"
            + talk_list(ev.topic_talks(t["topic_id"]), "passage"))
    return (f'<div class="row"><div class="term">{esc(t["label"])}</div>'
            + spark([round(100 * h, 3) for h in t["history"]],
                    f"Share of passages on “{t['label']}” per conference", "% of passages", first_ord)
            + f'<div class="fig">{pct(t["share"])} of passages · {plural(t["talks"], "talk")} '
              f'({base_words(t).lower()}: {pct(t["base_share"])})'
            + bar(t["share"], t["base_share"], top_share) + "</div>"
            + details("Evidence", body) + "</div>")


def base_words(t):
    """Name of the comparison a topic's baseline share comes from."""
    if t.get("seasonal"):
        return "Previous 5 conferences held in the same month"
    return f"Previous {BASELINE_N} conferences"


def ev_total(ev):
    return ev.con.execute(
        "SELECT COUNT(*) FROM chunk_topics k JOIN talks t USING (talk_id) WHERE t.conf_id=?",
        (ev.conf_id,)).fetchone()[0]


def quote_block(q, conf_id, show_here=True):
    origin = f"{q['origin_speaker']}, “{q['origin_title'].strip('“”')}”, {conf_name(q['origin_conf'])}"
    source = ("Earliest conference use since 1971 (the speaker was quoting an earlier source): "
              if q["origin_quoted"] else "First said by ")
    here = ""
    if show_here and q["here"]:
        here = ("<p class='who'>Repeated this conference by "
                + esc(", ".join(sorted({u["speaker"] for u in q["here"]}))) + ".</p>")
    lineage = "<ul>" + "".join(
        f"<li>{esc(conf_name(u['conf_id']))} — {esc(u['speaker'] or '')}"
        + (f", “{esc(u['title'].strip('“”'))}”" if u["title"] else "") + "</li>" for u in q["lineage"]) + "</ul>"
    text = tidy_quote(q["text"])
    return (f'<div class="quote"><blockquote>“{esc(text)}”</blockquote>'
            f'<p class="src">{esc(source + origin)}</p>{here}'
            f'<div class="fig">Used in {q["later_talks"]} later talks by {q["later_speakers"]} speakers, '
            f'{esc(conf_name(q["first_use"]))} to {esc(conf_name(q["last_use"]))}</div>'
            + details("Every later talk that used it", lineage) + "</div>")


def tidy_quote(text):
    """Trim a matched span to end at a sentence or closing quote mark; mark open ends with …"""
    ends = [m.end() for m in re.finditer(r"[.!?]", text)]
    if ends and ends[-1] >= 0.5 * len(text):
        text = text[:ends[-1]]
    elif "”" in text[-20:]:
        text = text[:text.rindex("”")].rstrip(" ,")
    return ("… " if text[:1].islower() else "") + text + ("" if text[-1:] in ".!?" else " …")


def scripture_table(rows, ev, label):
    body = "".join(
        f"<tr><td>{esc(r['ref'])}</td><td>{r['talks']}</td><td>{num(r['base_per_conf'], 1)}</td>"
        f"<td>{details('Talks', "<ul>" + "".join(f"<li>{esc(ev.talk_label(t))}</li>" for t in r["talk_ids"]) + "</ul>")}</td></tr>"
        for r in rows)
    return (f'<div class="scroll"><table><thead><tr><th>{label}</th><th>Talks quoting it</th>'
            f'<th>Average per conference, previous {BASELINE_N}</th><th></th></tr></thead>'
            f"<tbody>{body}</tbody></table></div>")


def headline_facts(signals, ev):
    """Pick the strongest finding of each layer; each has stats (numbers) and a fallback sentence."""
    lex, topics = signals["lexical"], [t for t in signals["topics"]["topics"] if not t["junk"]]
    facts = []
    rising = sorted((t for t in topics if t["z"] > 0 and t["talks"] >= 3 and t["passages"] >= 8),
                    key=lambda t: -t["z"])
    falling = sorted((t for t in topics if t["z"] < 0 and t["base_passages"] >= 30),
                     key=lambda t: t["z"])
    for t in rising[:1]:
        facts.append({"finding": "topic discussed more than usual", "topic": t["label"],
                      "fallback": f"“{t['label']}” was discussed more than usual.",
                      "stats": f"{pct(t['share'])} of passages in {t['talks']} talks; "
                               f"{base_words(t).lower()} {pct(t['base_share'])}"})
    for t in falling[:1]:
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
    multiword_first = lambda rs: sorted(rs, key=lambda r: r["n"] == 1)  # stable: phrases lead
    picks = (("continuing", "phrase that entered recently and is still being used", lex["continuing"]),
             ("rising", "word or phrase used by more speakers than usual", multiword_first(lex["rising"][:6])),
             ("new", "phrase never used in conference before",
              [r for r in lex["new"] if r["speakers"] >= 3]),
             ("fading", "phrase that surged in a recent conference and has now dropped away",
              multiword_first(lex["fading"][:8])))
    for cls, finding, records in picks:
        for r in records[:1]:
            now = (f"{plural(r['count'], 'use')} by {plural(r['speakers'], 'speaker')}"
                   if r["count"] else "not used this time")
            facts.append({"finding": finding, "phrase": r["term"],
                          "fallback": f"“{r['term']}”: {finding}.",
                          "stats": f"{now}; previous {BASELINE_N} conferences {r['base_count']} uses"})
    for q in signals["quotes"]["repeated"][:1]:
        facts.append({"finding": "a long-established quotation repeated again this conference",
                      "quote_first_words": " ".join(q["text"].split()[:14]),
                      "originally_from": q["origin_speaker"],
                      "originally_quoting_an_earlier_source": bool(q["origin_quoted"]),
                      "repeated_by": sorted({u["speaker"] for u in q["here"]}),
                      "fallback": "A long-established quotation was repeated again.",
                      "stats": f"used in {q['later_talks']} talks since {conf_name(q['origin_conf'])}"})
    for r in signals["scriptures"]["top_chapters"][:1]:
        facts.append({"finding": "the scripture chapter quoted word-for-word by the most talks",
                      "chapter": r["ref"], "fallback": f"{r['ref']} was the most-quoted chapter.",
                      "stats": f"quoted in {r['talks']} talks; average {num(r['base_per_conf'], 1)} "
                               f"per conference before"})
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
p{margin:.5em 0}.sub,.blurb,.src,.who,.none{color:var(--text2)}.blurb{font-size:.93rem}
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
function name(o){var y=1971+Math.floor((o-1)/2);return (o%2?'April ':'October ')+y}
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


def build_html(signals, ev, dropped):
    conf_id = signals["conf_id"]
    lex, tp, qs, sc = signals["lexical"], signals["topics"], signals["quotes"], signals["scriptures"]
    con = ev.con
    n_talks, n_words = con.execute(
        "SELECT COUNT(*), SUM(word_count) FROM talks WHERE conf_id=? AND kind='address'",
        (conf_id,)).fetchone()
    n_speakers = con.execute("SELECT COUNT(DISTINCT speaker_id) FROM talks WHERE conf_id=? "
                             "AND kind='address'", (conf_id,)).fetchone()[0]
    n_confs, n_all = con.execute(
        "SELECT COUNT(DISTINCT conf_id), COUNT(*) FROM talks WHERE kind='address' AND conf_id < ?",
        (conf_id,)).fetchone()
    topics = [t for t in tp["topics"] if not t["junk"]]
    first = tp["first_conf_ord"]
    out = []
    add = out.append

    # ---- header
    add(f"<h1>{esc(conf_name(conf_id))} General Conference: what stood out</h1>")
    add(f"<p class='sub'>What was new, rising, continuing, fading and missing in the words, topics, "
        f"quotations and scriptures of this conference, measured against the {n_confs} conferences "
        f"({num(n_all)} talks) since April 1971.</p>")
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
    add("<p class='blurb'>Small grey charts show every conference from April 1971 to now; the "
        "blue dot is this conference. Point at a chart to read a value. “Evidence” opens the "
        "counts and talks behind a line. “Previous 10 conferences” means "
        f"{esc(ord_name(ev.c - BASELINE_N))} through {esc(ord_name(ev.c - 1))}.</p>")

    # ---- 1 headline
    facts = headline_facts(signals, ev)
    sentences = narrate(facts, conf_id)
    add('<section id="s1"><h2>1. Headlines</h2><ol class="head">' + "".join(
        f"<li>{esc(s)}<div class='fig'>{esc(f['stats'])}</div></li>"
        for s, f in zip(sentences, facts)) + "</ol></section>")

    # ---- 2 topics
    add('<section id="s2"><h2>2. Topics</h2>')
    add(f"<p class='blurb'>Every talk was cut into passages of a few sentences ({tp['total_passages']} "
        f"this conference) and each passage was matched to one of {signals['topic_model']['topics']} "
        "long-running topics found in talks since 1971. A topic's share is the part of all "
        "passages that matched it. The black tick on each bar is the share in the previous "
        f"{BASELINE_N} conferences.</p><h3>Most-discussed topics</h3>")
    top_share = max(t["share"] for t in topics[:12]) * 1.05
    add("".join(topic_row(t, ev, top_share, first) for t in topics[:12]))
    movers_up = sorted((t for t in topics if t["z"] > 0 and t["talks"] >= 3), key=lambda t: -t["z"])[:6]
    movers_dn = sorted((t for t in topics if t["z"] < 0 and t["base_passages"] >= 30), key=lambda t: t["z"])[:6]
    add("<h3>Biggest moves against the previous ten conferences</h3><div class='two'><div>"
        "<p class='blurb'>Discussed more than usual</p>" + "".join(
            f"<p class='up'><strong>{esc(t['label'])}</strong> <span class='fig'>{pct(t['share'])} of "
            f"passages, was {pct(t['base_share'])} · {plural(t['talks'], 'talk')}</span></p>" for t in movers_up)
        + "</div><div><p class='blurb'>Discussed less than usual</p>" + "".join(
            f"<p class='dn'><strong>{esc(t['label'])}</strong> <span class='fig'>{pct(t['share'])} of "
            f"passages, was {pct(t['base_share'])} · {plural(t['talks'], 'talk')}</span></p>" for t in movers_dn)
        + "</div></div>")
    absent = [t for t in topics if t["class"] == "absent"]
    if absent:
        add("<h3>Regular topics not touched this time</h3><p class='chips'>" + "".join(
            f"<span>{esc(t['label'])} <span class='fig'>(was {pct(t['base_share'])} of passages)</span></span>"
            for t in absent) + "</p>")
    add(f"<h3>Subjects that fit no long-running topic</h3><p class='blurb'>{tp['no_topic_passages']} "
        f"of {tp['total_passages']} passages matched no topic. Where several of them resembled "
        "each other, they are grouped here.</p>")
    cands = sorted(signals["new_topics"], key=lambda c: (c.get("kind") != "subject", -c["passages"]))
    for cand in cands:
        kind = "A subject" if cand.get("kind") == "subject" else "A story"
        who = ", ".join(cand["speakers"])
        add(f"<div class='row'><div class='term'>{esc(cand['label'])}"
            f"<div class='who'>{esc(who)}</div></div><div></div>"
            f"<div class='fig'>{kind} · {cand['passages']} passages · "
            f"{plural(len(cand['speakers']), 'speaker')}</div>"
            + details("Evidence", "<p>Opening words of the passages (transcript):</p><ul>" + "".join(
                f"<li>“{esc(' '.join(s.split()[:28]))} …”</li>" for s in cand["samples"]) + "</ul>")
            + "</div>")
    if not cands:
        add("<p class='none'>No groups found.</p>")
    add("</section>")

    # ---- 3 new and revived
    add('<section id="s3"><h2>3. New and revived words and phrases</h2>')
    add(lexical_block("New", "Never used in a conference talk since 1971 until now, and used by at "
                      "least two speakers this time.", lex["new"], ev, "new"))
    add(lexical_block("Revived", f"Used in the past, absent from all of the previous {BASELINE_N} "
                      "conferences, and back with at least three speakers.", lex["revived"], ev, "revived"))
    add("</section>")

    # ---- 4 rising / continuing / fading / absent
    add('<section id="s4"><h2>4. Rising, continuing, fading and absent phrases</h2>')
    add(lexical_block("Rising", "Used clearly more than in the previous ten conferences, and by at "
                      "least three speakers.", lex["rising"], ev, "rising"))
    add(lexical_block("Continuing: entered recently and stuck", "Took off within the last few "
                      "conferences and was still being used this time by at least three speakers.",
                      lex["continuing"], ev, "continuing"))
    add(lexical_block("Emphasised by one or two speakers", "Stood out strongly, but in only one or "
                      "two talks, so it is one speaker's emphasis and not a conference-wide trend.",
                      lex["single"], ev, "single"))
    add(lexical_block("Fading", "Surged in one of the previous six conferences and has fallen back "
                      "to well under half of that peak.", lex["fading"], ev, "fading"))
    add(lexical_block("Absent", f"Used in at least eight of the previous {BASELINE_N} conferences, "
                      "but not once this time.", lex["absent"], ev, "absent"))
    add("</section>")

    # ---- 5 quotes
    add('<section id="s5"><h2>5. Quotations</h2>')
    add("<p class='blurb'>Found by matching runs of seven or more identical words between talks by "
        "different speakers, leaving out scripture. A passage counts as a quotation when later "
        "talks usually put it in quotation marks.</p>")
    add(f"<h3>Established quotations repeated this conference</h3>")
    add("".join(quote_block(q, conf_id) for q in qs["repeated"][:12]) or "<p class='none'>None found.</p>")
    add("<h3>The most-repeated quotations since 1971</h3><p class='blurb'>For context: the passages "
        "repeated by the most different speakers in all conferences since 1971.</p>")
    add("".join(quote_block(q, conf_id, show_here=False) for q in qs["all_time"]))
    add(f"<h3>Most-repeated lines from the last {BASELINE_N} conferences</h3>")
    add("".join(quote_block(q, conf_id, show_here=False) for q in qs["recent"])
        or "<p class='none'>None yet.</p>")
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
    add(f"<p class='blurb'>Counted from verses quoted word-for-word in the talks (eight or more "
        f"consecutive words matching the standard works): {sc['total_quotes']} verse quotations this "
        "conference. A verse that a speaker only refers to, without quoting, is not counted.</p>")
    add("<h3>Chapters quoted by the most talks</h3>" + scripture_table(sc["top_chapters"], ev, "Chapter"))
    add("<h3>Verses quoted by the most talks</h3>" + scripture_table(sc["top_verses"], ev, "Verse"))
    add("<h3>Movers</h3><div class='two'><div><p class='blurb'>Quoted by more talks than usual</p>"
        + ("".join(f"<p class='up'><strong>{esc(r['ref'])}</strong> <span class='fig'>{r['talks']} talks; "
                   f"{r['base_talks']} in the previous {BASELINE_N} conferences combined</span></p>"
                   for r in sc["up"]) or "<p class='none'>None.</p>")
        + "</div><div><p class='blurb'>Often quoted before, not quoted this time</p>"
        + "".join(f"<p class='dn'><strong>{esc(r['ref'])}</strong> <span class='fig'>0 talks; "
                  f"{r['base_talks']} in the previous {BASELINE_N} conferences combined</span></p>"
                  for r in sc["down"]) + "</div></div>")
    add("<h3>By book of scripture</h3><div class='scroll'><table><thead><tr><th>Volume</th>"
        f"<th>Verse quotations</th><th>Share now</th><th>Share, previous {BASELINE_N}</th></tr></thead><tbody>"
        + "".join(f"<tr><td>{esc(v['volume'])}</td><td>{v['quotes']}</td>"
                  f"<td>{pct(v['quotes'] / max(sc['total_quotes'], 1))}</td>"
                  f"<td>{pct(v['base_quotes'] / max(sc['base_total_quotes'], 1))}</td></tr>"
                  for v in sc["volumes"]) + "</tbody></table></div></section>")

    # ---- 7 groups
    labels = {t["topic_id"]: t for t in tp["topics"]}
    names = {"First Presidency": "First Presidency", "Twelve": "Quorum of the Twelve Apostles",
             "Other": "Other speakers (Seventies, Presiding Bishopric, general officers)"}
    add('<section id="s7"><h2>7. Who said what</h2><p class="blurb">The same measures split by the '
        "speaker's calling at this conference.</p>")
    for g in signals["groups"]:
        shown = [t for t in g["topics"] if not labels[t["topic_id"]]["junk"]][:5]
        add(f"<h3>{esc(names[g['group']])}</h3><div class='fig'>{g['talks']} talks · "
            f"{num(g['words'])} words · {g['passages']} passages</div>"
            + details("Speakers", "<p>" + esc(", ".join(g["speakers"])) + "</p>")
            + "<p>Leading topics: " + "; ".join(
                f"{esc(labels[t['topic_id']]['label'])} <span class='fig'>({plural(t['passages'], 'passage')}, "
                f"{plural(t['talks'], 'talk')})</span>" for t in shown) + ".</p>"
            + ("<p>Words this group used much more than the other speakers did: " + ", ".join(
                f"{esc(d['term'])} <span class='fig'>({d['count']} uses, {d['speakers']} speakers; "
                f"others {d['rest_count']})</span>" for d in g["distinctive"][:8]) + ".</p>"
               if g["distinctive"] else ""))
    add("</section>")

    # ---- 8 method
    tm = signals["topic_model"]
    add('<section id="s8"><h2>8. Method and caveats</h2><ul>')
    add(f"<li><strong>Sources.</strong> Conferences from April 1971 through April 2026 come from the "
        f"Church's published text ({num(n_all)} talks). "
        + ("This conference comes from automatic transcripts of the broadcast audio "
           "(names were corrected by hand; immediately doubled words were removed). " if signals["provisional"] else "")
        + "Sustainings, audit and statistical reports are left out.</li>")
    add(f"<li><strong>Baseline.</strong> “Previous {BASELINE_N} conferences” is {esc(ord_name(ev.c - BASELINE_N))} "
        f"through {esc(ord_name(ev.c - 1))}. Rates are uses per 10,000 words, so longer or shorter "
        "conferences compare fairly.</li>")
    add("<li><strong>Phrases.</strong> One- to five-word phrases are counted within sentences. "
        "Phrases that begin or end with a filler word (the, of, and …) are skipped. Words quoted "
        "from scripture are not counted as the speaker's own.</li>")
    add("<li><strong>Thresholds.</strong> New: never used before, at least two speakers. Revived: "
        f"absent for {BASELINE_N} conferences, at least three speakers. Rising: at least three speakers, "
        "at least 1.5 times the earlier rate, and a log-odds z-score (with an informative Dirichlet "
        "prior) of at least 3 on uses and 2 on speakers. Continuing: two to seven conferences in a "
        "row at three times the earlier rate. Fading: a recent surge now below 40% of its peak. "
        f"Absent: used in at least eight of the previous {BASELINE_N} conferences, at least three uses "
        "expected, none found.</li>")
    add("<li><strong>Left out.</strong> Speakers' names, names of people and places in stories, "
        "spoken markers such as “quote”, and words that are neither in a dictionary nor in any "
        "earlier talk (likely transcription errors). An AI model also screened the listed phrases "
        f"for names, places and transcript noise and removed {len(dropped)}"
        + (": " + esc(", ".join(sorted(dropped))) if dropped else "") + ".</li>")
    add(f"<li><strong>Topics.</strong> {tm['passages']:,} passages from 1971 to April 2026 were grouped by "
        f"meaning with a language model run locally ({esc(tm['model'])}); the {tm['topics']} topics "
        "are frozen so that shares stay comparable between conferences. Topic names were written "
        "by an AI model from each topic's typical words and passages. Topic moves use the same "
        "z-score, threshold 2. With only a few hundred passages per conference, small topic "
        "shifts are within normal variation.</li>")
    add("<li><strong>Quotations.</strong> Text matching finds word-for-word reuse only, not "
        "paraphrase. The “origin” is the earliest use since 1971; where that earliest use was itself "
        "inside quotation marks the page says the speaker was quoting an earlier source. Quotations "
        "shown are 40 words or fewer.</li>")
    add("<li><strong>Scriptures.</strong> Only word-for-word quotations are counted. Passages that "
        "appear in two books (for example Malachi 3 and 3 Nephi 24) are counted under both.</li>")
    add("<li><strong>Sentences.</strong> The headline sentences were written by an AI model from "
        "the computed tables. Every number on this page was computed by code from the talk "
        "texts; none was written by an AI model.</li>")
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
    ev = Evidence(con, conf_id)
    dropped = screen_terms(signals)
    label_new_topics(signals["new_topics"])
    page = build_html(signals, ev, dropped)
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / f"{conf_id}.html"
    out.write_text(page)
    log(f"wrote {out} ({len(page.encode()) / 1024:.0f} KB)")
