"""Parse the raw dictionary text files (data/raw/*_dict.txt) into words.csv/examples.csv."""

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from dutch_cards.data import clean_example_text

LISTS = ["core", "fiction", "general", "newspapers", "spoken", "web"]

POS_WORDS = {"adj", "adv", "art", "conj", "interj", "noun", "num", "prep", "pron", "verb"}
POS_RENAME = {"art": "article"}

_RANK_RE = re.compile(r"^(\d+)\s+(\S.*)$")
_FREQ_RE = re.compile(r"^\d+\.\d+$")
_NUM_MARKER_RE = re.compile(r"(?:^|\s)(\d+)\)\s*")
_LETTER_MARKER_RE = re.compile(r"(?:^|\s)([a-z])\)\s")
_POS_ONLY_RE = re.compile(
    r"^(?P<head>.*?)\s+(?P<pos>" + "|".join(POS_WORDS) + r")\b(?P<gender>,\s*[a-z()/]+)?$"
)
_POS_GLOSS_RE = re.compile(
    r"^(?P<head>.*?)\s+(?P<pos>" + "|".join(POS_WORDS) + r")\b"
    r"(?P<gender>,\s*[a-z()/]+)?\s+(?P<gloss>.*)$"
)
_POS_SEGMENT_RE = re.compile(r"^(?P<pos>\w+)(?:,\s*(?P<gender>[a-z()/]+))?$")
# ponytail: 1 real OCR glitch has a POS glued directly to the gloss with no
# space (e.g. "adjpleasant"). Only used as a last-resort retry when normal
# parsing fails outright, so it can't misfire on real headwords that happen
# to start with a POS-like substring (those already parse fine on try 1).
_POS_GLUED_RE = re.compile(r"\b(" + "|".join(POS_WORDS) + r")(?=[a-z])")


@dataclass(frozen=True)
class RawEntry:
    rank: int
    header: str
    example_lines: list[str]
    freq: float


def parse_entries(lines: list[str]) -> list[RawEntry]:
    """Rank-continuity sidebar skip: real entries have strictly sequential rank
    numbers; anything that breaks the sequence (topical sidebar sections,
    file titles) is junk to skip one line at a time until the sequence resumes."""
    entries, expected_rank, i = [], 1, 0
    n = len(lines)
    while i < n:
        m = _RANK_RE.match(lines[i])
        if not m or int(m.group(1)) != expected_rank:
            i += 1
            continue
        header = m.group(2)
        i += 1
        examples = []
        while i < n and not _FREQ_RE.match(lines[i]):
            if lines[i].startswith("•"):
                examples.append(lines[i][1:].strip())
            i += 1
        if i >= n:
            break  # truncated trailing entry with no freq line -- discard
        freq = float(lines[i])
        i += 1
        entries.append(RawEntry(expected_rank, header, examples, freq))
        expected_rank += 1
    return entries


def normalize_gender(raw: str | None) -> str:
    if not raw:
        return ""
    raw = raw.replace("de(m)lhet", "de(m)/het")  # OCR typo
    if raw in ("pl", "pi"):  # "pi" is an OCR typo for "pl"
        return ""
    raw = raw.replace("de(m)", "de").replace("de(f)", "de")
    if raw in ("de/het", "het/de"):
        return "de/het"
    return raw


def _rename_pos(pos: str) -> str:
    return POS_RENAME.get(pos, pos)


def _split_head(head: str) -> tuple[str, list[str]]:
    parts = [p.strip() for p in head.split(",") if p.strip()]
    return parts[0], parts[1:]


def parse_header(header: str) -> dict:
    """Returns {lemma, variants, pos: list[str], gender: str, gloss: list[str], sense_count: int}."""
    if _NUM_MARKER_RE.search(header):
        return _parse_numbered(header)
    if _LETTER_MARKER_RE.search(header):
        return _parse_lettered(header)
    return _parse_simple(header)


def _parse_simple(header: str) -> dict:
    m = _POS_GLOSS_RE.match(header)
    if not m:
        m = _POS_GLOSS_RE.match(_POS_GLUED_RE.sub(lambda mm: mm.group(1) + " ", header))
    if not m:
        return _parse_no_pos(header)  # a few abbreviation/phrase entries have no POS at all
    lemma, variants = _split_head(m.group("head"))
    gender = normalize_gender((m.group("gender") or "").lstrip(", ").strip())
    return {
        "lemma": lemma,
        "variants": variants,
        "pos": [_rename_pos(m.group("pos"))],
        "gender": gender,
        "gloss": [m.group("gloss").strip()],
        "sense_count": 1,
    }


