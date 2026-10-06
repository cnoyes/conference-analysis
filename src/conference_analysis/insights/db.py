"""corpus.db: schema and small helpers."""
import json
import re
import sqlite3
import unicodedata

from .config import CORPUS_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS conferences (
    conf_id TEXT PRIMARY KEY,           -- '2026-10'
    year INTEGER, month INTEGER,
    ordinal INTEGER,                    -- 1 = 1971-04, 2 = 1971-10, ...
    provisional INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS speakers (
    speaker_id INTEGER PRIMARY KEY,
    name TEXT,                          -- canonical display name
    name_key TEXT UNIQUE,               -- normalized key (see speaker_key)
    aliases TEXT DEFAULT '[]'           -- JSON list of raw byline strings seen
);
CREATE TABLE IF NOT EXISTS talks (
    talk_id INTEGER PRIMARY KEY,        -- conference ordinal * 100 + position
    conf_id TEXT, uri TEXT UNIQUE, title TEXT,
    speaker_id INTEGER, speaker_raw TEXT, role_raw TEXT,
    calling_group TEXT,                 -- 'First Presidency' | 'Twelve' | 'Other'
    kind TEXT,                          -- 'address' | 'business' | 'session' | 'other'
    session TEXT, position INTEGER, word_count INTEGER,
    source TEXT,                        -- 'api' | 'scribe'
    provisional INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS paragraphs (
    para_id INTEGER PRIMARY KEY,        -- talk_id * 1000 + position
    talk_id INTEGER, position INTEGER,
    pid TEXT,                           -- the API's data-aid, footnotes point at it
    text TEXT
);
CREATE TABLE IF NOT EXISTS footnotes (
    fn_id INTEGER PRIMARY KEY, talk_id INTEGER, marker TEXT,
    para_position INTEGER, text TEXT
);
CREATE TABLE IF NOT EXISTS citations (
    cit_id INTEGER PRIMARY KEY, talk_id INTEGER,
    fn_id INTEGER,                      -- NULL for inline (in-body) references
    target_type TEXT,                   -- 'scripture' | 'talk'
    target_uri TEXT,                    -- '/scriptures/bofm/2-ne/2' or '/general-conference/2016/10/slug'
    volume TEXT, book TEXT, chapter INTEGER,
    verses TEXT                         -- '25', '1-5', '8,11' or '' for a whole chapter
);
CREATE TABLE IF NOT EXISTS para_norm (   -- token view of address paragraphs, see text.py
    para_id INTEGER PRIMARY KEY, talk_id INTEGER, norm TEXT, clean TEXT,
    quoted TEXT, scripture TEXT        -- one '0'/'1' per token of norm
);
CREATE INDEX IF NOT EXISTS para_norm_talk ON para_norm(talk_id);
CREATE INDEX IF NOT EXISTS talks_conf ON talks(conf_id);
CREATE INDEX IF NOT EXISTS para_talk ON paragraphs(talk_id);
CREATE INDEX IF NOT EXISTS fn_talk ON footnotes(talk_id);
CREATE INDEX IF NOT EXISTS cit_talk ON citations(talk_id);
CREATE INDEX IF NOT EXISTS cit_target ON citations(target_type, target_uri);
"""


def connect(path=None):
    path = path or CORPUS_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def conf_ordinal(conf_id):
    year, month = map(int, conf_id.split("-"))
    return (year - 1971) * 2 + (1 if month == 4 else 2)


def ensure_conference(con, conf_id, provisional=0):
    year, month = map(int, conf_id.split("-"))
    con.execute("INSERT OR REPLACE INTO conferences VALUES (?,?,?,?,?)",
                (conf_id, year, month, conf_ordinal(conf_id), provisional))


TITLES = re.compile(
    r"^(by|presented by|read by|given by)\s+|"
    r"^(president|elder|sister|bishop|brother|presiding bishop|patriarch|dr\.?)\s+", re.I)


def clean_speaker(raw):
    """'By President Russell M. Nelson' -> 'Russell M. Nelson'."""
    name = unicodedata.normalize("NFKC", raw or "").replace("\xa0", " ")
    name = re.sub(r"\s+", " ", name).strip(" ,:")
    while True:
        stripped = TITLES.sub("", name).strip()
        if stripped == name:
            break
        name = stripped
    return re.sub(r",?\s+(Jr|Sr)\.?$", r" \1.", name)


def speaker_key(name):
    """Accent-, case- and punctuation-insensitive key: 'Gérald Caussé' -> 'gerald causse'."""
    name = unicodedata.normalize("NFKD", clean_speaker(name))
    name = "".join(c for c in name if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", name)).strip()


def speaker_id_for(con, raw, clean=None):
    """One speaker_id per person; remembers every raw byline variant as an alias."""
    name = clean_speaker(clean or raw)
    key = speaker_key(name)
    if not key:
        return None
    row = con.execute("SELECT speaker_id, aliases FROM speakers WHERE name_key=?", (key,)).fetchone()
    if row is None:
        cur = con.execute("INSERT INTO speakers (name, name_key, aliases) VALUES (?,?,?)",
                          (name, key, json.dumps([raw])))
        return cur.lastrowid
    aliases = json.loads(row["aliases"])
    if raw not in aliases:
        aliases.append(raw)
        con.execute("UPDATE speakers SET aliases=? WHERE speaker_id=?",
                    (json.dumps(aliases), row["speaker_id"]))
    return row["speaker_id"]


def calling_group(role):
    """Calling at the time, from the byline role line."""
    role = (role or "").lower()
    if "first presidency" in role or "president of the church" in role:
        return "First Presidency"
    if "twelve" in role and "assistant" not in role:
        return "Twelve"
    return "Other"


WORD = re.compile(r"(?<![0-9a-z])[a-z]+(?:['’][a-z]+)*")  # "1980s" yields no stray "s"


def tokenize(text):
    """Lower-case word tokens; apostrophes normalised to '."""
    return [w.replace("’", "'") for w in WORD.findall(text.lower())]
