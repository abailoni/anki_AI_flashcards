from dutch_cards.data import clean_example_text
from dutch_cards.nlp import check_coverage


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
