"""Unified diff output in the format produced by ``diff -u`` and understood by ``patch``."""

from __future__ import annotations

from collections.abc import Iterator

from .core import EQUAL, Opcode, diff_opcodes, split_lines

NO_NEWLINE_MARKER = "\\ No newline at end of file"


def unified_diff(
    old: str,
    new: str,
    fromfile: str = "a",
    tofile: str = "b",
    context: int = 3,
) -> str:
    """Return the unified diff turning ``old`` into ``new``, or "" if they are equal.

    Hunk headers follow GNU diff: ``@@ -start,count +start,count @@``, with the
    count left out when it is 1 and the start naming the preceding line when
    the range is empty. Changes separated by at most ``2 * context`` unchanged
    lines share a hunk, so the context of neighbouring hunks never overlaps.
    """
    if not isinstance(context, int) or context < 0:
        raise ValueError(f"context must be a non-negative integer, got {context!r}")
    for name in (fromfile, tofile):
        if "\n" in name or "\r" in name:
            raise ValueError(f"file names must not contain line breaks: {name!r}")

    old_lines = split_lines(old)
    new_lines = split_lines(new)
    changes = [op for op in diff_opcodes(old_lines, new_lines) if op.tag != EQUAL]
    if not changes:
        return ""

    parts = [f"--- {fromfile}\n", f"+++ {tofile}\n"]
    for group in _group_changes(changes, context):
        parts.append(_render_hunk(old_lines, new_lines, group, context))
    return "".join(parts)


def _group_changes(changes: list[Opcode], context: int) -> list[list[Opcode]]:
    """Cluster change blocks whose gap is small enough for their context to meet."""
    groups: list[list[Opcode]] = [[changes[0]]]
    for change in changes[1:]:
        gap = change.a_start - groups[-1][-1].a_end
        if gap <= 2 * context:
            groups[-1].append(change)
        else:
            groups.append([change])
    return groups


def _render_hunk(
    old_lines: list[str],
    new_lines: list[str],
    group: list[Opcode],
    context: int,
) -> str:
    first, last = group[0], group[-1]
    old_start = max(0, first.a_start - context)
    old_end = min(len(old_lines), last.a_end + context)
    # Everything between a hunk's edges and its changes is unchanged text, so
    # the new-side range is the old-side range shifted by the same overhang.
    new_start = first.b_start - (first.a_start - old_start)
    new_end = last.b_end + (old_end - last.a_end)

    body: list[str] = []
    position = old_start
    for change in group:
        body.extend(_prefixed(" ", old_lines[position : change.a_start]))
        body.extend(_prefixed("-", old_lines[change.a_start : change.a_end]))
        body.extend(_prefixed("+", new_lines[change.b_start : change.b_end]))
        position = change.a_end
    body.extend(_prefixed(" ", old_lines[position:old_end]))

    header = (
        f"@@ -{_format_range(old_start, old_end - old_start)}"
        f" +{_format_range(new_start, new_end - new_start)} @@\n"
    )
    return header + "".join(body)


def _format_range(start: int, count: int) -> str:
    """Format a zero-based ``start`` and ``count`` as unified diff's one-based range."""
    if count == 1:
        return str(start + 1)
    if count == 0:
        return f"{start},0"
    return f"{start + 1},{count}"


def _prefixed(prefix: str, lines: list[str]) -> Iterator[str]:
    """Prefix each line, flagging one that lacks its newline (only a file's last can)."""
    for line in lines:
        if line.endswith("\n"):
            yield prefix + line
        else:
            yield f"{prefix}{line}\n{NO_NEWLINE_MARKER}\n"
