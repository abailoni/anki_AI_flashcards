import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dutch_cards.parse_dict import parse_all, write_csvs

RAW_DIR = Path("data/raw")
WORDS_PATH = Path("data/words.csv")
EXAMPLES_PATH = Path("data/examples.csv")


def main() -> None:
    words, examples = parse_all(RAW_DIR)
    write_csvs(words, examples, WORDS_PATH, EXAMPLES_PATH)
    print(f"Parsed {len(words)} words, {len(examples)} examples -> {WORDS_PATH}, {EXAMPLES_PATH}")


if __name__ == "__main__":
    main()
