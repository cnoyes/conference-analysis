"""Insights engine tests.

Pure-function tests always run. Tests marked `corpus` run against the real
data/corpus.db (never fixtures) and are skipped when it has not been built.
"""
import re

import pytest

from conference_analysis.insights import config
from conference_analysis.insights.build import parse_ref
from conference_analysis.insights.db import (calling_group, clean_speaker, conf_ordinal, connect,
                                             speaker_key, tokenize)
from conference_analysis.insights.ngrams import count_occurrences, meaningful, phrase_history
from conference_analysis.insights.signals import dedupe, fragments
from conference_analysis.insights.text import clean_tokens, tokens_with_quotes
from conference_analysis.insights.topics import MIN_WORDS, split_passages

corpus = pytest.mark.skipif(not config.CORPUS_DB.exists(), reason="data/corpus.db not built")


# ------------------------------------------------------------ pure functions

@pytest.mark.parametrize("raw", [
    "By President Russell M. Nelson", "Russell M. Nelson", "Elder Russell M. Nelson",
    "Presented by President Russell\xa0M. Nelson"])
def test_speaker_variants_share_one_key(raw):
    assert clean_speaker(raw) == "Russell M. Nelson"
    assert speaker_key(raw) == "russell m nelson"


def test_speaker_key_ignores_accents():
    assert speaker_key("Gérald Caussé") == speaker_key("Gerald Causse")


def test_calling_group():
    assert calling_group("President of the Church") == "First Presidency"
    assert calling_group("Second Counselor in the First Presidency") == "First Presidency"
    assert calling_group("Of the Quorum of the Twelve Apostles") == "Twelve"
    assert calling_group("Acting President of the Quorum of the Twelve Apostles") == "Twelve"
    assert calling_group("Assistant to the Council of the Twelve") == "Other"
    assert calling_group("Of the Seventy") == "Other"


def test_conf_ordinal():
    assert conf_ordinal("1971-04") == 1
    assert conf_ordinal("1971-10") == 2
    assert conf_ordinal("2026-10") == 112


def test_parse_ref_scripture_and_talk():
    ref = parse_ref("/study/scriptures/bofm/2-ne/2?lang=eng&amp;id=p25#p25")
    assert (ref["target_type"], ref["book"], ref["chapter"], ref["verses"]) == \
        ("scripture", "2-ne", 2, "25")
    assert parse_ref("/study/scriptures/ot/ps/16?lang=eng&amp;id=p8%2Cp11#p8")["verses"] == "8,11"
    talk = parse_ref("/study/general-conference/2022/04/47nelson?lang=eng&amp;id=p21-p22#p21")
    assert talk["target_uri"] == "/general-conference/2022/04/47nelson"
    assert parse_ref("/study/general-conference/2022/04/saturday-morning-session") is None
    assert parse_ref("https://speeches.byu.edu/talks/x") is None


def test_tokens_track_quotes_and_sentences():
    triples = tokens_with_quotes("He said, “Come unto me.” Then we left.")
    assert [t[0] for t in triples] == ["he", "said", "come", "unto", "me", "then", "we", "left"]
    assert [t[1] for t in triples] == [False, False, True, True, True, False, False, False]
    assert [t[2] for t in triples] == [True, False, False, False, False, True, False, False]


def test_doubled_words_collapse_only_when_asked():
    assert len(tokens_with_quotes("He said, said that")) == 4
    assert [t[0] for t in tokens_with_quotes("He said, said that", collapse_doubles=True)] == \
        ["he", "said", "that"]


def test_abbreviations_and_initials_do_not_end_sentences():
    triples = tokens_with_quotes("President Dallin H. Oaks met Mr. Martin. He smiled.")
    starts = [t[0] for t in triples if t[2]]
    assert starts == ["president", "he"]


def test_repeated_phrases_collapse_in_transcripts():
    words = [t[0] for t in tokens_with_quotes("he replied he replied that it was was fine",
                                              collapse_doubles=True)]
    assert words == ["he", "replied", "that", "it", "was", "fine"]


def test_digits_leave_no_stray_tokens():
    assert tokenize("In the 1980s we had 3 sons") == ["in", "the", "we", "had", "sons"]


def test_report_text_helpers():
    from conference_analysis.insights.report import ord_name, show_term, tidy_quote, unstutter
    assert ord_name(1) == "April 1971" and ord_name(112) == "October 2026"
    assert ord_name(0) == "October 1970" and ord_name(-57) == "April 1942"
    assert show_term("close to jesus christ") == "close to Jesus Christ"
    assert unstutter("it is is an activity, he'd, he'd say") == "it is an activity, he'd say"
    assert tidy_quote("judgment. They need love. It is") == "They need love."
    assert tidy_quote("is not content with blessing his family alone") == \
        "… is not content with blessing his family alone …"


