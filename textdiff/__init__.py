"""textdiff: a from-scratch text diff and patch library with a small CLI."""

from .core import DELETE, EQUAL, INSERT, REPLACE, Opcode, diff_opcodes, split_lines
from .patch import (
    Hunk,
    HunkLine,
    Patch,
    PatchError,
    PatchFormatError,
    PatchMismatchError,
    apply_patch,
    parse_patch,
)
from .unified import unified_diff
from .words import WordSegment, format_word_diff, tokenize, word_diff

__all__ = [
    "DELETE",
    "EQUAL",
    "INSERT",
    "REPLACE",
    "Hunk",
    "HunkLine",
    "Opcode",
    "Patch",
    "PatchError",
    "PatchFormatError",
    "PatchMismatchError",
    "WordSegment",
    "apply_patch",
    "diff_opcodes",
    "format_word_diff",
    "parse_patch",
    "split_lines",
    "tokenize",
    "unified_diff",
    "word_diff",
]
