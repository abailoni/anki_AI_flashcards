"""Load words/examples fixtures and clean example-sentence text."""

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Word:
    id: str
    rank: int
    lemma: str
    variants: list[str]
    pos: list[str]
    gender: str | None
    gloss: list[str]
    freq: float


@dataclass(frozen=True)
class Example:
    word_id: str
    example_order: int
    text: str


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split("|") if v.strip()]


def load_words(path: Path) -> list[Word]:
    with path.open(encoding="utf-8") as f:
        return [
            Word(
                id=row["id"],
                rank=int(row["rank"]),
                lemma=row["lemma"],
                variants=_split(row["variants"]),
                pos=_split(row["pos"]),
                gender=row["gender"] or None,
                gloss=_split(row["gloss"]),
                freq=float(row["freq"]),
            )
            for row in csv.DictReader(f)
        ]


def load_examples(path: Path) -> list[Example]:
    with path.open(encoding="utf-8") as f:
        return [
            Example(word_id=row["id"], example_order=int(row["example_order"]), text=row["example_nl"])
            for row in csv.DictReader(f)
        ]


# Label artifacts observed in examples_partial.csv: "a) ...", "1) ... 2) ...",
# "(adv) ...", "af en toe: ...". Only strip these concrete, observed patterns.
_LEADING_LETTER_LABEL = re.compile(r"^[a-z]\)\s*")
_LEADING_NUM_LABEL = re.compile(r"^\d+\)\s*")
_LEADING_PAREN_LABEL = re.compile(r"^\([a-z]+\)\s*")
_LEADING_COLON_LABEL = re.compile(r"^([\wà-ú' ]{1,30}):\s*")
_MID_NUM_LABEL = re.compile(r"\s\d+\)\s*")


def clean_example_text(raw: str) -> list[str]:
    """Strip label prefixes; split rows that bundle multiple numbered sentences."""
    text = raw
    for pattern in (_LEADING_LETTER_LABEL, _LEADING_NUM_LABEL, _LEADING_PAREN_LABEL):
        text = pattern.sub("", text, count=1)

    m = _LEADING_COLON_LABEL.match(text)
    label = m.group(1) if m else ""
    # real sentences start with a capital letter; dictionary collocation labels don't
    if m and label[:1].islower() and not any(c in label for c in ".!?"):
        text = text[m.end():]

    parts = [p.strip() for p in _MID_NUM_LABEL.split(text) if p.strip()]
    return parts or [text.strip()]


def known_set(words: list[Word]) -> set[str]:
    lemmas = set()
    for w in words:
        lemmas.add(w.lemma.lower())
        lemmas.update(v.lower() for v in w.variants)
    return lemmas
