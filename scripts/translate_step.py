"""Re-run after handoff/translate_response.json is written."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dutch_cards.translate import (
    TRANSLATE_REQUEST_PATH,
    TRANSLATE_RESPONSE_PATH,
    TRANSLATIONS_PATH,
    read_translate_response,
    write_translate_request,
)


def main() -> None:
    if TRANSLATE_RESPONSE_PATH.exists():
        translations = read_translate_response()
        TRANSLATIONS_PATH.parent.mkdir(exist_ok=True)
        TRANSLATIONS_PATH.write_text(
            json.dumps(translations, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Wrote {len(translations)} translations to {TRANSLATIONS_PATH}")
    else:
        write_translate_request()
        print(
            f"Wrote {TRANSLATE_REQUEST_PATH}.\n"
            f"Hand it to Claude Code, ask it to write {TRANSLATE_RESPONSE_PATH}, "
            f"then re-run this script."
        )


if __name__ == "__main__":
    main()
