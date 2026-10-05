"""Paths and constants shared by every stage."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DATA = REPO / "data"
RAW_API = DATA / "raw" / "api"
CORPUS_DB = DATA / "corpus.db"
TOPICS_DIR = DATA / "topics"
LLM_CACHE = DATA / "llm_cache"
REPORTS = REPO / "reports"
LEGACY = REPO / "legacy"

SCRIBE_MEETINGS = Path.home() / "code" / "ldt-scribe" / "meetings"
SCRIPTURES_DB = Path.home() / "code" / "ldt-search" / "data" / "raw" / "lds-scriptures.db"
CLAUDE_BIN = "/home/clay/.local/bin/claude"

FIRST_CONF = (1971, 4)
LAST_API_CONF = (2026, 4)
BASELINE_N = 10  # trailing conferences used as "recent" baseline


def api_conferences():
    """Every conf_id ('YYYY-MM') the API scrape covers, oldest first."""
    out = []
    for year in range(FIRST_CONF[0], LAST_API_CONF[0] + 1):
        for month in (4, 10):
            if (year, month) <= LAST_API_CONF:
                out.append(f"{year}-{month:02d}")
    return out
