# textdiff

A text diff and patch tool written from scratch with only the Python standard library. It computes a minimal line diff with Myers' algorithm, prints it as a unified diff, applies such a diff back to the original text while checking every context line, and can show the word-level changes inside a single line. It comes with a small command line interface.

## Interesting engineering

- **Myers' O(ND) shortest-edit-script search.** Common head and tail are trimmed first, and empty or completely different inputs are answered directly. The search itself keeps one table per round of edits so it can walk the path back, which costs memory proportional to the square of the edit count. The tests compare the result with a textbook dynamic-programming LCS on 400 seeded random pairs, so a script that is valid but not minimal fails.
- **GNU-style unified diff.** Hunk headers follow `diff -u` (`@@ -a,b +c,d @@`, the count omitted when it is 1, `N,0` for an empty range), changes whose gap is at most twice the context size share a hunk, and a missing final newline is written as `\ No newline at end of file`. On inputs with an unambiguous alignment the output is compared with `difflib.unified_diff`, and patches written by `difflib` are applied with this implementation.
- **Strict patching.** `apply_patch` compares every context and removed line, including the final newline, with the original and raises `PatchMismatchError` carrying the hunk number and line. There is no fuzz and no offset search, so a patch made for a different base is refused rather than applied in the wrong place. Hunk bodies are read by the counts in their headers, so a changed line that happens to look like `@@ ...` or `--- ...` is not mistaken for diff syntax.
- **Byte-exact line handling.** Text is split on `\n` only and lines keep their terminators, so CRLF files, lone carriage returns and form feeds survive a diff and patch round trip unchanged.
- **Property-style tests with fixed seeds.** 600 random old/new text pairs (random line endings, missing final newlines, lines imitating diff syntax) satisfy `apply_patch(old, unified_diff(old, new)) == new`. A second test damages one line a hunk relies on and checks that the error names that exact hunk and line.

## Usage

Library:

```python
from textdiff import unified_diff, apply_patch, word_diff, format_word_diff, PatchMismatchError

old = "red\ngreen\nblue\nyellow\n"
new = "red\nGREEN\nblue\nyellow\nviolet\n"

patch = unified_diff(old, new, "colors.old", "colors.new", context=1)
print(patch, end="")
# --- colors.old
# +++ colors.new
# @@ -1,4 +1,5 @@
#  red
# -green
# +GREEN
#  blue
#  yellow
# +violet

assert apply_patch(old, patch) == new

try:
    apply_patch("red\ngreen\nORANGE\nyellow\n", patch)
except PatchMismatchError as error:
    print(error)  # hunk 1 does not match at line 3: the patch expects 'blue\n' but the original has 'ORANGE\n'

print(format_word_diff(word_diff("the quick brown fox", "the slow brown fox")))
# the [-quick-]{+slow+} brown fox
```

Command line:

```
python -m textdiff diff old.txt new.txt > change.diff
python -m textdiff patch old.txt change.diff -o patched.txt
python -m textdiff words "the quick brown fox" "the slow brown fox"
```

`diff -U N` sets the number of context lines (default 3). `patch` never modifies its input file; without `-o` the result goes to standard output. Exit status: 0 for no differences (or a patch that applied), 1 when differences were found, 2 for an error such as a missing file, a file that is not UTF-8, or a patch that does not match.

## Running the tests

```
python -m pytest -q
```

Only `pytest` is needed besides the standard library. The suite is deterministic: random data comes from seeded generators, and there is no network access, sleeping or dependence on the current date.

## Limitations

- A patch may describe one file only; a patch that touches several files is rejected.
- Patching is exact. Line endings are part of the compared text, so a patch whose line endings were converted (for example LF to CRLF) is refused for a file that was not converted too. The new-side start numbers in hunk headers are read but not checked; the old-side start, the line counts and the old-side text are.
- The edit search keeps one table per round of edits, so two long inputs that share a few lines but are otherwise unrelated need memory proportional to the square of their edit count.
- The CLI reads files as UTF-8 and reports anything else as an error. Word diffs compare one pair of lines you pass in; the unified diff does not pair up changed lines to show word changes inside them.

Built with AI coding assistance.
