"""Sequence diffing built on Myers' O(ND) shortest-edit-script algorithm.

Every other module (unified diffs, word diffs) consumes the opcodes produced
here, so this is the only place that searches for a minimal set of edits.
"""

from __future__ import annotations

from array import array
from collections.abc import Hashable, Sequence
from dataclasses import dataclass

EQUAL = "equal"
DELETE = "delete"
INSERT = "insert"
REPLACE = "replace"


@dataclass(frozen=True)
class Opcode:
    """One run of an edit script: ``a[a_start:a_end]`` becomes ``b[b_start:b_end]``."""

    tag: str
    a_start: int
    a_end: int
    b_start: int
    b_end: int


def split_lines(text: str) -> list[str]:
    """Split text into lines that keep their terminators.

    Only a newline character ends a line. ``str.splitlines`` would also break
    on form feeds, Unicode separators and lone carriage returns, so a
    diff/patch round trip would silently rewrite files that merely contain
    those characters. A last line without a terminator is kept as it is, which
    makes a missing newline at the end of a file visible to the diff.
    """
    if not isinstance(text, str):
        raise TypeError(f"expected str, got {type(text).__name__}")
    pieces = text.split("\n")
    lines = [piece + "\n" for piece in pieces[:-1]]
    if pieces[-1]:
        lines.append(pieces[-1])
    return lines


def diff_opcodes(a: Sequence[Hashable], b: Sequence[Hashable]) -> list[Opcode]:
    """Return a minimal edit script turning ``a`` into ``b``.

    The script is a list of opcodes that tile both sequences from start to end.
    Equal runs and changed runs alternate; a changed run is a DELETE (only
    ``a`` items), an INSERT (only ``b`` items) or a REPLACE (both). Keeping
    each changed run as one block means deletions always precede insertions in
    the rendered output, whatever order the search found them in.

    Items only need to support ``==`` and hashing. Memory use grows with the
    square of the number of edits (about 4 bytes per cell), so two long
    sequences that share a few items but are otherwise unrelated are costly.
    """
    prefix = _common_prefix(a, b)
    suffix = _common_suffix(a, b, prefix)
    middle = _edit_steps(a[prefix : len(a) - suffix], b[prefix : len(b) - suffix])
    return _group_steps(["="] * prefix + middle + ["="] * suffix)


def _common_prefix(a: Sequence[Hashable], b: Sequence[Hashable]) -> int:
    length = 0
    limit = min(len(a), len(b))
    while length < limit and a[length] == b[length]:
        length += 1
    return length


def _common_suffix(a: Sequence[Hashable], b: Sequence[Hashable], prefix: int) -> int:
    length = 0
    limit = min(len(a), len(b)) - prefix
    while length < limit and a[-1 - length] == b[-1 - length]:
        length += 1
    return length


def _edit_steps(a: Sequence[Hashable], b: Sequence[Hashable]) -> list[str]:
    """Steps ('=', '-', '+') for the part of the input left after trimming.

    The trivial shapes are answered directly: running the quadratic-memory
    search on, say, a file that was emptied or completely rewritten would cost
    far more than the answer is worth.
    """
    if not a:
        return ["+"] * len(b)
    if not b:
        return ["-"] * len(a)
    if set(a).isdisjoint(b):
        return ["-"] * len(a) + ["+"] * len(b)
    return _myers(a, b)


def _furthest(previous: array, d: int, k: int) -> int:
    """Furthest x on diagonal ``k`` after ``d - 1`` edits.

    ``previous`` holds that round's results, one entry per diagonal of the
    right parity, ordered from -(d-1) upwards. Round 0 reads from a sentinel
    row containing a single 0, which stands for "nothing consumed yet".
    """
    return previous[(k + d - 1) // 2]


def _prefers_insert(previous: array, d: int, k: int) -> bool:
    """True when the best path into diagonal ``k`` comes from diagonal ``k + 1``."""
    if k == -d:
        return True
    if k == d:
        return False
    return _furthest(previous, d, k - 1) < _furthest(previous, d, k + 1)


def _myers(a: Sequence[Hashable], b: Sequence[Hashable]) -> list[str]:
    """Greedy forward search; keeps every round so the path can be walked back."""
    n, m = len(a), len(b)
    rows = [array("i", [0])]
    d = 0
    while True:
        previous = rows[d]
        row = array("i")
        for k in range(-d, d + 1, 2):
            if _prefers_insert(previous, d, k):
                x = _furthest(previous, d, k + 1)
            else:
                x = _furthest(previous, d, k - 1) + 1
            y = x - k
            while x < n and y < m and a[x] == b[y]:
                x += 1
                y += 1
            if x >= n and y >= m:
                return _walk_back(rows, n, m, d)
            row.append(x)
        rows.append(row)
        d += 1


def _walk_back(rows: list[array], n: int, m: int, last_round: int) -> list[str]:
    """Recover the step sequence by undoing the search from (n, m) to (0, 0)."""
    steps: list[str] = []
    x, y = n, m
    for d in range(last_round, -1, -1):
        previous = rows[d]
        k = x - y
        came_from_insert = _prefers_insert(previous, d, k)
        previous_k = k + 1 if came_from_insert else k - 1
        previous_x = _furthest(previous, d, previous_k)
        previous_y = previous_x - previous_k
        while x > previous_x and y > previous_y:
            steps.append("=")
            x -= 1
            y -= 1
        if d > 0:
            steps.append("+" if came_from_insert else "-")
        x, y = previous_x, previous_y
    steps.reverse()
    return steps


def _group_steps(steps: list[str]) -> list[Opcode]:
    """Collapse per-item steps into runs; a run of edits becomes one opcode."""
    opcodes: list[Opcode] = []
    i = j = 0
    position = 0
    while position < len(steps):
        if steps[position] == "=":
            start = position
            while position < len(steps) and steps[position] == "=":
                position += 1
            length = position - start
            opcodes.append(Opcode(EQUAL, i, i + length, j, j + length))
            i += length
            j += length
            continue
        deleted = inserted = 0
        while position < len(steps) and steps[position] != "=":
            if steps[position] == "-":
                deleted += 1
            else:
                inserted += 1
            position += 1
        if not inserted:
            tag = DELETE
        elif not deleted:
            tag = INSERT
        else:
            tag = REPLACE
        opcodes.append(Opcode(tag, i, i + deleted, j, j + inserted))
        i += deleted
        j += inserted
    return opcodes
