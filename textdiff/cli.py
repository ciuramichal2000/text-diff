"""Command line interface: ``python -m textdiff diff|patch|words``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import TextIO

from .core import EQUAL
from .patch import apply_patch
from .unified import unified_diff
from .words import format_word_diff, word_diff


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="textdiff",
        description="Unified diff, strict patch and word-level diff. "
        "Exit status: 0 = no differences (or patch applied), 1 = differences found, 2 = error.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    diff = commands.add_parser("diff", help="print a unified diff of two files")
    diff.add_argument("old", help="original file")
    diff.add_argument("new", help="changed file")
    diff.add_argument(
        "-U", "--context", type=int, default=3, metavar="N", help="lines of context around each change (default: 3)"
    )

    patch = commands.add_parser("patch", help="apply a unified diff to a file; the file itself is never modified")
    patch.add_argument("file", help="file to patch")
    patch.add_argument("patch_file", help="unified diff to apply")
    patch.add_argument("-o", "--output", metavar="PATH", help="write the result here instead of to standard output")

    words = commands.add_parser("words", help="word-level diff of two lines of text")
    words.add_argument("old", help="original line")
    words.add_argument("new", help="changed line")
    return parser


def _read(path: str) -> str:
    """Read a UTF-8 file without newline translation, so CRLF files survive intact."""
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            return handle.read()
    except UnicodeDecodeError as error:
        raise ValueError(f"{path}: not valid UTF-8 text ({error.reason})") from error


def main(
    argv: Sequence[str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the CLI and return its exit status; the streams can be injected for tests."""
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "diff":
            text = unified_diff(_read(args.old), _read(args.new), args.old, args.new, args.context)
            out.write(text)
            return 1 if text else 0
        if args.command == "patch":
            result = apply_patch(_read(args.file), _read(args.patch_file))
            if args.output is None:
                out.write(result)
            else:
                with open(args.output, "w", encoding="utf-8", newline="") as handle:
                    handle.write(result)
            return 0
        segments = word_diff(args.old, args.new)
        out.write(format_word_diff(segments) + "\n")
        return 1 if any(segment.kind != EQUAL for segment in segments) else 0
    except (OSError, ValueError) as error:
        err.write(f"textdiff: {error}\n")
        return 2
