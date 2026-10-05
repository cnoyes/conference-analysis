"""Parse the cached API JSON (data/raw/api/) into corpus.db. No network."""
import json
import re
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from .config import api_conferences
from .db import (calling_group, conf_ordinal, connect, ensure_conference,
                 speaker_id_for, tokenize)
from .fetch import cache_path, item_uris

# Items typed as talks by the API that are not addresses.
BUSINESS_TITLE = re.compile(
    r"sustaining of|audit|statistical report|officers sustained|solemn assembly|"
    r"^report of the|church finance committee|video presentation|^video:", re.I)


def clean_text(node):
    """Visible text of a paragraph, footnote markers removed."""
    for sup in node.select("sup, a.note-ref"):
        sup.decompose()
    text = node.get_text("", strip=False).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def parse_ref(href):
    """Classify a link. Returns a dict for scripture/talk targets, else None."""
    href = href.replace("&amp;", "&")
    url = urlparse(href)
    path = re.sub(r"^/study", "", url.path).rstrip("/")
    m = re.match(r"^/scriptures/([^/]+)/([^/]+)(?:/(\d+))?$", path)
    if m:
        ids = unquote(parse_qs(url.query).get("id", [""])[0])
        verses = re.sub(r"p(\d+)", r"\1", ids) if re.fullmatch(r"[p\d,\-]*", ids) else ""
        return {"target_type": "scripture", "target_uri": path, "volume": m[1], "book": m[2],
                "chapter": int(m[3]) if m[3] else None, "verses": verses}
    m = re.match(r"^/general-conference/(\d{4})/(\d{2})/([^/]+)$", path)
    if m and not m[3].endswith("-session"):
        return {"target_type": "talk", "target_uri": path, "volume": None, "book": None,
                "chapter": None, "verses": None}
    return None


def sessions_from_index(index_json):
    """uri -> session title, from the conference index page."""
    soup = BeautifulSoup(index_json["content"]["body"], "lxml")
    out = {}
    for li in soup.select('li[data-content-type="general-conference-session"]'):
        title = li.select_one("p.title")
        name = title.get_text(" ", strip=True) if title else ""
        for a in li.select("a[href]"):
            m = re.search(r"/study(/general-conference/\d{4}/\d{2}/[^?#]+)", a["href"])
            if m:
                out[m[1]] = name
    return out


def parse_talk(data):
    """API JSON for one item -> dict of fields, paragraphs, footnotes, citations."""
    meta, content = data["meta"], data["content"]
    soup = BeautifulSoup(content.get("body") or "", "lxml")
    ctype = meta.get("pageAttributes", {}).get("data-content-type", "")
    title = (meta.get("title") or "").replace("\xa0", " ").strip()

    author = soup.select_one("p.author-name")
    role = soup.select_one("p.author-role")
    speaker_raw = clean_text(author) if author else ""
    role_raw = clean_text(role) if role else ""
    m = re.search(r'"author":\{[^}]*"name":"([^"]+)"', meta.get("structuredData") or "")
    speaker_clean = m[1].replace("\\u00a0", " ") if m else speaker_raw

    for junk in soup.select("header, footer, figure, video, .page-break"):
        junk.decompose()
    block = soup.select_one("div.body-block") or soup.body or soup
    paragraphs, citations = [], []
    for p in block.find_all("p"):
        refs = [parse_ref(a["href"]) for a in p.select("a[href]")
                if "note-ref" not in a.get("class", [])]
        text = clean_text(p)
        if not text:
            continue
        paragraphs.append({"pid": p.get("data-aid"), "text": text})
        citations += [dict(r, fn=None) for r in refs if r]

    pid_pos = {p["pid"]: i for i, p in enumerate(paragraphs, 1) if p["pid"]}
    footnotes = []
    for note in (content.get("footnotes") or {}).values():
        text = clean_text(BeautifulSoup(note.get("text") or "", "lxml"))
        footnotes.append({"marker": (note.get("marker") or "").strip(". "),
                          "para_position": pid_pos.get(note.get("pid")), "text": text})
        # referenceUris is not always complete; the links in the note HTML are
        for href in re.findall(r'href="([^"]+)"', note.get("text") or ""):
            ref = parse_ref(href)
            if ref:
                citations.append(dict(ref, fn=len(footnotes) - 1))

    words = sum(len(tokenize(p["text"])) for p in paragraphs)
    if ctype == "general-conference-session":
        kind = "session"
    elif ctype != "general-conference-talk" or BUSINESS_TITLE.search(title):
        kind = "business"
    elif not speaker_clean or words < 150:
        kind = "other"
    else:
        kind = "address"
    return {"title": title, "speaker_raw": speaker_raw, "speaker_clean": speaker_clean,
            "role_raw": role_raw, "kind": kind, "word_count": words,
            "paragraphs": paragraphs, "footnotes": footnotes, "citations": citations}


def delete_talk_rows(con, where, args=()):
    ids = f"SELECT talk_id FROM talks WHERE {where}"
    for table in ("paragraphs", "footnotes", "citations", "para_norm"):
        con.execute(f"DELETE FROM {table} WHERE talk_id IN ({ids})", args)
    con.execute(f"DELETE FROM talks WHERE {where}", args)


def insert_talk(con, talk_id, conf_id, uri, session, position, t, source, provisional=0,
                group=None):
    sid = speaker_id_for(con, t["speaker_raw"], t["speaker_clean"]) if t["speaker_clean"] else None
    con.execute(
        "INSERT INTO talks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (talk_id, conf_id, uri, t["title"], sid, t["speaker_raw"], t["role_raw"],
         group or calling_group(t["role_raw"]), t["kind"], session, position,
         t["word_count"], source, provisional))
    con.executemany("INSERT INTO paragraphs VALUES (?,?,?,?,?)",
                    [(talk_id * 1000 + i, talk_id, i, p["pid"], p["text"])
                     for i, p in enumerate(t["paragraphs"], 1)])
    fn_ids = []
    for f in t["footnotes"]:
        cur = con.execute(
            "INSERT INTO footnotes (talk_id, marker, para_position, text) VALUES (?,?,?,?)",
            (talk_id, f["marker"], f["para_position"], f["text"]))
        fn_ids.append(cur.lastrowid)
    con.executemany(
        "INSERT INTO citations (talk_id, fn_id, target_type, target_uri, volume, book, chapter,"
        " verses) VALUES (?,?,?,?,?,?,?,?)",
        [(talk_id, fn_ids[c["fn"]] if c["fn"] is not None else None, c["target_type"],
          c["target_uri"], c["volume"], c["book"], c["chapter"], c["verses"])
         for c in t["citations"]])


def build(log=print):
    """Rebuild every API-sourced row from the cache. Idempotent; scribe rows untouched."""
    con = connect()
    delete_talk_rows(con, "source='api'")
    total = 0
    for conf_id in api_conferences():
        year, month = conf_id.split("-")
        index_path = cache_path(f"/general-conference/{year}/{month}")
        if not index_path.exists():
            continue
        index = json.loads(index_path.read_text())
        sessions = sessions_from_index(index)
        ensure_conference(con, conf_id)
        for position, uri in enumerate(item_uris(index), 1):
            path = cache_path(uri)
            if not path.exists():
                continue
            data = json.loads(path.read_text())
            if "_status" in data:
                continue
            insert_talk(con, conf_ordinal(conf_id) * 100 + position, conf_id, uri,
                        sessions.get(uri, ""), position, parse_talk(data), "api")
            total += 1
    con.commit()
    log(f"built {total} items from cache")
    return total
