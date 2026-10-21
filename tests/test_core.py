import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import random

import pytest

from textdiff import DELETE, EQUAL, INSERT, REPLACE, Opcode, core, diff_opcodes, split_lines


def lcs_length(a, b):
    """Textbook dynamic-programming LCS, used as an oracle independent of Myers."""
    previous = [0] * (len(b) + 1)
    for item in a:
        current = [0]
        for j, other in enumerate(b, start=1):
            if item == other:
                current.append(previous[j - 1] + 1)
            else:
                current.append(max(previous[j], current[j - 1]))
        previous = current
    return previous[-1]


def equal_total(opcodes):
    return sum(op.a_end - op.a_start for op in opcodes if op.tag == EQUAL)


def assert_well_formed(a, b, opcodes):
    """The opcodes must tile both sequences and their tags must match their ranges."""
    a_pos = b_pos = 0
    for op in opcodes:
        assert (op.a_start, op.b_start) == (a_pos, b_pos)
        a_len, b_len = op.a_end - op.a_start, op.b_end - op.b_start
        if op.tag == EQUAL:
            assert a_len == b_len > 0
            assert a[op.a_start : op.a_end] == b[op.b_start : op.b_end]
        elif op.tag == DELETE:
            assert a_len > 0 and b_len == 0
        elif op.tag == INSERT:
            assert a_len == 0 and b_len > 0
        else:
            assert op.tag == REPLACE and a_len > 0 and b_len > 0
        a_pos, b_pos = op.a_end, op.b_end
    assert (a_pos, b_pos) == (len(a), len(b))
    for first, second in zip(opcodes, opcodes[1:]):
        # Equal runs and change runs strictly alternate.
        assert (first.tag == EQUAL) != (second.tag == EQUAL)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("", []),
        ("a", ["a"]),
        ("a\n", ["a\n"]),
        ("a\n\nb", ["a\n", "\n", "b"]),
        ("a\r\nb\r\n", ["a\r\n", "b\r\n"]),
        # Only "\n" ends a line: form feed, U+2028 and a lone CR stay inside the line.
        ("x\x0cy z\rw\n", ["x\x0cy z\rw\n"]),
    ],
)
def test_split_lines_breaks_only_on_newline_and_keeps_terminators(text, expected):
    assert split_lines(text) == expected
    assert "".join(split_lines(text)) == text


def test_split_lines_rejects_bytes_with_a_clear_error():
    with pytest.raises(TypeError, match="expected str, got bytes"):
        split_lines(b"abc\n")


def test_classic_myers_paper_example_has_lcs_four_and_five_edits():
    # ABCABBA -> CBABAC from the Myers paper: shortest edit script has 5 edits,
    # so the longest common subsequence has (7 + 6 - 5) / 2 = 4 items.
    a, b = list("ABCABBA"), list("CBABAC")
    opcodes = diff_opcodes(a, b)
    assert_well_formed(a, b, opcodes)
    assert equal_total(opcodes) == 4
    deleted = sum(op.a_end - op.a_start for op in opcodes if op.tag != EQUAL)
    inserted = sum(op.b_end - op.b_start for op in opcodes if op.tag != EQUAL)
    assert (deleted, inserted) == (3, 2)


def test_simple_scripts_have_the_expected_tags_and_ranges():
    assert diff_opcodes([], []) == []
    assert diff_opcodes(["a", "b"], ["a", "b"]) == [Opcode(EQUAL, 0, 2, 0, 2)]
    assert diff_opcodes([], ["x", "y"]) == [Opcode(INSERT, 0, 0, 0, 2)]
    assert diff_opcodes(["x", "y"], []) == [Opcode(DELETE, 0, 2, 0, 0)]
    assert diff_opcodes(["a", "b", "c"], ["a", "X", "c"]) == [
        Opcode(EQUAL, 0, 1, 0, 1),
        Opcode(REPLACE, 1, 2, 1, 2),
        Opcode(EQUAL, 2, 3, 2, 3),
    ]
    assert diff_opcodes(["a", "b", "c", "d"], ["a", "d"]) == [
        Opcode(EQUAL, 0, 1, 0, 1),
        Opcode(DELETE, 1, 3, 1, 1),
        Opcode(EQUAL, 3, 4, 1, 2),
    ]


def test_random_pairs_give_minimal_well_formed_scripts():
    rng = random.Random(20240601)
    for _ in range(400):
        # A three-letter alphabet makes duplicates, and so ties, very common.
        a = rng.choices("abc", k=rng.randint(0, 12))
        b = rng.choices("abc", k=rng.randint(0, 12))
        opcodes = diff_opcodes(a, b)
        assert_well_formed(a, b, opcodes)
        assert equal_total(opcodes) == lcs_length(a, b), (a, b)


def test_trivial_shapes_never_reach_the_quadratic_memory_search(monkeypatch):
    # Emptied, filled-from-nothing and completely rewritten inputs have an
    # obvious answer; running the O(D^2)-memory search on them would need
    # hundreds of millions of cells for inputs of this size.
    def forbidden(a, b):
        raise AssertionError("the Myers search must not run for this input")

    monkeypatch.setattr(core, "_myers", forbidden)
    a = list(range(5000))
    b = list(range(5000, 12000))
    assert diff_opcodes(a, b) == [Opcode(REPLACE, 0, 5000, 0, 7000)]
    assert diff_opcodes(a, []) == [Opcode(DELETE, 0, 5000, 0, 0)]
    assert diff_opcodes([], b) == [Opcode(INSERT, 0, 0, 0, 7000)]
    # Shared head and tail are trimmed first, leaving only the disjoint middle.
    assert diff_opcodes([0] + a + [1], [0] + b + [1]) == [
        Opcode(EQUAL, 0, 1, 0, 1),
        Opcode(REPLACE, 1, 5001, 1, 7001),
        Opcode(EQUAL, 5001, 5002, 7001, 7002),
    ]


def test_large_inputs_with_few_edits_are_diffed_exactly():
    a = [f"line {i}" for i in range(20000)]
    b = list(a)
    b[10] = "changed"  # one replacement
    del b[5000]  # one deletion
    b.insert(15000, "added")  # one insertion
    opcodes = diff_opcodes(a, b)
    assert_well_formed(a, b, opcodes)
    # Edits: line 10 (1 delete + 1 insert), line 5000 (1 delete), one added line.
    assert equal_total(opcodes) == 20000 - 2
    assert sum(1 for op in opcodes if op.tag != EQUAL) == 3
