"""Stopwords and an English dictionary (NLTK data, kept under data/nltk_data)."""
from functools import lru_cache

import warnings

import nltk

from .config import DATA

NLTK_DIR = DATA / "nltk_data"
nltk.data.path.insert(0, str(NLTK_DIR))
warnings.filterwarnings("ignore", message="NLTK will not authorize")


@lru_cache(None)
def stopwords():
    try:
        words = nltk.corpus.stopwords.words("english")
    except LookupError:
        nltk.download("stopwords", download_dir=str(NLTK_DIR), quiet=True)
        words = nltk.corpus.stopwords.words("english")
    return frozenset(words)


@lru_cache(None)
def dictionary():
    """Lower-case English words (entries NLTK lists in lower case, i.e. not proper nouns)."""
    try:
        words = nltk.corpus.words.words()
    except LookupError:
        nltk.download("words", download_dir=str(NLTK_DIR), quiet=True)
        words = nltk.corpus.words.words()
    return frozenset(w for w in words if w.islower())


def in_dictionary(word):
    """True for a dictionary word or a regular inflection of one."""
    d = dictionary()
    word = word.replace("'s", "")
    if word in d:
        return True
    for suffix, repl in (("ies", "y"), ("es", ""), ("s", ""), ("ing", ""), ("ing", "e"),
                         ("ed", ""), ("ed", "e"), ("d", ""), ("ly", ""), ("er", ""), ("ers", "")):
        if word.endswith(suffix) and word[:len(word) - len(suffix)] + repl in d:
            return True
    return False
