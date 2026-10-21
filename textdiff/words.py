"""Word-level diff for a single changed line."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .core import DELETE, EQUAL, INSERT, diff_opcodes

# Whitespace runs, word runs and single punctuation marks are separate tokens,
# so "foo(bar)" -> "foo(baz)" reports only "bar" as changed instead of the
# whole parenthesised expression. Every character falls into exactly one
# alternative, which means the tokens always join back into the input.
_TOKEN = re.compile(r"\s+|\w+|[^\w\s]")


@dataclass(frozen=True)
class WordSegment:
    """A stretch of text that is unchanged (EQUAL), only in the old line (DELETE) or only in the new (INSERT)."""

    kind: str
    text: str


def tokenize(line: str) -> list[str]:
    """Split a line into whitespace runs, word runs and single punctuation marks."""
    return _TOKEN.findall(line)


def word_diff(old: str, new: str) -> list[WordSegment]:
    """Diff two versions of a line token by token.

    Joining the EQUAL and DELETE segments gives back ``old``; joining the EQUAL
    and INSERT segments gives back ``new``. Where a run of tokens was replaced,
    the DELETE segment comes first and the INSERT segment right after it.
    """
    old_tokens = tokenize(old)
    new_tokens = tokenize(new)
    segments: list[WordSegment] = []
    for op in diff_opcodes(old_tokens, new_tokens):
        if op.tag == EQUAL:
            segments.append(WordSegment(EQUAL, "".join(old_tokens[op.a_start : op.a_end])))
            continue
        if op.a_end > op.a_start:
            segments.append(WordSegment(DELETE, "".join(old_tokens[op.a_start : op.a_end])))
        if op.b_end > op.b_start:
            segments.append(WordSegment(INSERT, "".join(new_tokens[op.b_start : op.b_end])))
    return segments


def format_word_diff(segments: list[WordSegment]) -> str:
    """Render segments in wdiff style: ``[-removed-]`` and ``{+added+}``."""
    parts = []
    for segment in segments:
        if segment.kind == DELETE:
            parts.append(f"[-{segment.text}-]")
        elif segment.kind == INSERT:
            parts.append(f"{{+{segment.text}+}}")
        else:
            parts.append(segment.text)
    return "".join(parts)
