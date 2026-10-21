import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from textdiff import PatchError, PatchFormatError, PatchMismatchError, apply_patch, parse_patch

COLORS = "red\ngreen\nblue\nyellow\n"

COLORS_PATCH = (
    "--- a/colors\n"
    "+++ b/colors\n"
    "@@ -1,4 +1,4 @@\n"
    " red\n"
    "-green\n"
    "+GREEN\n"
    " blue\n"
    " yellow\n"
)


def test_applies_a_hand_written_patch():
    assert apply_patch(COLORS, COLORS_PATCH) == "red\nGREEN\nblue\nyellow\n"


def test_applies_several_hunks_and_ignores_git_preamble():
    original = "".join(f"{i}\n" for i in range(1, 21))
    patch = (
        "diff --git a/n b/n\n"
        "index 83db48f..bf2a3c1 100644\n"
        "--- a/n\n"
        "+++ b/n\n"
        "@@ -1,3 +1,4 @@ heading text after the range is allowed\n"
        " 1\n"
        "+one and a half\n"
        " 2\n"
        " 3\n"
        "@@ -18,3 +19,2 @@\n"
        " 18\n"
        "-19\n"
        " 20\n"
    )
    lines = [f"{i}\n" for i in range(1, 21)]
    expected = "".join(lines[:1] + ["one and a half\n"] + lines[1:18] + lines[19:])
    assert apply_patch(original, patch) == expected


def test_empty_patch_leaves_the_text_unchanged():
    assert apply_patch(COLORS, "") == COLORS
    assert apply_patch(COLORS, "--- a\n+++ b\n") == COLORS


def test_parse_patch_exposes_names_ranges_and_line_kinds():
    patch = parse_patch(
        "--- old.txt\t2020-01-01 10:00:00\n"
        "+++ new.txt\t2020-01-02 10:00:00\n"
        "@@ -3 +3,2 @@\n"
        "-gone\n"
        "+one\n"
        "+two\n"
    )
    assert (patch.old_name, patch.new_name) == ("old.txt", "new.txt")
    (hunk,) = patch.hunks
    # A range written without a count means exactly one line.
    assert (hunk.old_start, hunk.old_count, hunk.new_start, hunk.new_count) == (3, 1, 3, 2)
    assert [line.kind for line in hunk.lines] == ["-", "+", "+"]
    assert hunk.old_lines == ["gone\n"]
    assert hunk.new_lines == ["one\n", "two\n"]


def test_context_mismatch_names_the_hunk_line_and_both_texts():
    original = "red\ngreen\nORANGE\nyellow\n"
    with pytest.raises(PatchMismatchError) as caught:
        apply_patch(original, COLORS_PATCH)
    error = caught.value
    assert (error.hunk, error.line) == (1, 3)
    assert "line 3" in str(error)
    assert "'blue\\n'" in str(error) and "'ORANGE\\n'" in str(error)


def test_removed_line_that_differs_is_a_mismatch_too():
    with pytest.raises(PatchMismatchError) as caught:
        apply_patch("red\nGreen\nblue\nyellow\n", COLORS_PATCH)
    assert caught.value.line == 2


def test_original_shorter_than_the_hunk_reports_where_it_ends():
    with pytest.raises(PatchMismatchError, match="original ends at line 2") as caught:
        apply_patch("red\ngreen\n", COLORS_PATCH)
    assert caught.value.line == 3


def test_failure_in_a_later_hunk_reports_that_hunk_number():
    original = "".join(f"{i}\n" for i in range(1, 21))
    patch = (
        "--- a\n+++ b\n"
        "@@ -1 +1 @@\n-1\n+one\n"
        "@@ -10 +10 @@\n-WRONG\n+ten\n"
    )
    with pytest.raises(PatchMismatchError) as caught:
        apply_patch(original, patch)
    assert (caught.value.hunk, caught.value.line) == (2, 10)


def test_insertion_after_the_end_of_a_short_file_is_a_mismatch():
    with pytest.raises(PatchMismatchError, match="starts after line 5 but the original ends at line 1") as caught:
        apply_patch("a\n", "--- a\n+++ b\n@@ -5,0 +6 @@\n+late\n")
    assert caught.value.hunk == 1


