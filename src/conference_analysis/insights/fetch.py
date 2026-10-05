"""Fetch raw JSON from the Church content API into data/raw/api/ (the scrape cache).

One connection, at most ~2.5 requests/second, exponential backoff on errors.
Everything already cached is skipped, so a second run makes zero network calls.
"""
import json
import re
import time

import requests

from .config import RAW_API, api_conferences

API = "https://www.churchofjesuschrist.org/study/api/v3/language-pages/type/content"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
MIN_INTERVAL = 0.4  # seconds between requests (2.5 req/s, under the 3 req/s cap)
ITEM_LINK = re.compile(r'href="/study(/general-conference/\d{4}/\d{2}/[^"?#]+)')


class Fetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = UA
        self.last = 0.0
        self.network_calls = 0

    def get(self, uri):
        """Return the API JSON for uri, or {'_status': code} for a permanent miss."""
        for attempt in range(7):
            wait = self.last + MIN_INTERVAL - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
            self.network_calls += 1
            try:
                r = self.session.get(API, params={"lang": "eng", "uri": uri}, timeout=30)
            except requests.RequestException:
                time.sleep(2 ** attempt * 2)
                continue
            if r.status_code == 200:
                return r.json()
            if r.status_code in (404, 410):
                return {"_status": r.status_code}
            # 429 / 5xx: honour the error and back off
            time.sleep(float(r.headers.get("Retry-After", 0)) or 2 ** attempt * 5)
        raise RuntimeError(f"gave up on {uri}")


def cache_path(uri):
    """/general-conference/2016/10/slug -> data/raw/api/2016-10/slug.json (index: _index.json)"""
    parts = uri.strip("/").split("/")
    name = parts[3] if len(parts) > 3 else "_index"
    return RAW_API / f"{parts[1]}-{parts[2]}" / f"{name}.json"


def item_uris(index_json):
    """URIs of every item a conference index lists, in page order, de-duplicated."""
    body = (index_json.get("content") or {}).get("body") or ""
    return list(dict.fromkeys(ITEM_LINK.findall(body)))


def fetch_all(log=print):
    """Fill the cache. Returns the number of network calls made."""
    fetcher = Fetcher()

    def cached(uri):
        path = cache_path(uri)
        if not path.exists():
            data = fetcher.get(uri)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data))
            tmp.rename(path)
        return json.loads(path.read_text())

    for conf_id in reversed(api_conferences()):  # newest first: most-used data lands early
        year, month = conf_id.split("-")
        before = fetcher.network_calls
        uris = item_uris(cached(f"/general-conference/{year}/{month}"))
        for uri in uris:
            cached(uri)
        if fetcher.network_calls > before:
            log(f"{conf_id}: {len(uris)} items, {fetcher.network_calls - before} fetched")
    log(f"network calls: {fetcher.network_calls}")
    return fetcher.network_calls
