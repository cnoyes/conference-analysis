"""Token-level view of the corpus shared by the n-gram and quote indexes.

Every address paragraph becomes a row in `para_norm`:
  norm  - all tokens, space-joined
  clean - the same, but with a '|' at every sentence boundary and in place of every
          stretch quoted from scripture (6+ consecutive words found in the standard
          works). Signals count on `clean`, so phrases never span sentences and
          scripture quotations never count as a speaker's own words.
  quoted    - one char per token: '1' inside quotation marks, else '0'
  scripture - one char per token: '1' inside a scripture-quoted stretch
"""
import re
import sqlite3

from .config import SCRIPTURES_DB
from .db import tokenize

SCRIPTURE_N = 6
PIECE = re.compile(r"[“”\".!?]|(?<![0-9a-z])[a-z]+(?:['’][a-z]+)*")
ABBREVIATIONS = {"mr", "mrs", "ms", "dr", "st", "jr", "sr", "vs", "no", "vol", "pp", "etc"}

_scripture = None


def scripture_shingles():
    """Set of every 6-word sequence in the standard works, plus the scripture vocabulary."""
    global _scripture
    if _scripture is None:
        con = sqlite3.connect(f"file:{SCRIPTURES_DB}?mode=ro", uri=True)
        shingles, vocab = set(), set()
        for (verse,) in con.execute("SELECT scripture_text FROM verses"):
            toks = tokenize(verse)
            vocab.update(toks)
            for i in range(len(toks) - SCRIPTURE_N + 1):
                shingles.add(" ".join(toks[i:i + SCRIPTURE_N]))
        _scripture = (shingles, vocab)
    return _scripture


_scripture4 = None


def scripture_coverage(tokens):
    """Share of tokens lying inside some 4-word sequence found in the standard works."""
    global _scripture4
    if _scripture4 is None:
        con = sqlite3.connect(f"file:{SCRIPTURES_DB}?mode=ro", uri=True)
        _scripture4 = set()
        for (verse,) in con.execute("SELECT scripture_text FROM verses"):
            toks = tokenize(verse)
            _scripture4.update(" ".join(toks[i:i + 4]) for i in range(len(toks) - 3))
    covered = [False] * len(tokens)
    for i in range(len(tokens) - 3):
        if " ".join(tokens[i:i + 4]) in _scripture4:
            covered[i:i + 4] = [True] * 4
    return sum(covered) / max(len(tokens), 1)


def tokens_with_quotes(text, collapse_doubles=False):
    """[(token, inside_quotes, starts_sentence)] for one paragraph.

    Quote state resets per paragraph. A full stop after an initial or an abbreviation
    ("Dallin H.", "Mr.") does not end the sentence. collapse_doubles drops an immediately
    repeated word or 2-3-word phrase ("said, said", "he replied he replied") - a whisper
    artefact, used for provisional transcripts only.
    """
    out, depth, start = [], False, True
    for piece in PIECE.findall(text.lower()):
        if piece == "“":
            depth = True
        elif piece == "”":
            depth = False
        elif piece == '"':
            depth = not depth
        elif piece in ".!?":
            last = out[-1][0] if out else ""
            start = not (piece == "." and (len(last) == 1 or last in ABBREVIATIONS))
        else:
            out.append((piece.replace("’", "'"), depth, start))
            start = False
            if collapse_doubles:
                words = [t[0] for t in out[-6:]]
                for k in (1, 2, 3):
                    if len(words) >= 2 * k and words[-k:] == words[-2 * k:-k]:
                        del out[-k:]
                        break
    return out


def scripture_mask(tokens):
    """True for each token that sits inside a 6+-word run matching scripture."""
    shingles, _ = scripture_shingles()
    mask = [False] * len(tokens)
    for i in range(len(tokens) - SCRIPTURE_N + 1):
        if " ".join(tokens[i:i + SCRIPTURE_N]) in shingles:
            for j in range(i, i + SCRIPTURE_N):
                mask[j] = True
    return mask


def clean_tokens(tokens, starts, mask):
    """Tokens with '|' at every sentence start and in place of each scripture-quoted run."""
    out = []
    for tok, masked, start in zip(tokens, mask, starts):
        if (masked or start) and out and out[-1] != "|":
            out.append("|")
        if not masked:
            out.append(tok)
    return out


def build_para_norm(con, log=print):
    """Fill para_norm for every address paragraph that lacks a row. Resumable."""
    rows = con.execute(
        "SELECT p.para_id, p.talk_id, p.text, t.provisional FROM paragraphs p "
        "JOIN talks t USING (talk_id) WHERE t.kind='address' "
        "AND p.para_id NOT IN (SELECT para_id FROM para_norm)").fetchall()
    batch = []
    for para_id, talk_id, text, provisional in rows:
        triples = tokens_with_quotes(text, collapse_doubles=bool(provisional))
        toks = [t[0] for t in triples]
        mask = scripture_mask(toks)
        batch.append((para_id, talk_id, " ".join(toks),
                      " ".join(clean_tokens(toks, [t[2] for t in triples], mask)),
                      "".join("1" if t[1] else "0" for t in triples),
                      "".join("1" if m else "0" for m in mask)))
    con.executemany("INSERT INTO para_norm VALUES (?,?,?,?,?,?)", batch)
    con.commit()
    log(f"para_norm: {len(batch)} paragraphs tokenized")