def _parse_no_pos(header: str) -> dict:
    """Fallback for the handful of entries with no POS tag at all, e.g. "cc cc",
    "o.a. amongst other things", "alstublieft, alsjeblieft, a.u.b. please"."""
    segments = [s.strip() for s in header.split(",")]
    if len(segments) == 1:
        tokens = segments[0].split(None, 1)
        lemma, variants = tokens[0], []
        gloss = tokens[1] if len(tokens) > 1 else ""
    else:
        variants = segments[:-1]
        lemma = variants.pop(0)
        last_tokens = segments[-1].split(None, 1)
        variants.append(last_tokens[0])
        gloss = last_tokens[1] if len(last_tokens) > 1 else ""
    return {
        "lemma": lemma, "variants": variants, "pos": [], "gender": "",
        "gloss": [gloss], "sense_count": 1,
    }


def _parse_lettered(header: str) -> dict:
    marker = _LETTER_MARKER_RE.search(header)
    head_and_pos = header[: marker.start()].strip()
    gloss_block = header[marker.start():].strip()

    m = _POS_ONLY_RE.match(head_and_pos)
    lemma, variants = _split_head(m.group("head"))
    gender = normalize_gender((m.group("gender") or "").lstrip(", ").strip())

    glosses = [g.strip() for g in re.split(r"[a-z]\)\s*", gloss_block) if g.strip()]
    return {
        "lemma": lemma,
        "variants": variants,
        "pos": [_rename_pos(m.group("pos"))],
        "gender": gender,
        "gloss": glosses,
        "sense_count": len(glosses),
    }


def _parse_numbered(header: str) -> dict:
    matches = list(_NUM_MARKER_RE.finditer(header))
    head = header[: matches[0].start()].strip()
    lemma, variants = _split_head(head)

    segments = []
    for idx, mm in enumerate(matches):
        start = mm.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(header)
        segments.append((int(mm.group(1)), header[start:end].strip()))

    boundary, last = None, 0
    for i, (num, _text) in enumerate(segments):
        if num == 1 and last > 1:
            boundary = i
            break
        last = num
    pos_segments = segments[:boundary]
    gloss_segments = segments[boundary:]

    pos_list, gender, seen = [], "", set()
    for i, (_num, text) in enumerate(pos_segments):
        sm = _POS_SEGMENT_RE.match(text)
        pos_tok = _rename_pos(sm.group("pos"))
        if pos_tok not in seen:
            seen.add(pos_tok)
            pos_list.append(pos_tok)
        if i == 0:
            gender = normalize_gender(sm.group("gender"))

    glosses = [text for _num, text in gloss_segments]
    return {
        "lemma": lemma,
        "variants": variants,
        "pos": pos_list,
        "gender": gender,
        "gloss": glosses,
        "sense_count": len(glosses),
    }


def collect_examples(word_id: str, raw_lines: list[str]) -> list[tuple[str, int, str]]:
    order, out = 1, []
    for raw in raw_lines:
        for text in clean_example_text(raw):
            out.append((word_id, order, text))
            order += 1
    return out


def parse_file(path: Path, list_name: str) -> tuple[list[dict], list[tuple]]:
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    words, examples = [], []
    for entry in parse_entries(lines):
        word_id = f"{list_name}_{entry.rank:06d}"
        parsed = parse_header(entry.header)
        words.append({
            "id": word_id,
            "rank": entry.rank,
            "list": list_name,
            "lemma": parsed["lemma"],
            "variants": "|".join(parsed["variants"]),
            "pos": "|".join(parsed["pos"]),
            "gender": parsed["gender"],
            "sense_count": parsed["sense_count"],
            "gloss": "|".join(parsed["gloss"]),
            "freq": entry.freq,
        })
        examples.extend(collect_examples(word_id, entry.example_lines))
    return words, examples


def parse_all(raw_dir: Path) -> tuple[list[dict], list[tuple]]:
    words, examples = [], []
    for list_name in LISTS:
        w, e = parse_file(raw_dir / f"{list_name}_dict.txt", list_name)
        words.extend(w)
        examples.extend(e)
    return words, examples


def write_csvs(words: list[dict], examples: list[tuple], words_path: Path, examples_path: Path) -> None:
    with words_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "id", "rank", "list", "lemma", "variants", "pos", "gender", "sense_count", "gloss", "freq",
        ])
        writer.writeheader()
        writer.writerows(words)

    with examples_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "example_order", "example_nl"])
        writer.writerows(examples)
