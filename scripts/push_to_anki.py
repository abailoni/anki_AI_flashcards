"""Build cloze + listening notes from phase 1 output and push to a running Anki via AnkiConnect."""

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dutch_cards.cards import build_cloze_note, build_listening_note

ANKI_URL = "http://127.0.0.1:8765"
RESULTS_PATH = Path("reports/phase1_results.json")
TRANSLATIONS_PATH = Path("reports/translations.json")

CLOZE_MODEL = "Dutch Cloze"
LISTENING_MODEL = "Dutch Listening"
CLOZE_DECK = "Dutch::Cloze"
LISTENING_DECK = "Dutch::Listening"

CLOZE_BACK = (
    "{{cloze:Text}}<hr>{{English}}<br>{{Italian}}<br>{{Sentence}}<br>{{tts nl_NL:Sentence}}"
)
LISTENING_BACK = "{{Sentence}}<hr>{{English}}<br>{{Italian}}"


def invoke(action, **params):
    body = json.dumps({"action": action, "version": 6, "params": params}).encode("utf-8")
    with urllib.request.urlopen(urllib.request.Request(ANKI_URL, data=body)) as resp:
        result = json.loads(resp.read())
    if result.get("error"):
        raise RuntimeError(f"{action} failed: {result['error']}")
    return result["result"]


def ensure_model_and_deck() -> None:
    models = invoke("modelNames")
    if CLOZE_MODEL not in models:
        invoke(
            "createModel",
            modelName=CLOZE_MODEL,
            inOrderFields=["Text", "English", "Italian", "Sentence"],
            isCloze=True,
            cardTemplates=[{"Name": "Card 1", "Front": "{{cloze:Text}}", "Back": CLOZE_BACK}],
        )
    if LISTENING_MODEL not in models:
        invoke(
            "createModel",
            modelName=LISTENING_MODEL,
            inOrderFields=["Sentence", "English", "Italian"],
            isCloze=False,
            cardTemplates=[
                {"Name": "Card 1", "Front": "{{tts nl_NL:Sentence}}", "Back": LISTENING_BACK}
            ],
        )

    decks = invoke("deckNames")
    for deck in (CLOZE_DECK, LISTENING_DECK):
        if deck not in decks:
            invoke("createDeck", deck=deck)


def main() -> None:
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))["words"]
    translations = json.loads(TRANSLATIONS_PATH.read_text(encoding="utf-8"))

    cloze_notes, listening_notes, excluded = [], [], []
    seen_sentences = set()  # a few words landed on the same generated carrier
    # sentence; a listening card is per-sentence, so a second identical card
    # (same audio, same back) adds nothing -- keep only the first (ponytail)
    for w in results:
        tr = translations[w["word_id"]]
        if w["sentence_nl"] not in seen_sentences:
            seen_sentences.add(w["sentence_nl"])
            listening_notes.append(build_listening_note(w["sentence_nl"], tr["en"], tr["it"]))
        cloze_fields = build_cloze_note(w, w["sentence_nl"], tr["en"], tr["it"])
        if cloze_fields is None:
            excluded.append(w["lemma"])
        else:
            cloze_notes.append(cloze_fields)

    ensure_model_and_deck()

    cloze_payload = [
        {"deckName": CLOZE_DECK, "modelName": CLOZE_MODEL, "fields": f, "tags": ["dutch-core"]}
        for f in cloze_notes
    ]
    listening_payload = [
        {"deckName": LISTENING_DECK, "modelName": LISTENING_MODEL, "fields": f, "tags": ["dutch-core"]}
        for f in listening_notes
    ]

    can_add = invoke("canAddNotesWithErrorDetail", notes=cloze_payload + listening_payload)
    errors = [c for c in can_add if not c["canAdd"]]
    if errors:
        print(f"{len(errors)} note(s) have preflight issues (likely duplicates):")
        for e in errors[:10]:
            print(" -", e.get("error"))

    print(
        f"About to add {len(cloze_payload)} notes to '{CLOZE_DECK}' and "
        f"{len(listening_payload)} notes to '{LISTENING_DECK}' "
        f"({len(excluded)} words excluded from cloze deck, no span match: {excluded})."
    )
    if input("Proceed? [y/N] ").strip().lower() != "y":
        print("Aborted.")
        return

    added_cloze = invoke("addNotes", notes=cloze_payload)
    added_listening = invoke("addNotes", notes=listening_payload)
    print(
        f"Added {sum(1 for x in added_cloze if x is not None)}/{len(cloze_payload)} cloze notes, "
        f"{sum(1 for x in added_listening if x is not None)}/{len(listening_payload)} listening notes."
    )


if __name__ == "__main__":
    main()
