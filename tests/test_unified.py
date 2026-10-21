import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import difflib
import random

import pytest

from textdiff import split_lines, unified_diff

TEN = "".join(f"{word}\n" for word in "one two three four five six seven eight nine ten".split())


def numbered(count):
    return "".join(f"{i}\n" for i in range(1, count + 1))


def with_lines_replaced(text, replacements):
    """Return ``text`` with the given 1-based lines swapped for new, newline-terminated ones."""
    lines = split_lines(text)
    for number, new_line in replacements.items():
        lines[number - 1] = new_line
    return "".join(lines)


def hunk_headers(diff):
    return [line for line in diff.splitlines() if line.startswith("@@")]


def test_single_change_matches_hand_written_output():
    new = TEN.replace("five\n", "FIVE\n")
    expected = (
        "--- a\n"
        "+++ b\n"
        "@@ -2,7 +2,7 @@\n"
        " two\n"
        " three\n"
        " four\n"
        "-five\n"
        "+FIVE\n"
        " six\n"
        " seven\n"
        " eight\n"
    )
    assert unified_diff(TEN, new) == expected


def test_file_names_and_context_size_are_honoured():
    new = TEN.replace("five\n", "FIVE\n")
    expected = (
        "--- old.txt\n"
        "+++ new.txt\n"
        "@@ -4,3 +4,3 @@\n"
        " four\n"
        "-five\n"
        "+FIVE\n"
        " six\n"
    )
    assert unified_diff(TEN, new, "old.txt", "new.txt", context=1) == expected


def test_identical_texts_produce_no_output():
    assert unified_diff(TEN, TEN) == ""
    assert unified_diff("", "") == ""


@pytest.mark.parametrize(
    "old, new, context, expected_body",
    [
        # Creating a file: the old range is empty and starts "at line 0".
        ("", "a\nb\n", 3, "@@ -0,0 +1,2 @@\n+a\n+b\n"),
        # Emptying a file: the new range is empty.
        ("a\nb\n", "", 3, "@@ -1,2 +0,0 @@\n-a\n-b\n"),
        # One line on each side: the count of 1 is omitted, as GNU diff does.
        ("a\n", "b\n", 3, "@@ -1 +1 @@\n-a\n+b\n"),
        # Pure insertion with no context names the line it comes after.
        ("x\ny\n", "x\nnew\ny\n", 0, "@@ -1,0 +2 @@\n+new\n"),
        # Pure deletion with no context: the new side is empty after line 1.
        ("x\ny\nz\n", "x\nz\n", 0, "@@ -2 +1,0 @@\n-y\n"),
    ],
)
def test_hunk_header_forms(old, new, context, expected_body):
    assert unified_diff(old, new, context=context) == "--- a\n+++ b\n" + expected_body


def test_changes_exactly_twice_the_context_apart_share_a_hunk():
    # Lines 6..11 (six lines) lie between the changes at 5 and 12: 6 == 2 * 3.
    old = numbered(30)
    new = with_lines_replaced(old, {5: "five\n", 12: "twelve\n"})
    assert hunk_headers(unified_diff(old, new)) == ["@@ -2,14 +2,14 @@"]


def test_changes_more_than_twice_the_context_apart_get_separate_hunks():
    # Lines 6..12 (seven lines) lie between the changes at 5 and 13: 7 > 6.
    old = numbered(30)
    new = with_lines_replaced(old, {5: "five\n", 13: "thirteen\n"})
    assert hunk_headers(unified_diff(old, new)) == ["@@ -2,7 +2,7 @@", "@@ -10,7 +10,7 @@"]


def test_new_side_start_accounts_for_earlier_insertions():
    old = numbered(30)
    lines = split_lines(old)
    # Three lines go in after line 2, which pushes old line 20 down to new line 23.
    new_lines = lines[:2] + ["x\n", "y\n", "z\n"] + lines[2:]
    new_lines[22] = "twenty\n"
    diff = unified_diff(old, "".join(new_lines), context=1)
    # First hunk: old lines 2-3 (2 lines) become new lines 2-6 (2, x, y, z, 3).
    # Second hunk: old lines 19-21 sit at new lines 22-24 because of the 3 added lines.
    assert hunk_headers(diff) == ["@@ -2,2 +2,5 @@", "@@ -19,3 +22,3 @@"]


@pytest.mark.parametrize(
    "old, new, expected_body",
    [
        (
            "a\nb",
            "a\nb\n",
            "@@ -1,2 +1,2 @@\n a\n-b\n\\ No newline at end of file\n+b\n",
        ),
        (
            "a\nb",
            "a\nc",
            "@@ -1,2 +1,2 @@\n a\n-b\n\\ No newline at end of file\n+c\n\\ No newline at end of file\n",
        ),
        (
            "a\nb",
            "x\nb",
            "@@ -1,2 +1,2 @@\n-a\n+x\n b\n\\ No newline at end of file\n",
        ),
    ],
)
def test_missing_final_newline_is_flagged_with_the_gnu_marker(old, new, expected_body):
    assert unified_diff(old, new) == "--- a\n+++ b\n" + expected_body


def test_matches_difflib_on_changes_with_a_unique_alignment():
    # Every line is unique, so the longest common subsequence is unambiguous
    # and any correct diff must equal difflib's, hunk grouping and headers included.
    rng = random.Random(99)
    for _ in range(60):
        old_lines = [f"L{i}\n" for i in range(rng.randint(5, 40))]
        new_lines = []
        fresh = 0
        for line in old_lines:
            roll = rng.random()
            if roll < 0.10:
                continue  # deleted
            if roll < 0.20:
                new_lines.append(f"R{fresh}\n")  # replaced
                fresh += 1
                continue
            new_lines.append(line)
            if rng.random() < 0.08:
                new_lines.append(f"N{fresh}\n")  # inserted after
                fresh += 1
        for context in (0, 1, 3):
            expected = "".join(difflib.unified_diff(old_lines, new_lines, "a", "b", n=context))
            assert unified_diff("".join(old_lines), "".join(new_lines), context=context) == expected


@pytest.mark.parametrize("context", [-1, 2.5, "3", None])
def test_invalid_context_is_rejected(context):
    with pytest.raises(ValueError, match="context must be a non-negative integer"):
        unified_diff("a\n", "b\n", context=context)


def test_file_names_with_line_breaks_are_rejected():
    with pytest.raises(ValueError, match="line breaks"):
        unified_diff("a\n", "b\n", fromfile="evil\n+++ forged")
