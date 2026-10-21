import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import random

import pytest

from textdiff import DELETE, EQUAL, INSERT, WordSegment, format_word_diff, tokenize, word_diff


def as_pairs(segments):
    return [(segment.kind, segment.text) for segment in segments]


@pytest.mark.parametrize(
    "line, tokens",
    [
        ("", []),
        ("a  b,c", ["a", "  ", "b", ",", "c"]),
        ("foo(bar)", ["foo", "(", "bar", ")"]),
        ("zażółć gęślą", ["zażółć", " ", "gęślą"]),
        ("tab\tand nbsp", ["tab", "\t", "and", " ", "nbsp"]),
    ],
)
def test_tokenize_separates_words_whitespace_and_punctuation(line, tokens):
    assert tokenize(line) == tokens
    assert "".join(tokens) == line


def test_replaced_word_is_reported_as_delete_then_insert():
    segments = word_diff("the quick brown fox", "the slow brown fox")
    assert as_pairs(segments) == [
        (EQUAL, "the "),
        (DELETE, "quick"),
        (INSERT, "slow"),
        (EQUAL, " brown fox"),
    ]
    assert format_word_diff(segments) == "the [-quick-]{+slow+} brown fox"


def test_appended_and_removed_words_take_their_separating_space_along():
    assert as_pairs(word_diff("a b", "a b c")) == [(EQUAL, "a b"), (INSERT, " c")]
    assert as_pairs(word_diff("a b c", "a c")) == [(EQUAL, "a "), (DELETE, "b "), (EQUAL, "c")]


def test_punctuation_changes_do_not_swallow_neighbouring_words():
    segments = word_diff("foo(bar)", "foo(baz)")
    assert as_pairs(segments) == [(EQUAL, "foo("), (DELETE, "bar"), (INSERT, "baz"), (EQUAL, ")")]


def test_whitespace_only_change_is_still_a_change():
    assert as_pairs(word_diff("a  b", "a b")) == [
        (EQUAL, "a"),
        (DELETE, "  "),
        (INSERT, " "),
        (EQUAL, "b"),
    ]


def test_degenerate_inputs():
    assert word_diff("", "") == []
    assert as_pairs(word_diff("same line", "same line")) == [(EQUAL, "same line")]
    assert as_pairs(word_diff("", "new")) == [(INSERT, "new")]
    assert as_pairs(word_diff("old", "")) == [(DELETE, "old")]


def test_reordered_words_cost_a_minimal_number_of_moves():
    # "one two three" -> "three one two": the shortest script moves only "three".
    segments = word_diff("one two three", "three one two")
    assert as_pairs(segments) == [
        (INSERT, "three "),
        (EQUAL, "one two"),
        (DELETE, " three"),
    ]


def test_segments_always_reassemble_both_input_lines():
    rng = random.Random(5)
    vocabulary = ["alpha", " ", "  ", "beta", ",", "(", ")", "x1", "gamma", "-", "\t"]
    for _ in range(300):
        old = "".join(rng.choices(vocabulary, k=rng.randint(0, 10)))
        new = "".join(rng.choices(vocabulary, k=rng.randint(0, 10)))
        segments = word_diff(old, new)
        assert "".join(s.text for s in segments if s.kind != INSERT) == old
        assert "".join(s.text for s in segments if s.kind != DELETE) == new
        assert all(segment.text for segment in segments)


def test_format_word_diff_renders_each_kind_and_leaves_braces_in_text_alone():
    segments = [
        WordSegment(EQUAL, "if {x} "),
        WordSegment(DELETE, "a"),
        WordSegment(INSERT, "b"),
    ]
    assert format_word_diff(segments) == "if {x} [-a-]{+b+}"
    assert format_word_diff([]) == ""