@pytest.mark.parametrize(
    "patch, message",
    [
        ("just some text\n", "no '--- ' file header"),
        ("--- a\n@@ -1 +1 @@\n-x\n+y\n", "expected a '\\+\\+\\+ ' header"),
        ("--- a\n+++ b\n@@ -1 +1\n-x\n+y\n", "malformed hunk header"),
        ("--- a\n+++ b\n@@ -1,3 +1,3 @@\n a\n-b\n", "truncated"),
        ("--- a\n+++ b\n@@ -1 +1 @@\n-x\n-y\n+z\n", "more lines than its header"),
        ("--- a\n+++ b\n@@ -1 +1 @@\n?x\n+y\n", "not a valid hunk line"),
        ("--- a\n+++ b\n@@ -1 +1 @@\n-x\n+y\nstray\n", "unexpected text after the last hunk"),
        (
            "--- a\n+++ b\n@@ -1 +1 @@\n-x\n+y\n--- c\n+++ d\n@@ -1 +1 @@\n-p\n+q\n",
            "several files are not supported",
        ),
        ("--- a\n+++ b\n@@ -1 +1 @@\n\\ No newline at end of file\n-x\n+y\n", "before any hunk line"),
        (
            "--- a\n+++ b\n@@ -1 +1 @@\n-x\n\\ No newline at end of file\n\\ No newline at end of file\n+y\n",
            "two 'No newline' markers",
        ),
    ],
)
def test_malformed_patches_are_rejected_with_a_specific_message(patch, message):
    with pytest.raises(PatchFormatError, match=message):
        parse_patch(patch)


def test_hunks_out_of_order_or_overlapping_are_rejected():
    patch = "--- a\n+++ b\n@@ -3 +3 @@\n-c\n+C\n@@ -1 +1 @@\n-a\n+A\n"
    with pytest.raises(PatchFormatError, match="hunk 2 overlaps or comes before"):
        apply_patch("a\nb\nc\n", patch)


def test_old_range_starting_at_line_zero_with_lines_is_rejected():
    with pytest.raises(PatchFormatError, match="starts at line 0"):
        apply_patch("a\n", "--- a\n+++ b\n@@ -0,1 +1 @@\n-a\n+b\n")


def test_patch_errors_share_a_common_base_that_is_a_value_error():
    assert issubclass(PatchFormatError, PatchError)
    assert issubclass(PatchMismatchError, PatchError)
    assert issubclass(PatchError, ValueError)


def test_final_newline_is_part_of_the_context_that_gets_verified():
    patch = (
        "--- a\n+++ b\n"
        "@@ -1,2 +1,2 @@\n"
        " a\n"
        "-b\n"
        "\\ No newline at end of file\n"
        "+b\n"
    )
    assert apply_patch("a\nb", patch) == "a\nb\n"
    # The same patch must refuse a file that does end with a newline.
    with pytest.raises(PatchMismatchError) as caught:
        apply_patch("a\nb\n", patch)
    assert caught.value.line == 2


def test_patch_can_remove_the_final_newline():
    patch = (
        "--- a\n+++ b\n"
        "@@ -1,2 +1,2 @@\n"
        " a\n"
        "-b\n"
        "+b\n"
        "\\ No newline at end of file\n"
    )
    assert apply_patch("a\nb\n", patch) == "a\nb"


def test_missing_newline_marker_in_the_middle_of_the_result_is_rejected():
    patch = "--- a\n+++ b\n@@ -1 +1 @@\n-a\n+x\n\\ No newline at end of file\n"
    with pytest.raises(PatchFormatError, match="followed by more text"):
        apply_patch("a\nb\n", patch)


def test_lines_that_look_like_diff_syntax_are_read_by_count_not_by_shape():
    original = (
        "keep\n"
        "-- sql comment\n"
        "+++ not a header\n"
        "@@ -1 +1 @@\n"
        "\\ No newline at end of file\n"
        "end\n"
    )
    # Body lines below start with "--- ", "+++ ", "@@" and a backslash on purpose:
    #   "--- sql comment"   deletes the line "-- sql comment"
    #   "-+++ not a header" deletes the line "+++ not a header"
    #   "+++ forged"        adds the line "++ forged"
    #   " @@ -1 +1 @@"      keeps the line "@@ -1 +1 @@"
    #   " \ No newline ..." keeps a line whose text is a marker (the leading space makes it context)
    patch = (
        "--- a\n+++ b\n"
        "@@ -1,6 +1,5 @@\n"
        " keep\n"
        "--- sql comment\n"
        "-+++ not a header\n"
        "+++ forged\n"
        " @@ -1 +1 @@\n"
        " \\ No newline at end of file\n"
        " end\n"
    )
    parsed = parse_patch(patch)
    assert [line.kind for line in parsed.hunks[0].lines] == [" ", "-", "-", "+", " ", " ", " "]
    assert parsed.hunks[0].old_lines == [
        "keep\n",
        "-- sql comment\n",
        "+++ not a header\n",
        "@@ -1 +1 @@\n",
        "\\ No newline at end of file\n",
        "end\n",
    ]
    assert apply_patch(original, patch) == (
        "keep\n++ forged\n@@ -1 +1 @@\n\\ No newline at end of file\nend\n"
    )
