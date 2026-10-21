"""Tests for the EAD Series/Question-Wording reference workbook
integration: python/build_ead_reference_index.py, python/ead_series_lookup.py,
pollitik_common.normalize_question_wording, validate_record.py's
check_ead_wording_match, and the pollitik_guard.py protection for
docs/ead/. Synthetic fixture workbooks only - the real committed
docs/ead/reference workbook is touched only by the read-only
byte-identical check, never written to.
"""

import hashlib
import json
import sys
from pathlib import Path

import openpyxl
import pytest

from .conftest import REPO_ROOT, run_hook, run_script

sys.path.insert(0, str(REPO_ROOT / "python"))
import pollitik_common as pc  # noqa: E402
import validate_record  # noqa: E402


def make_fixture_reference_workbook(path, rows=None):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["Country", "Series", "Description", "Question Type", "Question Wording",
               "Method (face to face, telephone, mixed, etc.)"])
    default_rows = [
        ("TestCountry", "TESTAPP", "Test Pollster (approval)", "Approval",
         "Do you approve or disapprove of the way [NAME] is handling the job?", "Telephone"),
        ("TestCountry", "OTHERAPP", "Other Pollster (approval)", "Approval",
         "Do you have a favorable or unfavorable opinion of [NAME]?", "Online"),
        ("TestCountry", "BLANKWORDING", "Some Pollster, wording not confirmed", None, None, None),
    ]
    for row in (rows if rows is not None else default_rows):
        ws.append(list(row))
    wb.save(path)


