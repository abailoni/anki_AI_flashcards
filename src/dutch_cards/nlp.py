"""spaCy lemmatization + coverage checking."""

from functools import lru_cache

import spacy

POS_BUCKET = {
    "NOUN": "content", "PROPN": "content", "VERB": "content", "AUX": "content",
    "ADJ": "content", "ADV": "content", "NUM": "content", "INTJ": "content",
    "ADP": "function", "CCONJ": "function", "SCONJ": "function",
    "PRON": "function", "DET": "function", "PART": "function",
    "PUNCT": "ignore", "SYM": "ignore", "SPACE": "ignore", "X": "ignore",
}


@lru_cache(maxsize=1)
def _nlp():
    return spacy.load("nl_core_news_sm")


def check_coverage(text: str, known_lemmas: set[str], target_lemma: str) -> tuple[bool, list[str]]:
    """Content-word lemmas must be in known_lemmas, except target_lemma itself."""
    target = target_lemma.lower()
    offending = []
    # lowercase first: nl_core_news_sm fails to lemmatize sentence-initial
    # capitalized verbs (e.g. "Gaat" stays "Gaat" instead of "gaan")
    for tok in _nlp()(text.lower()):
        bucket = POS_BUCKET.get(tok.pos_, "ignore")
        if bucket != "content":
            continue
        # some tokens keep a stray trailing period glued to the lemma (e.g. "hand.")
        lemma = tok.lemma_.lower().strip(".,!?;:")
        if lemma and lemma != target and lemma not in known_lemmas:
            offending.append(lemma)
    return (not offending, offending)
