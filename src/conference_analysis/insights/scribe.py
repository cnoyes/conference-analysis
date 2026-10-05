"""Ingest ldt-scribe transcripts as a provisional conference (read-only source)."""
import re

import yaml

from .build import delete_talk_rows, insert_talk
from .config import SCRIBE_MEETINGS
from .db import calling_group, conf_ordinal, connect, ensure_conference, speaker_key, tokenize

# conf_id -> session directories under ldt-scribe/meetings, in conference order.
# The separate partial recording "...president-oaks-october-2026" is deliberately absent.
SESSIONS = {
    "2026-10": [
        ("Saturday Morning Session", "2026-10-03-general-conference-saturday-morning-session"),
        ("Saturday Afternoon Session", "2026-10-03-general-conference-saturday-afternoon-session"),
        ("Sunday Morning Session", "2026-10-04-general-conference-sunday-morning-session-october-2026"),
        ("Sunday Afternoon Session", "2026-10-04-general-conference-sunday-afternoon-session-october-2026"),
    ],
}


def read_talk(path):
    """A scribe talk file -> (front matter dict, list of paragraph strings)."""
    _, front, body = path.read_text().split("---\n", 2)
    paragraphs = [re.sub(r"\s+", " ", p).strip() for p in body.split("\n\n")]
    # a "©" paragraph is a whisper hallucination ("© transcript ..."), never speech
    return yaml.safe_load(front), [p for p in paragraphs
                                   if p and not p.startswith("#") and "©" not in p]


def callings(session_dir):
    """speaker key -> calling, from the session's program.yaml."""
    program = yaml.safe_load((session_dir / "program.yaml").read_text())
    return {speaker_key(item["name"]): item.get("calling", "")
            for item in program.get("program", []) if item.get("type") == "talk"}


def ingest(conf_id="2026-10", log=print):
    """Replace the provisional conference's rows. Idempotent."""
    con = connect()
    delete_talk_rows(con, "conf_id=? AND source='scribe'", (conf_id,))
    ensure_conference(con, conf_id, provisional=1)
    position = 0
    for session, dirname in SESSIONS[conf_id]:
        session_dir = SCRIBE_MEETINGS / dirname
        calling = callings(session_dir)
        for path in sorted((session_dir / "talks").glob("*.md")):
            front, paragraphs = read_talk(path)
            position += 1
            speaker = front["speaker"]
            role = calling.get(speaker_key(speaker), "")
            talk = {
                "title": "", "speaker_raw": speaker, "speaker_clean": speaker, "role_raw": role,
                "kind": "address",
                "word_count": sum(len(tokenize(p)) for p in paragraphs),
                "paragraphs": [{"pid": None, "text": p} for p in paragraphs],
                "footnotes": [], "citations": [],
            }
            insert_talk(con, conf_ordinal(conf_id) * 100 + position, conf_id,
                        f"scribe:{dirname}/{path.stem}", session, position, talk,
                        "scribe", provisional=1, group=calling_group(role))
    con.commit()
    log(f"ingested {position} provisional talks for {conf_id}")
    return position
