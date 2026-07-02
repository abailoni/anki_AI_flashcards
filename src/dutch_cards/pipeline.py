"""Retrieval-first sentence resolution + file-based LLM handoff."""

import json
from dataclasses import dataclass
from pathlib import Path

from dutch_cards.data import Example, Word, clean_example_text
from dutch_cards.nlp import check_coverage

HANDOFF_DIR = Path("handoff")
REQUEST_PATH = HANDOFF_DIR / "request.json"
RESPONSE_PATH = HANDOFF_DIR / "response.json"
STATE_PATH = HANDOFF_DIR / "state.json"
MAX_ROUNDS = 3


@dataclass
class Outcome:
    word_id: str
    lemma: str
    source: str  # "dictionary_example" | "llm_generated" | "failed"
    sentence: str | None
    status: str  # "pass" | "failed_exhausted"


def resolve_by_retrieval(
    words: list[Word], examples: list[Example], known: set[str]
) -> tuple[dict[str, Outcome], list[Word]]:
    by_word: dict[str, list[Example]] = {}
    for e in examples:
        by_word.setdefault(e.word_id, []).append(e)

    resolved: dict[str, Outcome] = {}
    pending: list[Word] = []
    for w in words:
        candidates = sorted(by_word.get(w.id, []), key=lambda e: e.example_order)
        sentence = None
        for c in candidates:
            for text in clean_example_text(c.text):
                passed, _ = check_coverage(text, known, w.lemma)
                if passed:
                    sentence = text
                    break
            if sentence:
                break
        if sentence:
            resolved[w.id] = Outcome(w.id, w.lemma, "dictionary_example", sentence, "pass")
        else:
            pending.append(w)
    return resolved, pending


def write_request(words: list[Word], known: set[str], feedback: dict[str, list[str]] | None = None) -> None:
    feedback = feedback or {}
    items = [
        {
            "word_id": w.id,
            "lemma": w.lemma,
            "pos": w.pos,
            "gloss": w.gloss,
            "gender": w.gender,
            **({"feedback": (
                f"Your previous sentence for '{w.lemma}' used lemma(s) "
                f"{', '.join(feedback[w.id])} which are out of band — retry avoiding them."
            )} if w.id in feedback else {}),
        }
        for w in words
    ]
    HANDOFF_DIR.mkdir(exist_ok=True)
    REQUEST_PATH.write_text(json.dumps({
        "instructions": (
            "For each item, write ONE natural, simple Dutch sentence using the target "
            "lemma. Keep other content words (nouns, verbs, adjectives, adverbs, numbers) "
            "within known_lemmas where possible; function words are unrestricted. If "
            "'feedback' is present, follow it. Write your answers to handoff/response.json "
            "as {\"items\": [{\"word_id\": ..., \"sentence_nl\": ...}]}."
        ),
        "known_lemmas": sorted(known),
        "items": items,
    }, indent=2, ensure_ascii=False), encoding="utf-8")


def read_response() -> dict[str, str]:
    data = json.loads(RESPONSE_PATH.read_text(encoding="utf-8"))
    if "items" not in data:
        raise ValueError("response.json missing 'items' key")
    result = {}
    for item in data["items"]:
        if "word_id" not in item or "sentence_nl" not in item:
            raise ValueError(f"response item missing word_id/sentence_nl: {item}")
        result[item["word_id"]] = item["sentence_nl"]
    return result


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"round": 0}


def save_state(state: dict) -> None:
    HANDOFF_DIR.mkdir(exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
