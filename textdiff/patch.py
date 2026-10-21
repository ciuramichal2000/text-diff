"""Parsing and strict application of unified diffs."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from .core import split_lines

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class PatchError(ValueError):
    """Base class for everything that can go wrong while reading or applying a patch."""


class PatchFormatError(PatchError):
    """The patch text is malformed or internally inconsistent."""


class PatchMismatchError(PatchError):
    """A hunk's context or removed lines differ from the text being patched.

    ``hunk`` is the one-based hunk number and ``line`` the one-based line of
    the original where the disagreement was found.
    """

    def __init__(self, message: str, hunk: int, line: int) -> None:
        super().__init__(message)
        self.hunk = hunk
        self.line = line


@dataclass(frozen=True)
class HunkLine:
    """One body line of a hunk.

    ``kind`` is " " (context), "-" (removed) or "+" (added). ``text`` is the
    full line; it ends with a newline unless the patch marked it as missing.
    """

    kind: str
    text: str


@dataclass(frozen=True)
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: tuple[HunkLine, ...]

    @property
    def old_lines(self) -> list[str]:
        """Lines the original must contain here: context plus removed lines."""
        return [line.text for line in self.lines if line.kind != "+"]

    @property
    def new_lines(self) -> list[str]:
        """Lines that replace them: context plus added lines."""
        return [line.text for line in self.lines if line.kind != "-"]

    @property
    def old_index(self) -> int:
        """Zero-based index in the original where the old lines start.

        An empty range names the line the new text goes *after*, so its start
        already is the index at which to insert.
        """
        return self.old_start if self.old_count == 0 else self.old_start - 1

    @property
    def new_index(self) -> int:
        """Zero-based index in the patched text where the new lines start."""
        return self.new_start if self.new_count == 0 else self.new_start - 1


@dataclass(frozen=True)
class Patch:
    old_name: str
    new_name: str
    hunks: tuple[Hunk, ...]


def parse_patch(text: str) -> Patch:
    """Parse a single-file unified diff.

    Text before the ``---`` header (``diff --git``, ``index`` ...) is skipped.
    Hunk bodies are read by the counts in their headers rather than by
    looking for the next ``@@``, because a changed line may itself look like a
    header. Anything left over after the last hunk is rejected instead of
    ignored: a stray line usually means the header counts are wrong.
    """
    if not isinstance(text, str):
        raise TypeError(f"expected str, got {type(text).__name__}")
    if not text.strip():
        return Patch("", "", ())

    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()  # the empty piece after the final newline is not a line
    index = 0
    while index < len(lines) and not lines[index].startswith("--- "):
        index += 1
    if index == len(lines):
        raise PatchFormatError("no '--- ' file header found")
    if index + 1 == len(lines) or not lines[index + 1].startswith("+++ "):
        raise PatchFormatError(f"line {index + 2}: expected a '+++ ' header after the '--- ' header")
    old_name = _header_name(lines[index])
    new_name = _header_name(lines[index + 1])
    index += 2

    hunks: list[Hunk] = []
    while index < len(lines) and lines[index].startswith("@@"):
        hunk, index = _parse_hunk(lines, index)
        hunks.append(hunk)

    for position in range(index, len(lines)):
        stray = lines[position]
        if stray == "":
            continue
        if stray.startswith("--- "):
            raise PatchFormatError(f"line {position + 1}: patches touching several files are not supported")
        raise PatchFormatError(f"line {position + 1}: unexpected text after the last hunk: {stray!r}")
    return Patch(old_name, new_name, tuple(hunks))


def _header_name(line: str) -> str:
    """File name from a '--- ' or '+++ ' line, without a trailing timestamp."""
    return line[4:].split("\t")[0].strip()


def _parse_hunk(lines: list[str], start: int) -> tuple[Hunk, int]:
    """Parse the hunk whose header is ``lines[start]``; return it and the next index."""
    match = _HUNK_HEADER.match(lines[start])
    if match is None:
        raise PatchFormatError(f"line {start + 1}: malformed hunk header {lines[start]!r}")
    old_start = int(match.group(1))
    new_start = int(match.group(3))
    # A range written without a count (``-5``) means exactly one line.
    old_count = int(match.group(2)) if match.group(2) is not None else 1
    new_count = int(match.group(4)) if match.group(4) is not None else 1

    body: list[HunkLine] = []
    old_seen = new_seen = 0
    cursor = start + 1
    while True:
        if cursor < len(lines) and lines[cursor].startswith("\\"):
            _mark_missing_newline(body, cursor)
            cursor += 1
            continue
        if old_seen == old_count and new_seen == new_count:
            break
        if cursor == len(lines):
            raise PatchFormatError(
                f"hunk at line {start + 1} is truncated: its header promises {old_count} old and "
                f"{new_count} new lines but only {old_seen} and {new_seen} follow"
            )
        raw = lines[cursor]
        # Mailers often strip the trailing space of an empty context line.
        kind = raw[0] if raw else " "
        if kind not in " -+":
            raise PatchFormatError(f"line {cursor + 1}: not a valid hunk line: {raw!r}")
        if kind != "+":
            old_seen += 1
        if kind != "-":
            new_seen += 1
        if old_seen > old_count or new_seen > new_count:
            raise PatchFormatError(f"line {cursor + 1}: hunk at line {start + 1} has more lines than its header says")
        body.append(HunkLine(kind, raw[1:] + "\n"))
        cursor += 1
    return Hunk(old_start, old_count, new_start, new_count, tuple(body)), cursor


def _mark_missing_newline(body: list[HunkLine], cursor: int) -> None:
    """Apply a '\\ No newline at end of file' marker to the line before it."""
    if not body:
        raise PatchFormatError(f"line {cursor + 1}: 'No newline' marker before any hunk line")
    previous = body[-1]
    if not previous.text.endswith("\n"):
        raise PatchFormatError(f"line {cursor + 1}: two 'No newline' markers in a row")
    body[-1] = replace(previous, text=previous.text[:-1])


def apply_patch(original: str, patch: str) -> str:
    """Apply a unified diff to ``original`` and return the patched text.

    Every context and removed line is compared with the original at the
    position the hunk header names, newline-at-end-of-file included, and the
    first disagreement raises PatchMismatchError. There is deliberately no
    fuzz or offset search: a patch either describes exactly this text or it
    is refused, so a wrong base can never be patched silently.
    """
    parsed = parse_patch(patch)
    source = split_lines(original)
    result: list[str] = []
    cursor = 0
    for number, hunk in enumerate(parsed.hunks, start=1):
        start = hunk.old_index
        if start < 0:
            raise PatchFormatError(f"hunk {number}: its old range starts at line 0 but is not empty")
        if start < cursor:
            raise PatchFormatError(f"hunk {number} overlaps or comes before the previous hunk")
        if start > len(source):
            raise PatchMismatchError(
                f"hunk {number} starts after line {start} but the original ends at line {len(source)}",
                number,
                start,
            )
        expected = hunk.old_lines
        _verify_context(source, start, expected, number)
        result.extend(source[cursor:start])
        result.extend(hunk.new_lines)
        cursor = start + len(expected)
    result.extend(source[cursor:])

    if any(not line.endswith("\n") for line in result[:-1]):
        raise PatchFormatError("a line marked 'No newline at end of file' is followed by more text")
    return "".join(result)


def _verify_context(source: list[str], start: int, expected: list[str], number: int) -> None:
    for offset, wanted in enumerate(expected):
        line_number = start + offset + 1
        if line_number > len(source):
            raise PatchMismatchError(
                f"hunk {number} does not match at line {line_number}: the patch expects {wanted!r} "
                f"but the original ends at line {len(source)}",
                number,
                line_number,
            )
        found = source[line_number - 1]
        if found != wanted:
            raise PatchMismatchError(
                f"hunk {number} does not match at line {line_number}: the patch expects {wanted!r} "
                f"but the original has {found!r}",
                number,
                line_number,
            )
