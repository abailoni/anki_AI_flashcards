from dutch_cards.cards import build_cloze_field, find_cloze_span
from dutch_cards.data import clean_example_text
from dutch_cards.nlp import check_coverage
from dutch_cards.parse_dict import normalize_gender, parse_entries, parse_header


def test_clean_letter_label():
    assert clean_example_text("a) Ik vind het leuk om voor hem te koken.") == \
        ["Ik vind het leuk om voor hem te koken."]


def test_clean_two_sentence_numeric_labels():
    assert clean_example_text("1) Het kind was ziek. 2) Het is niet anders.") == \
        ["Het kind was ziek.", "Het is niet anders."]


def test_clean_paren_label():
    assert clean_example_text("(adv) Het klonk als een beslissing waarover lang was nagedacht.") == \
        ["Het klonk als een beslissing waarover lang was nagedacht."]


def test_clean_colon_label():
    assert clean_example_text("af en toe: Af en toe zit ik te klappertanden van de kou.") == \
        ["Af en toe zit ik te klappertanden van de kou."]
    assert clean_example_text("een vraag stellen: Hij hield niet op met vragen stellen.") == \
        ["Hij hield niet op met vragen stellen."]


def test_clean_no_label_unchanged():
    assert clean_example_text("Ik kom uit Amsterdam.") == ["Ik kom uit Amsterdam."]


def test_clean_colon_false_positive_guard():
    # a real sentence with a colon shouldn't be mistaken for a label
    text = "Hij zei: 'Kom morgen.'"
    assert clean_example_text(text) == [text]


def test_coverage_all_known_passes():
    known = {"ik", "komen", "uit", "amsterdam"}
    passed, offending = check_coverage("Ik kom uit Amsterdam.", known, "komen")
    assert passed
    assert offending == []


def test_coverage_target_is_only_allowed_exception():
    known = {"ik", "uit", "amsterdam"}
    passed, offending = check_coverage("Ik kom uit Amsterdam.", known, "komen")
    assert passed  # "komen" (target) is the sole offender, allowed


def test_coverage_real_offender_fails():
    known = {"ik", "komen", "amsterdam"}
    passed, offending = check_coverage("Ik kom snel uit Amsterdam.", known, "komen")
    assert not passed
    assert "snel" in offending


def test_coverage_function_words_always_pass():
    known = {"komen"}
    passed, offending = check_coverage("Ik kom uit Amsterdam.", known, "komen")
    # "amsterdam" is an unknown PROPN (content) -> should fail, but "uit"/"ik" (function) never blamed
    assert not passed
    assert "amsterdam" in offending
    assert "uit" not in offending and "ik" not in offending


def test_coverage_target_absent_but_sentence_covered_passes():
    known = {"ik", "gaan", "naar", "huis"}
    passed, offending = check_coverage("Ik ga naar huis.", known, "wandelen")
    assert passed
    assert offending == []


def test_find_cloze_span_normal():
    sentence = "Ik ga naar huis."
    span = find_cloze_span(sentence, "gaan")
    assert sentence[span[0]:span[1]] == "ga"


def test_find_cloze_span_capitalized_initial_verb():
    # exercises the lowercase-offset-reuse trick: "Gaat" fails to lemmatize
    # to "gaan" unless lowercased first, but the returned span must still
    # point at the original-case "Gaat"
    sentence = "Gaat hij naar huis?"
    span = find_cloze_span(sentence, "gaan")
    assert sentence[span[0]:span[1]] == "Gaat"


def test_find_cloze_span_target_absent():
    assert find_cloze_span("Ik ga naar huis.", "wandelen") is None


def test_build_cloze_field():
    sentence = "Ik ga naar huis."
    span = find_cloze_span(sentence, "gaan")
    result = build_cloze_field(sentence, span, "to go")
    assert result == "Ik {{c1::ga::to go}} naar huis."


def test_parse_entries_skips_sidebar_section():
    lines = [
        "1 de art the",
        "• De man is hier.",
        "99.92",
        "2 en conj and",
        "• Ik en jij.",
        "99.80",
        "1 Animals",
        "hond 7.70 dog",
        "vis 5.39 fish",
        "3 in prep in",
        "• Het is in de doos.",
        "99.79",
    ]
    entries = parse_entries(lines)
    ranks = [e.rank for e in entries]
    headers = [e.header for e in entries]
    assert ranks == [1, 2, 3]
    assert headers == ["de art the", "en conj and", "in prep in"]


def test_parse_entries_collects_examples_and_freq():
    lines = [
        "1 vertellen verb to tell",
        "• De juffrouw vertelde tijdens de les een verhaal.",
        "38.21",
    ]
    entries = parse_entries(lines)
    assert len(entries) == 1
    assert entries[0].example_lines == ["De juffrouw vertelde tijdens de les een verhaal."]
    assert entries[0].freq == 38.21


def test_parse_header_simple():
    result = parse_header("vertellen verb to tell")
    assert result == {
        "lemma": "vertellen", "variants": [], "pos": ["verb"],
        "gender": "", "gloss": ["to tell"], "sense_count": 1,
    }


def test_parse_header_simple_with_gender():
    result = parse_header("mens noun, de(m) human")
    assert result["lemma"] == "mens"
    assert result["pos"] == ["noun"]
    assert result["gender"] == "de"
    assert result["gloss"] == ["human"]


def test_parse_header_lettered():
    result = parse_header("voor prep a) for b) in front of")
    assert result["pos"] == ["prep"]
    assert result["gloss"] == ["for", "in front of"]
    assert result["sense_count"] == 2


def test_parse_header_lettered_with_gender():
    result = parse_header("punt noun, de(m) a) full stop b) item c) point")
    assert result["gender"] == "de"
    assert result["gloss"] == ["full stop", "item", "point"]
    assert result["sense_count"] == 3


def test_parse_header_numbered():
    result = parse_header("het, 't 1) art 2) pron 1) the 2) it")
    assert result["lemma"] == "het"
    assert result["variants"] == ["'t"]
    assert result["pos"] == ["article", "pron"]
    assert result["gloss"] == ["the", "it"]
    assert result["sense_count"] == 2


def test_parse_header_numbered_three_way_different_gender():
    result = parse_header("maat 1) noun, de 2) noun, de 3) noun, de(m) 1) size 2) rhythm 3) mate")
    assert result["lemma"] == "maat"
    assert result["pos"] == ["noun"]
    assert result["gender"] == "de"  # first sense's gender only
    assert result["gloss"] == ["size", "rhythm", "mate"]
    assert result["sense_count"] == 3


def test_headword_variant_split():
    result = parse_header("zij, ze pron a) she b) they")
    assert result["lemma"] == "zij"
    assert result["variants"] == ["ze"]


def test_normalize_gender():
    assert normalize_gender("de(m)") == "de"
    assert normalize_gender("de(f)") == "de"
    assert normalize_gender("de/het") == "de/het"
    assert normalize_gender("het/de") == "de/het"
    assert normalize_gender("pl") == ""
    assert normalize_gender("pi") == ""  # OCR typo for "pl"
    assert normalize_gender("de(m)lhet") == "de/het"  # OCR typo
