import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import io
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from textdiff.cli import main

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORK_ROOT = Path(__file__).resolve().parent / "_work"


@pytest.fixture
def workdir():
    """A scratch directory inside the project that is removed after each test."""
    WORK_ROOT.mkdir(exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="cli_", dir=WORK_ROOT))
    yield path
    shutil.rmtree(path, ignore_errors=True)
    try:
        WORK_ROOT.rmdir()  # only succeeds once no test directory is left
    except OSError:
        pass


def write_bytes(path, data):
    path.write_bytes(data)
    return str(path)


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    status = main(list(argv), stdout=out, stderr=err)
    return status, out.getvalue(), err.getvalue()


def test_diff_prints_a_unified_diff_and_exits_1_when_files_differ(workdir):
    old = write_bytes(workdir / "old.txt", b"one\ntwo\nthree\n")
    new = write_bytes(workdir / "new.txt", b"one\n2\nthree\n")
    status, out, err = run("diff", old, new)
    assert status == 1
    assert err == ""
    assert out == f"--- {old}\n+++ {new}\n@@ -1,3 +1,3 @@\n one\n-two\n+2\n three\n"


def test_diff_exits_0_with_no_output_for_identical_files(workdir):
    first = write_bytes(workdir / "a.txt", b"same\n")
    second = write_bytes(workdir / "b.txt", b"same\n")
    assert run("diff", first, second) == (0, "", "")


def test_context_option_changes_the_hunk(workdir):
    old = write_bytes(workdir / "old.txt", b"1\n2\n3\n4\n5\n")
    new = write_bytes(workdir / "new.txt", b"1\n2\nX\n4\n5\n")
    _, out, _ = run("diff", "-U", "0", old, new)
    assert out.splitlines()[2:] == ["@@ -3 +3 @@", "-3", "+X"]


def test_negative_context_is_reported_as_an_error_not_a_traceback(workdir):
    old = write_bytes(workdir / "old.txt", b"a\n")
    new = write_bytes(workdir / "new.txt", b"b\n")
    status, out, err = run("diff", "-U", "-1", old, new)
    assert (status, out) == (2, "")
    assert "context must be a non-negative integer" in err


def test_patch_writes_the_result_to_the_output_file_and_keeps_crlf_endings(workdir):
    original = write_bytes(workdir / "doc.txt", b"first\r\nsecond\r\nthird\r\n")
    changed = write_bytes(workdir / "doc2.txt", b"first\r\nSECOND\r\nthird\r\nfourth\r\n")
    status, patch_text, _ = run("diff", original, changed)
    assert status == 1
    patch_file = write_bytes(workdir / "change.diff", patch_text.encode("utf-8"))

    result_path = workdir / "result.txt"
    assert run("patch", original, patch_file, "-o", str(result_path)) == (0, "", "")
    assert result_path.read_bytes() == b"first\r\nSECOND\r\nthird\r\nfourth\r\n"
    # The input file is never modified.
    assert (workdir / "doc.txt").read_bytes() == b"first\r\nsecond\r\nthird\r\n"


def test_patch_without_output_option_prints_the_result(workdir):
    original = write_bytes(workdir / "f.txt", b"a\nb\n")
    patch_file = write_bytes(workdir / "p.diff", b"--- f\n+++ f\n@@ -1,2 +1,2 @@\n a\n-b\n+B\n")
    assert run("patch", original, patch_file) == (0, "a\nB\n", "")


def test_patch_that_does_not_match_exits_2_with_the_reason_and_no_output(workdir):
    original = write_bytes(workdir / "f.txt", b"a\nDIFFERENT\n")
    patch_file = write_bytes(workdir / "p.diff", b"--- f\n+++ f\n@@ -1,2 +1,2 @@\n a\n-b\n+B\n")
    result_path = workdir / "never.txt"
    status, out, err = run("patch", original, patch_file, "-o", str(result_path))
    assert (status, out) == (2, "")
    assert "hunk 1 does not match at line 2" in err
    assert not result_path.exists()


def test_missing_input_file_exits_2_and_names_the_file(workdir):
    missing = str(workdir / "nope.txt")
    other = write_bytes(workdir / "x.txt", b"x\n")
    status, out, err = run("diff", missing, other)
    assert (status, out) == (2, "")
    assert "nope.txt" in err


def test_input_that_is_not_utf8_exits_2_with_a_readable_message(workdir):
    binary = write_bytes(workdir / "bin.dat", b"\xff\xfe\x00bad")
    other = write_bytes(workdir / "x.txt", b"x\n")
    status, _, err = run("diff", binary, other)
    assert status == 2
    assert "not valid UTF-8 text" in err and "bin.dat" in err


def test_words_command_prints_the_marked_up_line():
    assert run("words", "the quick brown fox", "the slow brown fox") == (
        1,
        "the [-quick-]{+slow+} brown fox\n",
        "",
    )
    assert run("words", "same", "same") == (0, "same\n", "")


def test_unknown_command_is_an_argparse_error():
    with pytest.raises(SystemExit) as caught:
        main(["frobnicate"], stdout=io.StringIO(), stderr=io.StringIO())
    assert caught.value.code == 2


def test_real_process_emits_lf_only_utf8_so_redirected_patches_stay_valid(workdir):
    # On Windows a redirected stdout would turn every "\n" into "\r\n" and use
    # the locale encoding; either would corrupt a patch that is saved to a file.
    old = write_bytes(workdir / "old.txt", "zażółć\nstay\n".encode("utf-8"))
    new = write_bytes(workdir / "new.txt", "gęślą\nstay\n".encode("utf-8"))
    finished = subprocess.run(
        [sys.executable, "-m", "textdiff", "diff", old, new],
        cwd=PROJECT_ROOT,
        capture_output=True,
        timeout=60,
    )
    assert finished.returncode == 1
    assert finished.stderr == b""
    assert b"\r" not in finished.stdout
    lines = finished.stdout.decode("utf-8").split("\n")
    assert lines[2:7] == ["@@ -1,2 +1,2 @@", "-zażółć", "+gęślą", " stay", ""]
