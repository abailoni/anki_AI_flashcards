"""Generate ElevenLabs audio for resolved sentences. Usage: generate_audio.py [N]
With N given, only processes the first N words (by rank) -- for testing."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dutch_cards.audio import MAX_CHARS_PER_RUN, _cache_path, synthesize, voice_for
from dutch_cards.cards import dedupe_by_sentence

RESULTS_PATH = Path("reports/phase1_results.json")


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))["words"]
    if limit:
        results = results[:limit]
    unique = dedupe_by_sentence(results)

    chars_used, generated, cached = 0, 0, 0
    for i, w in enumerate(unique):
        text = w["sentence_nl"]
        voice = voice_for(i)
        if _cache_path(text, voice).exists():
            cached += 1
            continue
        if chars_used + len(text) > MAX_CHARS_PER_RUN:
            print(f"Stopping: next sentence would exceed {MAX_CHARS_PER_RUN}-char budget "
                  f"({chars_used} used so far).")
            break
        synthesize(text, voice)
        chars_used += len(text)
        generated += 1

    print(f"{generated} new, {cached} already cached, {chars_used} characters used this run.")


if __name__ == "__main__":
    main()
