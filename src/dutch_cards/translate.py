"""One-shot EN+IT translation handoff (no repair loop, unlike pipeline.py's
generation handoff — a translation has no coverage check to fail against)."""

import json
from pathlib import Path

from dutch_cards.report import RESULTS_PATH

HANDOFF_DIR = Path("handoff")
TRANSLATE_REQUEST_PATH = HANDOFF_DIR / "translate_request.json"
TRANSLATE_RESPONSE_PATH = HANDOFF_DIR / "translate_response.json"
TRANSLATIONS_PATH = Path("reports/translations.json")


def write_translate_request() -> None:
    data = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    items = [{"word_id": r["word_id"], "sentence_nl": r["sentence_nl"]} for r in data["words"]]
    HANDOFF_DIR.mkdir(exist_ok=True)
    TRANSLATE_REQUEST_PATH.write_text(json.dumps({
        "instructions": (
            "For each item, translate sentence_nl into natural English and natural "
            "Italian. Write handoff/translate_response.json as "
            '{"items": [{"word_id": ..., "en": ..., "it": ...}]}.'
        ),
        "items": items,
    }, indent=2, ensure_ascii=False), encoding="utf-8")


def read_translate_response() -> dict[str, dict[str, str]]:
    data = json.loads(TRANSLATE_RESPONSE_PATH.read_text(encoding="utf-8"))
    return {item["word_id"]: {"en": item["en"], "it": item["it"]} for item in data["items"]}
