"""Cloze span-finding + Anki note field assembly for both deck types."""

from dutch_cards.nlp import _nlp

# ponytail: separable verbs (op/aan/uit/... + stem, spread across two spans,
# both meant to share the same {{c1::}} number per the user's request) are
# out of scope — zero exist in the current 177-word core fixture (all 41 verb
# lemmas are simple stems). Add multi-span-same-c1 clozing once the full
# dictionary (opbellen/aankomen/...) is processed.


def _normalize(lemma: str) -> str:
    # dictionary source uses a curly apostrophe (zo'n); generated/typed text
    # commonly uses a straight one -- treat them as the same lemma
    return lemma.lower().replace("’", "'")


def find_cloze_span(sentence: str, target_lemma: str) -> tuple[int, int] | None:
    """First surface span in `sentence` whose spaCy lemma matches target_lemma."""
    target = _normalize(target_lemma)
    # lemmatize a lowercased copy (same fix as nlp.check_coverage), but token
    # offsets/lengths are stable across .lower() for Dutch, so they still
    # index correctly into the original-case `sentence` for the cloze reveal.
    for tok in _nlp()(sentence.lower()):
        lemma = _normalize(tok.lemma_.strip(".,!?;:"))
        if lemma == target:
            return (tok.idx, tok.idx + len(tok.text))
    return None  # target absent; coverage check already allows this to pass


def build_cloze_field(sentence: str, span: tuple[int, int], gloss_hint: str) -> str:
    start, end = span
    return f"{sentence[:start]}{{{{c1::{sentence[start:end]}::{gloss_hint}}}}}{sentence[end:]}"


def build_cloze_note(word: dict, sentence_nl: str, en: str, it: str) -> dict | None:
    span = find_cloze_span(sentence_nl, word["lemma"])
    if span is None:
        return None
    hint = word["gloss"][0]  # ponytail: first sense only, multi-sense disambiguation deferred
    return {
        "Text": build_cloze_field(sentence_nl, span, hint),
        "English": en,
        "Italian": it,
        "Sentence": sentence_nl,
    }


def build_listening_note(sentence_nl: str, en: str, it: str) -> dict:
    return {"Sentence": sentence_nl, "English": en, "Italian": it}