def build_index(sandbox, workbook_path):
    proc = run_script(
        "build_ead_reference_index.py", sandbox,
        args=["--workbook", str(workbook_path), "--index", str(sandbox / "data" / "reference_index.duckdb")],
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def lookup(sandbox, args):
    proc = run_script(
        "ead_series_lookup.py", sandbox,
        args=["--index", str(sandbox / "data" / "reference_index.duckdb"), *args],
    )
    return json.loads(proc.stdout)


# --- 1: exact question wording finds its Series ----------------------------

def test_exact_wording_finds_series(sandbox):
    workbook = sandbox / "ead_reference.xlsx"
    make_fixture_reference_workbook(workbook)
    build_index(sandbox, workbook)

    result = lookup(sandbox, [
        "--wording-exact", "Do you approve or disapprove of the way [NAME] is handling the job?",
    ])
    assert result["row_count_returned"] == 1
    assert result["rows"][0]["Series"] == "TESTAPP"


# --- 2: capitalization/punctuation variation finds the same Series --------

def test_normalized_wording_variant_finds_same_series(sandbox):
    workbook = sandbox / "ead_reference.xlsx"
    make_fixture_reference_workbook(workbook)
    build_index(sandbox, workbook)

    # Different case, extra whitespace, curly quotes vs straight - same
    # underlying question.
    variant = "  DO  YOU approve or disapprove of the way [NAME] is handling the job?  "
    result = lookup(sandbox, ["--wording-exact", variant])
    assert result["row_count_returned"] == 1
    assert result["rows"][0]["Series"] == "TESTAPP"


# --- 3: unrelated wording does not produce a false match -------------------

def test_unrelated_wording_no_false_match(sandbox):
    workbook = sandbox / "ead_reference.xlsx"
    make_fixture_reference_workbook(workbook)
    build_index(sandbox, workbook)

    result = lookup(sandbox, [
        "--wording-exact", "What is your opinion of the national football team?",
    ])
    assert result["row_count_returned"] == 0


def test_wording_contains_does_not_cross_match_different_series(sandbox):
    workbook = sandbox / "ead_reference.xlsx"
    make_fixture_reference_workbook(workbook)
    build_index(sandbox, workbook)

    result = lookup(sandbox, ["--wording-contains", "approve or disapprove"])
    assert result["row_count_returned"] == 1
    assert result["rows"][0]["Series"] == "TESTAPP"
    result2 = lookup(sandbox, ["--wording-contains", "favorable or unfavorable"])
    assert result2["row_count_returned"] == 1
    assert result2["rows"][0]["Series"] == "OTHERAPP"


# --- 4: ambiguous wording routes to SERIES_REVIEW_REQUIRED -----------------

def test_ambiguous_ead_match_status_routes_to_review():
    record = {
        "country": "TestCountry",
        "series": "TESTAPP",
        "pollster": "Test Pollster",
        "question_wording_status": "EXACT_WORDING",
        "positive": 58, "negative": 36, "neutral": None,
        "response_categories": {"Well": 58, "Poorly": 36},
        "category_classification": {"Well": "positive", "Poorly": "negative"},
        "sample_size": 1000,
        "fieldwork_date_normalized": "1/8/2026", "fieldwork_date_status": "OBSERVED",
        "requested_url": "https://approved-pollster.example/report",
        "final_url": "https://approved-pollster.example/report",
        "http_status": 200, "retrieved_at": "2026-08-14T00:00:00Z",
        "evidence_text": "Well 58, Poorly 36.",
        "ead_wording_match_status": "SERIES_REVIEW_REQUIRED",
    }
    result = validate_record.validate(record)
    assert result["validation_status"] == "REVIEW"
    assert "SERIES_REVIEW_REQUIRED" in result["validation_flags"]


def test_ead_match_tiers_are_informational_not_blocking():
    base = {
        "country": "TestCountry", "series": "TESTAPP", "pollster": "Test Pollster",
        "question_wording_status": "EXACT_WORDING",
        "positive": 58, "negative": 36, "neutral": None,
        "response_categories": {"Well": 58, "Poorly": 36},
        "category_classification": {"Well": "positive", "Poorly": "negative"},
        "sample_size": 1000,
        "fieldwork_date_normalized": "1/8/2026", "fieldwork_date_status": "OBSERVED",
        "requested_url": "https://approved-pollster.example/report",
        "final_url": "https://approved-pollster.example/report",
        "http_status": 200, "retrieved_at": "2026-08-14T00:00:00Z",
        "evidence_text": "Well 58, Poorly 36.",
    }
    for status in ("SERIES_MATCH_EXACT", "SERIES_MATCH_NORMALIZED", "SERIES_MATCH_SUPPORTED"):
        record = dict(base, ead_wording_match_status=status)
        result = validate_record.validate(record)
        assert result["validation_status"] == "APPROVED", (status, result["validation_reason"])

    # Absence entirely is likewise never penalized.
    result = validate_record.validate(base)
    assert result["validation_status"] == "APPROVED"


# --- 5: original wording is preserved ---------------------------------------

def test_original_wording_preserved_verbatim_in_index(sandbox):
    workbook = sandbox / "ead_reference.xlsx"
    original = "  Do you approve or disapprove of the way [NAME] is handling the job?"
    make_fixture_reference_workbook(workbook, rows=[
        ("TestCountry", "TESTAPP", "Test Pollster", "Approval", original, "Telephone"),
    ])
    build_index(sandbox, workbook)
    result = lookup(sandbox, ["--series", "TESTAPP"])
    assert result["rows"][0]["Question Wording"] == original
    # normalized form differs (trimmed/lowercased) but original is untouched
    assert result["rows"][0]["question_wording_normalized"] != original


# --- 6: reference workbook is never modified --------------------------------

def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_real_reference_workbook_byte_identical_after_indexing():
    real_workbook = REPO_ROOT / "docs" / "ead" / "reference" / "EAD Series and Question Wording.xlsx"
    if not real_workbook.exists():
        pytest.skip("Real EAD reference workbook not present in this checkout.")
    before = _sha256(real_workbook)
    proc = run_script("build_ead_reference_index.py", REPO_ROOT, args=["--workbook", str(real_workbook)])
    assert proc.returncode == 0, proc.stderr
    after = _sha256(real_workbook)
    assert before == after, "docs/ead/reference workbook changed after being read - it must stay read-only"


# --- 7: production writer / hook never touch the reference workbook -------

def test_apply_changes_source_never_references_ead_reference_dir():
    source = (REPO_ROOT / "python" / "apply_changes.py").read_text(encoding="utf-8")
    assert "docs/ead" not in source
    assert "docs" + chr(92) + "ead" not in source  # no Windows-style path either


def test_hook_blocks_write_tool_on_ead_reference_path():
    decision = run_hook("Write", {
        "file_path": "docs/ead/reference/EAD Series and Question Wording.xlsx",
        "content": "x",
    })
    assert decision.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def test_hook_blocks_destructive_bash_on_ead_reference_dir():
    decision = run_hook("Bash", {"command": "rm -rf docs/ead/reference"})
    assert decision.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def test_hook_blocks_write_looking_bash_on_ead_manual_txt():
    decision = run_hook("Bash", {
        "command": 'echo "oops" >> "docs/ead/EAD MANUAL.txt"',
    })
    assert decision.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def test_hook_still_allows_read_only_command_mentioning_ead_reference_path():
    decision = run_hook("Bash", {
        "command": 'python3 python/build_ead_reference_index.py --workbook "docs/ead/reference/EAD Series and Question Wording.xlsx"',
    })
    assert decision == {}  # no opinion -> allowed (read-only invocation)


def test_hook_still_allows_devnull_redirect_in_command_mentioning_ead_path():
    # Regression: a `2>/dev/null` in an otherwise read-only diagnostic
    # command must not be mistaken for a write, just because a docs/ead
    # path also appears somewhere in the same command line.
    decision = run_hook("Bash", {
        "command": 'md5sum "docs/ead/reference/EAD Series and Question Wording.xlsx" 2>/dev/null',
    })
    assert decision == {}


def test_hook_still_allows_plain_copy_into_ead_dir():
    decision = run_hook("Bash", {
        "command": 'cp ~/Downloads/"Some New Reference.xlsx" docs/ead/reference/',
    })
    assert decision == {}  # populating the directory (not modifying existing content) stays allowed


# --- 8: DuckDB reference index can be rebuilt (and shared safely) ---------

def test_ead_reference_index_reports_cleanly_with_no_workbook(sandbox):
    proc = run_script(
        "build_ead_reference_index.py", sandbox,
        args=["--workbook", str(sandbox / "nope.xlsx"), "--index", str(sandbox / "data" / "reference_index.duckdb")],
    )
    result = json.loads(proc.stdout)
    assert result["built"] is False
    assert not (sandbox / "data" / "reference_index.duckdb").exists()


def test_ead_reference_index_rebuild_is_idempotent(sandbox):
    workbook = sandbox / "ead_reference.xlsx"
    make_fixture_reference_workbook(workbook)
    first = build_index(sandbox, workbook)
    second = build_index(sandbox, workbook)
    assert first["rows"] == second["rows"] == 3


def test_master_index_rebuild_does_not_wipe_ead_reference_table(sandbox):
    ead_workbook = sandbox / "ead_reference.xlsx"
    make_fixture_reference_workbook(ead_workbook)
    build_index(sandbox, ead_workbook)

    master_workbook = sandbox / "data" / "master" / "pollitik_master.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(["Country", "Series"])
    ws.append(["TestCountry", "TESTAPP"])
    wb.save(master_workbook)

    proc = run_script(
        "build_reference_index.py", sandbox,
        args=["--workbook", str(master_workbook), "--index", str(sandbox / "data" / "reference_index.duckdb")],
    )
    assert proc.returncode == 0, proc.stderr

    # ead_series_reference must have survived the master-index rebuild.
    result = lookup(sandbox, ["--series", "TESTAPP"])
    assert result["found_index"] is True
    assert result["row_count_returned"] == 1

    # ...and rebuilding the EAD reference index must not wipe the master
    # workbook's table either.
    build_index(sandbox, ead_workbook)
    import duckdb
    con = duckdb.connect(str(sandbox / "data" / "reference_index.duckdb"), read_only=True)
    tables = [r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()]
    con.close()
    assert "data" in tables  # normalize_table_name("Data") -> "data"
    assert "ead_series_reference" in tables


# --- 9: reference lookup returns only small relevant result sets ----------

def test_ead_lookup_limit_is_enforced_and_unmapped_filters_reported(sandbox):
    rows = [
        ("TestCountry", f"SERIES{i}", "Test Pollster", "Approval",
         "Do you approve of the president's job performance?", "Telephone")
        for i in range(5)
    ]
    workbook = sandbox / "ead_reference.xlsx"
    make_fixture_reference_workbook(workbook, rows=rows)
    build_index(sandbox, workbook)

    result = lookup(sandbox, ["--wording-contains", "approve", "--limit", "2"])
    assert result["row_count_returned"] == 2
    assert result["limit"] == 2

    unmapped = lookup(sandbox, ["--pollster", "Test Pollster", "--executive-type", "president"])
    assert set(unmapped["unmapped_filters"]) == {"pollster", "executive_type"}
    # Unmapped filters are reported, not silently applied to the wrong column.
    assert unmapped["row_count_returned"] == 5