def test_clean_tokens_breaks_sentences_and_masks_scripture():
    toks = ["a", "b", "c", "d"]
    assert clean_tokens(toks, [True, False, True, False], [False] * 4) == ["a", "b", "|", "c", "d"]
    assert clean_tokens(toks, [True, False, False, False], [False, True, True, False]) == \
        ["a", "|", "d"]


def test_meaningful_reuses_stopword_position_rule():
    assert meaningful("covenant path", 2)
    assert not meaningful("the covenant", 2)
    assert meaningful("let god prevail", 3)
    assert meaningful("brothers and sisters", 3)
    assert not meaningful("and sisters of", 3)


def test_count_occurrences():
    assert count_occurrences(" a b a b a ", " a b a ") == 2
    assert count_occurrences(" think celestial ", " celestial ") == 1


def test_fragments_and_dedupe():
    terms = ["stake high", "stake high priests", "ministering"]
    assert fragments(terms, [10, 9, 5]) == {"stake high"}
    kept = dedupe([{"term": "covenant path", "key": 10}, {"term": "the covenant path", "key": 9},
                   {"term": "ministering", "key": 3}])
    assert [k["term"] for k in kept] == ["covenant path", "ministering"]


def test_one_edit():
    from conference_analysis.insights.signals import one_edit
    assert one_edit("fulness", "fullness") and one_edit("worshiped", "worshipped")
    assert one_edit("grace", "grade") and not one_edit("grace", "grace")
    assert not one_edit("faith", "fruit")


def test_split_passages_merges_short_paragraphs():
    paras = [(1, "one two three"), (2, " ".join(["w"] * MIN_WORDS)), (3, "tail")]
    passages = split_passages(paras)
    assert len(passages) == 1 and passages[0][:2] == (1, 3)


def test_tokenize_normalises_apostrophes():
    assert tokenize("The Lord’s people") == ["the", "lord's", "people"]


# ------------------------------------------------------------ real corpus

@pytest.fixture(scope="module")
def con():
    return connect()


@corpus
def test_corpus_is_complete(con):
    api = con.execute("SELECT COUNT(DISTINCT conf_id) FROM talks WHERE source='api'").fetchone()[0]
    assert api == 111
    assert con.execute("SELECT MIN(conf_id), MAX(conf_id) FROM talks WHERE source='api'"
                       ).fetchone()[:] == ("1971-04", "2026-04")
    scribe = con.execute("SELECT COUNT(*), SUM(provisional) FROM talks WHERE source='scribe'")
    assert scribe.fetchone()[:] == (37, 37)
    empty = con.execute(
        "SELECT COUNT(*) FROM talks t WHERE kind='address' AND NOT EXISTS "
        "(SELECT 1 FROM paragraphs p WHERE p.talk_id = t.talk_id)").fetchone()[0]
    assert empty == 0
    assert con.execute("SELECT COUNT(*) FROM footnotes").fetchone()[0] > 20000


@corpus
def test_no_talk_double_counted(con):
    two_sources = con.execute(
        "SELECT COUNT(*) FROM (SELECT conf_id FROM talks GROUP BY conf_id "
        "HAVING COUNT(DISTINCT source) > 1)").fetchone()[0]
    assert two_sources == 0
    same_text = con.execute(  # two addresses in one conference with the same third paragraph
        "SELECT COUNT(*) FROM (SELECT t.conf_id, p.text FROM talks t JOIN paragraphs p USING (talk_id) "
        "WHERE t.kind='address' AND p.position = 3 AND length(p.text) > 200 "
        "GROUP BY 1, 2 HAVING COUNT(*) > 1)").fetchone()[0]
    assert same_text == 0


@corpus
@pytest.mark.parametrize("name", ["Russell M. Nelson", "Dallin H. Oaks", "Henry B. Eyring",
                                  "Jeffrey R. Holland"])
def test_one_speaker_id_per_person(con, name):
    last = name.split()[-1].lower()
    first = name.split()[0].lower()
    ids = con.execute("SELECT speaker_id FROM speakers WHERE name_key LIKE ? AND name_key LIKE ?",
                      (f"{first}%", f"%{last}")).fetchall()
    assert len(ids) == 1
    raw_variants = con.execute("SELECT COUNT(DISTINCT speaker_raw) FROM talks WHERE speaker_id=?",
                               (ids[0][0],)).fetchone()[0]
    assert raw_variants >= 2  # several byline spellings really did collapse into one id


def classes_as_of(con, conf_id, term):
    from conference_analysis.insights.signals import lexical_signals
    full = lexical_signals(con, conf_id, full=True)
    return {cls for cls, records in full.items() if any(r["term"] == term for r in records)}


