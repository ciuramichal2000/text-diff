import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import difflib
import random

import pytest

from textdiff import (
    PatchMismatchError,
    apply_patch,
    parse_patch,
    split_lines,
    unified_diff,
)

# Lines are drawn from a small pool so that old and new texts share many of
# them; several entries imitate diff syntax to catch parsers that trust shapes.
LINE_POOL = [
    "",
    "alpha",
    "beta",
    "gamma",
    " indented",
    "-dash",
    "+plus",
    "@@ -1 +1 @@",
    "--- not a header",
    "+++ not a header",
    "\\ No newline at end of file",
    "tab\there",
    "trailing space ",
    "zażółć gęślą jaźń",
    "x",
]


def lcs_length(a, b):
    previous = [0] * (len(b) + 1)
    for item in a:
        current = [0]
        for j, other in enumerate(b, start=1):
            current.append(previous[j - 1] + 1 if item == other else max(previous[j], current[j - 1]))
        previous = current
    return previous[-1]


def render(rng, contents, eol, final_newline=None):
    """Join line contents into text; the last line may lack its terminator."""
    text = eol.join(contents)
    if final_newline is None:
        final_newline = rng.random() < 0.8
    if contents and final_newline:
        text += eol
    return text


def mutated(rng, contents):
    result = []
    for line in contents:
        roll = rng.random()
        if roll < 0.15:
            continue
        result.append(rng.choice(LINE_POOL) if roll < 0.30 else line)
        if rng.random() < 0.10:
            result.append(rng.choice(LINE_POOL))
    return result


def random_pair(rng, final_newline=None):
    """An old and a new text, usually related, with random line endings."""
    old_contents = [rng.choice(LINE_POOL) for _ in range(rng.randint(0, 12))]
    if rng.random() < 0.3:
        new_contents = [rng.choice(LINE_POOL) for _ in range(rng.randint(0, 12))]
    else:
        new_contents = mutated(rng, old_contents)
    old_eol = rng.choice(["\n", "\n", "\r\n"])
    new_eol = old_eol if rng.random() < 0.9 else rng.choice(["\n", "\r\n"])
    return (
        render(rng, old_contents, old_eol, final_newline),
        render(rng, new_contents, new_eol, final_newline),
    )


def test_applying_the_diff_to_the_old_text_gives_the_new_text():
    rng = random.Random(1234)
    for _ in range(600):
        old, new = random_pair(rng)
        context = rng.randint(0, 5)
        patch = unified_diff(old, new, context=context)
        assert apply_patch(old, patch) == new, (old, new, context, patch)


def test_diffing_a_text_with_itself_is_empty_and_applies_as_a_no_op():
    rng = random.Random(8)
    for _ in range(100):
        old, _ = random_pair(rng)
        patch = unified_diff(old, old)
        assert patch == ""
        assert apply_patch(old, patch) == old


def test_diff_is_minimal_and_its_header_ranges_describe_both_texts():
    rng = random.Random(31337)
    for _ in range(400):
        old, new = random_pair(rng)
        old_lines, new_lines = split_lines(old), split_lines(new)
        patch = parse_patch(unified_diff(old, new, context=rng.randint(0, 4)))

        removed = sum(1 for hunk in patch.hunks for line in hunk.lines if line.kind == "-")
        added = sum(1 for hunk in patch.hunks for line in hunk.lines if line.kind == "+")
        common = lcs_length(old_lines, new_lines)
        assert removed == len(old_lines) - common, (old, new)
        assert added == len(new_lines) - common, (old, new)

        # Each side of every header must point at exactly the lines the body shows.
        for hunk in patch.hunks:
            old_at, new_at = hunk.old_index, hunk.new_index
            assert old_lines[old_at : old_at + hunk.old_count] == hunk.old_lines
            assert new_lines[new_at : new_at + hunk.new_count] == hunk.new_lines


def test_patches_written_by_difflib_apply_with_this_implementation():
    # difflib is an independent generator of unified diffs (it cannot express a
    # missing final newline, so every text here ends with one).
    rng = random.Random(555)
    for _ in range(300):
        old, new = random_pair(rng, final_newline=True)
        context = rng.randint(0, 4)
        foreign = "".join(difflib.unified_diff(split_lines(old), split_lines(new), "a", "b", n=context))
        assert apply_patch(old, foreign) == new, (old, new, context, foreign)


def test_changing_any_line_a_hunk_relies_on_is_detected_at_that_line():
    rng = random.Random(77)
    checked = 0
    for _ in range(300):
        old, new = random_pair(rng)
        patch_text = unified_diff(old, new, context=rng.randint(0, 3))
        hunks = parse_patch(patch_text).hunks
        # A pure insertion without context has no old lines to damage.
        candidates = [(number, hunk) for number, hunk in enumerate(hunks, start=1) if hunk.old_lines]
        if not candidates:
            continue
        number, hunk = rng.choice(candidates)
        position = hunk.old_index + rng.randrange(len(hunk.old_lines))
        damaged = split_lines(old)
        line = damaged[position]
        body, terminator = (line[:-1], "\n") if line.endswith("\n") else (line, "")
        damaged[position] = body + "#" + terminator  # same line count, different text
        with pytest.raises(PatchMismatchError) as caught:
            apply_patch("".join(damaged), patch_text)
        assert (caught.value.hunk, caught.value.line) == (number, position + 1)
        checked += 1
    # Guard against the loop silently skipping everything.
    assert checked > 100


def test_lone_carriage_return_form_feed_and_unicode_separator_do_not_split_lines():
    # str.splitlines would cut at the CR, FF and U+2028 below, turning four
    # lines into seven and making the hunk header "-1,7 +1,7".
    old = "a\rb\nx\x0cy\nkeep here\nlast\r\n"
    new = "a\rB\nx\x0cy\nkeep here\nlast2\r\n"
    patch = unified_diff(old, new)
    assert patch == (
        "--- a\n+++ b\n"
        "@@ -1,4 +1,4 @@\n"
        "-a\rb\n"
        "+a\rB\n"
        " x\x0cy\n"
        " keep here\n"
        "-last\r\n"
        "+last2\r\n"
    )
    assert apply_patch(old, patch) == new
