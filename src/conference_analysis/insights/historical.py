"""Pre-1971 conference text, 1942-1970 (SPEC F6, tier 1 of docs/PRE1971_SOURCES.md).

Source: scriptures.byu.edu. Raw responses are cached under data/raw/historical/byu/ so a
rerun makes no network calls. Rows enter corpus.db with source='historical'.
"""
import re
import time

import requests
from bs4 import BeautifulSoup

from .build import BUSINESS_TITLE, clean_text, delete_talk_rows, insert_talk
from .config import DATA
from .db import calling_group, conf_ordinal, connect, ensure_conference, tokenize
from .fetch import UA

BASE = "https://scriptures.byu.edu"
RAW = DATA / "raw" / "historical" / "byu"
YEARS = range(1942, 1971)
MIN_INTERVAL = 0.6  # seconds between requests (under the 2 req/s the source doc allows)


def fetch_historical(log=print):
    """Cache every conference listing and talk page. Returns the number of network calls."""
    session = requests.Session()
    session.headers["User-Agent"] = UA
    RAW.mkdir(parents=True, exist_ok=True)
    calls, last = 0, 0.0

    def cached(name, url):
        nonlocal calls, last
        path = RAW / name
        if not path.exists():
            for attempt in range(6):
                time.sleep(max(0.0, last + MIN_INTERVAL - time.monotonic()))
                last = time.monotonic()
                calls += 1
                try:
                    r = session.get(url, timeout=30)
                except requests.RequestException:
                    time.sleep(2 ** attempt * 2)
                    continue
                if r.status_code == 200:
                    tmp = path.with_suffix(".tmp")
                    tmp.write_text(r.text)
                    tmp.rename(path)
                    break
                if "gc_ajax" in url and r.status_code in (404, 500) and attempt >= 2:
                    log(f"no listing at {url} (HTTP {r.status_code}); recorded as empty")
                    path.write_text("")  # a permanent miss (October 1957 has no listing)
                    break
                time.sleep(2 ** attempt * 5)
            else:
                raise RuntimeError(f"gave up on {url}")
        return path.read_text()

    for year in YEARS:
        for half in "AO":
            listing = cached(f"conf-{year}-{half}.html", f"{BASE}/citation_index/gc_ajax/{year}/{half}")
            ids = talk_ids(listing)
            for talk_id in ids:
                cached(f"talk-{talk_id}.html", f"{BASE}/content/talks_ajax/{talk_id}")
            log(f"{year}-{half}: {len(ids)} talks")
    log(f"network calls: {calls}")
    return calls


def talk_ids(listing_html):
    """Talk ids in page order from a conference listing."""
    return list(dict.fromkeys(re.findall(r"getTalk\('(\d+)'\)", listing_html)))


def sessions(listing_html):
    """talk id -> session title."""
    out, current = {}, ""
    pattern = r'<div class="sessiontitle">([^<]*)</div>|getTalk\(\'(\d+)\'\)'
    for title, talk in re.findall(pattern, listing_html):
        if title:
            current = title.strip()
        elif talk:
            out.setdefault(talk, current)
    return out


def parse_talk(page_html):
    """A talks_ajax page -> the dict insert_talk expects (citation spans stripped)."""
    soup = BeautifulSoup(page_html, "lxml")
    text_of = lambda sel: clean_text(soup.select_one(sel)) if soup.select_one(sel) else ""
    title, speaker, role = text_of("p.gctitle"), text_of("p.gcspeaker"), text_of("p.gcspkpos")
    body = soup.select_one("div.gcbody")
    paragraphs, citations = [], []
    for p in (body.find_all("p") if body else []):
        for span in p.select("span.citation"):  # the reference, e.g. "1 Cor. 12:11"
            ref = clean_text(span)
            if ref:
                citations.append({"target_type": "scripture", "target_uri": "ref:" + ref,
                                  "volume": None, "book": None, "chapter": None, "verses": None,
                                  "fn": None})
        for span in p.select("span.ccontainer, span.citation"):
            span.decompose()
        text = clean_text(p)
        if text:
            paragraphs.append({"pid": None, "text": text})
    words = sum(len(tokenize(p["text"])) for p in paragraphs)
    kind = "business" if BUSINESS_TITLE.search(title) else "address" if speaker and words >= 150 else "other"
    return {"title": "" if title == "Untitled" else title, "speaker_raw": speaker,
            "speaker_clean": speaker, "role_raw": role, "kind": kind, "word_count": words,
            "paragraphs": paragraphs, "footnotes": [], "citations": citations}


def ingest_historical(log=print):
    """Rebuild every source='historical' row from the cache. Idempotent."""
    con = connect()
    delete_talk_rows(con, "source='historical'")
    con.execute("DELETE FROM conferences WHERE conf_id < '1971-04'")
    total = 0
    for year in YEARS:
        for half, month in (("A", "04"), ("O", "10")):
            listing = RAW / f"conf-{year}-{half}.html"
            if not listing.exists():
                continue
            conf_id = f"{year}-{month}"
            html = listing.read_text()
            session_of = sessions(html)
            ids = [i for i in talk_ids(html) if (RAW / f"talk-{i}.html").exists()]
            if not ids:
                continue  # e.g. October 1957, which the source lists with no talks
            ensure_conference(con, conf_id)
            for position, byu_id in enumerate(ids, 1):
                talk = parse_talk((RAW / f"talk-{byu_id}.html").read_text())
                insert_talk(con, conf_ordinal(conf_id) * 100 + position, conf_id,
                            f"byu:{byu_id}", session_of.get(byu_id, ""), position, talk,
                            "historical", group=calling_group(talk["role_raw"]))
                total += 1
    con.commit()
    log(f"ingested {total} historical items (1942-1970)")
    return total