@corpus
@pytest.mark.parametrize("conf_id, term, allowed", [
    ("2018-04", "ministering", {"new", "revived", "rising"}),
    ("2018-04", "covenant path", {"rising", "continuing"}),
    ("2021-04", "let god prevail", {"new", "continuing"}),
    ("2024-04", "think celestial", {"new", "rising", "continuing"}),
    # SPEC deviation (see SPEC changelog): in April 2023 only two speakers used
    # "peacemakers" outside scripture quotation, so the >= 3-speaker guard files it under
    # single-speaker emphasis instead of Rising.
    ("2023-04", "peacemakers", {"rising", "single"}),
    ("2023-04", "let god prevail", {"fading"}),
])
def test_backtest(con, conf_id, term, allowed):
    """As-of backtests: signals read nothing after conf_id (see test_signals_hide_the_future)."""
    assert classes_as_of(con, conf_id, term) & allowed


@corpus
def test_signals_hide_the_future():
    """Deleting every later conference from the index must not change an as-of result."""
    from conference_analysis.insights.signals import lexical_signals
    own = connect()  # private connection: the deletion below is rolled back, never committed
    c = conf_ordinal("2018-04")
    pick = lambda full: {cls: sorted(r["term"] for r in rs if r["count"] >= 8 or cls == "absent")
                         for cls, rs in full.items()}
    before = pick(lexical_signals(own, "2018-04", full=True))
    try:
        own.execute("DELETE FROM term_conf WHERE ord > ?", (c,))
        own.execute("DELETE FROM conf_stats WHERE ord > ?", (c,))
        after = pick(lexical_signals(own, "2018-04", full=True))
    finally:
        own.rollback()
        own.close()
    assert before == after
    assert "ministering" in before["rising"]


@corpus
def test_known_phrase_histories(con):
    by_year = {}
    for conf_id, _, talks, _ in phrase_history(con, "think celestial"):
        by_year[conf_id[:4]] = by_year.get(conf_id[:4], 0) + talks
    assert (by_year["2023"], by_year["2024"], by_year["2025"]) == (1, 10, 1)
    prevail = {c: t for c, _, t, _ in phrase_history(con, "let God prevail")}
    assert prevail["2020-10"] == 1 and prevail["2021-04"] + prevail["2021-10"] == 11


@corpus
def test_nelson_joy_quote_lineage(con):
    from conference_analysis.insights.quotes import leaderboard_rank, quote_lineage
    text = "little to do with the circumstances of our lives"
    uses = quote_lineage(con, text)
    origin = uses[0]
    assert (origin["conf_id"], origin["speaker"], origin["title"]) == \
        ("2016-10", "Russell M. Nelson", "Joy and Spiritual Survival")
    assert len(uses) - 1 >= 10
    rank, _ = leaderboard_rank(con, origin["talk_id"], text)
    assert rank is not None and rank <= 25  # found by the generic index, not special-cased


@corpus
def test_scripture_is_not_a_talk_quote(con):
    """No stored quote is mostly scripture wording (e.g. verses stitched with ellipses)."""
    from conference_analysis.insights.quotes import SCRIPTURE_SHARE
    from conference_analysis.insights.text import scripture_coverage
    texts = [r[0] for r in con.execute(
        "SELECT text FROM quotes ORDER BY later_speakers DESC LIMIT 300")]
    assert texts and all(scripture_coverage(t.split()) < SCRIPTURE_SHARE for t in texts)


@corpus
def test_quote_display_matches_stored_span(con):
    """The words shown for a quote are the words that were counted."""
    from conference_analysis.insights.quotes import display_text
    rows = con.execute(
        "SELECT q.origin_para_id, q.tok_start, q.tok_end, q.text FROM quotes q "
        "JOIN talks t ON t.talk_id = q.origin_talk_id WHERE t.provisional = 0").fetchall()
    for para_id, a, b, text in rows:
        shown = tokenize(display_text(con, para_id, a, b, max_words=10 ** 6))
        assert shown == text.split(), (para_id, text)


@corpus
def test_report_page_contract():
    page = config.REPORTS / "2026-10.html"
    if not page.exists():
        pytest.skip("report not generated")
    html = page.read_text()
    assert len(html.encode()) < 2_000_000
    title = re.search(r"<title>(.*?)</title>", html).group(1)
    assert 2 <= len(title.split()) <= 4
    assert not re.search(r"""\bsrc\s*=|<link\b|<iframe\b""", html)  # nothing is fetched
    assert "@import" not in html and "url(http" not in html
    assert ':root:not([data-theme="light"])' in html and ':root[data-theme="dark"]' in html
    assert "prefers-color-scheme: dark" in html
    assert re.search(r"body\s*\{[^}]*background", html)
    for n in range(1, 9):
        assert f'id="s{n}"' in html
