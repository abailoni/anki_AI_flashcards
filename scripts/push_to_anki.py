"""Build cloze + listening notes from phase 1 output and push to a running Anki via AnkiConnect.

Usage: push_to_anki.py [--decks cloze|listening|both] [--rebuild]
"""

import base64
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dutch_cards.audio import _cache_path, voice_for
from dutch_cards.cards import build_cloze_note, build_listening_note, dedupe_by_sentence

ANKI_URL = "http://127.0.0.1:8765"
RESULTS_PATH = Path("reports/phase1_results.json")
TRANSLATIONS_PATH = Path("reports/translations.json")

CLOZE_MODEL = "Dutch Cloze"
LISTENING_MODEL = "Dutch Listening"
CLOZE_DECK = "Dutch::Cloze"
LISTENING_DECK = "Dutch::Listening"

CLOZE_BACK = "{{cloze:Text}}<hr>{{English}}<br>{{Italian}}<br>{{Sentence}}<br>{{Audio}}"
LISTENING_BACK = "{{Sentence}}<hr>{{English}}<br>{{Italian}}"


def invoke(action, **params):
    body = json.dumps({"action": action, "version": 6, "params": params}).encode("utf-8")
    with urllib.request.urlopen(urllib.request.Request(ANKI_URL, data=body)) as resp:
        result = json.loads(resp.read())
    if result.get("error"):
        raise RuntimeError(f"{action} failed: {result['error']}")
    return result["result"]


def ensure_model_and_deck(decks: str) -> None:
    models = invoke("modelNames")
    if CLOZE_MODEL not in models:
        invoke(
            "createModel",
            modelName=CLOZE_MODEL,
            inOrderFields=["Text", "English", "Italian", "Sentence", "Audio"],
            isCloze=True,
            cardTemplates=[{"Name": "Card 1", "Front": "{{cloze:Text}}", "Back": CLOZE_BACK}],
        )
    if decks != "cloze" and LISTENING_MODEL not in models:
        invoke(
            "createModel",
            modelName=LISTENING_MODEL,
            inOrderFields=["Sentence", "English", "Italian", "Audio"],
            isCloze=False,
            cardTemplates=[{"Name": "Card 1", "Front": "{{Audio}}", "Back": LISTENING_BACK}],
        )

    deck_names = invoke("deckNames")
    wanted = [CLOZE_DECK] if decks == "cloze" else [CLOZE_DECK, LISTENING_DECK]
    for deck in wanted:
        if deck not in deck_names:
            invoke("createDeck", deck=deck)


def store_audio(sentence_nl: str, voice_index: int) -> str:
    """Upload the cached mp3 for this sentence to Anki media, return the [sound:...] tag."""
    voice = voice_for(voice_index)
    path = _cache_path(sentence_nl, voice)
    filename = f"nl_{path.stem}.mp3"
    invoke("storeMediaFile", filename=filename, data=base64.b64encode(path.read_bytes()).decode())
    return f"[sound:{filename}]"


def main() -> None:
    decks = "both"
    rebuild = False
    for arg in sys.argv[1:]:
        if arg == "--decks":
            continue
        if arg in ("cloze", "listening", "both"):
            decks = arg
        elif arg == "--rebuild":
            rebuild = True

    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))["words"]
    translations = json.loads(TRANSLATIONS_PATH.read_text(encoding="utf-8"))
    unique_sentences = dedupe_by_sentence(results)
    voice_index_by_sentence = {w["sentence_nl"]: i for i, w in enumerate(unique_sentences)}

    cloze_notes, listening_notes, excluded = [], [], []
    seen_sentences = set()
    for w in results:
        tr = translations[w["word_id"]]
        voice_idx = voice_index_by_sentence[w["sentence_nl"]]
        audio_path = _cache_path(w["sentence_nl"], voice_for(voice_idx))
        has_audio = audio_path.exists()

        if decks != "cloze" and w["sentence_nl"] not in seen_sentences:
            seen_sentences.add(w["sentence_nl"])
            note = build_listening_note(w["sentence_nl"], tr["en"], tr["it"])
            note["Audio"] = store_audio(w["sentence_nl"], voice_idx) if has_audio else ""
            listening_notes.append(note)

        cloze_fields = build_cloze_note(w, w["sentence_nl"], tr["en"], tr["it"])
        if cloze_fields is None:
            excluded.append(w["lemma"])
        else:
            cloze_fields["Audio"] = store_audio(w["sentence_nl"], voice_idx) if has_audio else ""
            cloze_notes.append({"word_id": w["word_id"], "fields": cloze_fields})

    if rebuild:
        existing = invoke("findNotes", query="tag:dutch-core")
        print(f"--rebuild: will delete {len(existing)} existing notes first.")
        if input("Proceed with delete? [y/N] ").strip().lower() != "y":
            print("Aborted.")
            return
        if existing:
            invoke("deleteNotes", notes=existing)

    ensure_model_and_deck(decks)

    cloze_payload = [
        {
            "deckName": CLOZE_DECK,
            "modelName": CLOZE_MODEL,
            "fields": c["fields"],
            "tags": ["dutch-core", f"id:{c['word_id']}"],
        }
        for c in cloze_notes
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
        f"About to add {len(cloze_payload)} notes to '{CLOZE_DECK}'"
        + (f" and {len(listening_payload)} notes to '{LISTENING_DECK}'" if decks != "cloze" else "")
        + f" ({len(excluded)} words excluded from cloze deck, no span match: {excluded})."
    )
    if input("Proceed? [y/N] ").strip().lower() != "y":
        print("Aborted.")
        return

    added_cloze = invoke("addNotes", notes=cloze_payload)
    print(f"Added {sum(1 for x in added_cloze if x is not None)}/{len(cloze_payload)} cloze notes.")
    if decks != "cloze":
        added_listening = invoke("addNotes", notes=listening_payload)
        print(
            f"Added {sum(1 for x in added_listening if x is not None)}/{len(listening_payload)} "
            f"listening notes."
        )


if __name__ == "__main__":
    main()
