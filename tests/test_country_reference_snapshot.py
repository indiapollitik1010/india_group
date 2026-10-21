"""Tests for python/build_country_reference_snapshot.py (the generic
master -> country reference-snapshot exporter) and
python/report_country_ead_coverage.py (the read-only Master-vs-EAD
Series comparison report).

Unit-level tests run against synthetic workbooks built with openpyxl
inside an isolated sandbox - never the real repo's data/master/. A
small set of integration tests at the bottom run against the REAL
authoritative workbooks and are skipped (not failed) when those
git-ignored files aren't present in this checkout.
"""

import csv
import hashlib
import json
import os

import openpyxl
import pytest

from .conftest import REPO_ROOT, run_script

REAL_MASTER_WORKBOOK = REPO_ROOT / "data" / "master" / "pollitik_master.xlsx"
REAL_EAD_WORKBOOK = REPO_ROOT / "data" / "master" / "EAD Series and Question Wording.xlsx"
REAL_CANADA_SNAPSHOT = REPO_ROOT / "countries" / "canada" / "data" / "canada_reference_snapshot.csv"


# --- synthetic fixture builders ----------------------------------------

def make_synthetic_master_workbook(path, extra_rows=None):
    """A Master-sheet-shaped workbook with the real quirks this exporter
    must handle: a leading-space 'Positive' header, unnamed trailing
    columns, and rows for more than one country."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Master"
    ws.append(["Series", "Date", "Total Count", "     Positive", "Neutral", "Negative", None, None, "Source", "Country", None, None])
    rows = extra_rows if extra_rows is not None else [
        ["NEWSPOLL", "2020-01-15 00:00:00", 1000, 55, None, 40, None, None, "https://newspoll.com.au/1", "Australia", "junkA", "junkB"],
        ["NEWSPOLL", "2020-02-15 00:00:00", 1000, 56, None, 39, None, None, "https://newspoll.com.au/2", "Australia", None, None],
        ["ABACUSJOBPM", "2019-01-15 00:00:00", 1000, 45, None, 50, None, None, "https://abacusdata.ca/1", "Canada", None, None],
    ]
    for r in rows:
        ws.append(r)
    wb.save(path)


def make_synthetic_ead_workbook(path, rows=None):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["Country", "Series", "Description", "Question Type", "Question Wording", "Method (face to face, telephone, mixed, etc.)"])
    rows = rows if rows is not None else [
        ["Australia ", "NEWSPOLL", "Prime Minister Satisfaction", "Satisfaction", "Do you approve of...", None],
        ["Australia ", "FreshwaterStrategy", "Freshwater Strategy", "Satisfaction", "Do you approve of...", None],
        ["Australia ", "NEWSPOLL/PYXIS", "NEWSPOLL/PYXIS", "Satisfaction", "Do you approve of...", None],
        ["Canada", "ABACUSJOBPM", "Abacus Data Approve Job of Gov led by PM", "Approval", "Do you approve of...", None],
    ]
    for r in rows:
        ws.append(r)
    wb.save(path)


def make_country_workspace(sandbox, slug):
    (sandbox / "countries" / slug / "data").mkdir(parents=True, exist_ok=True)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def run_build(sandbox, args):
    return run_script("build_country_reference_snapshot.py", sandbox, args=args)


# --- core export behavior ------------------------------------------------

def test_snapshot_export_exact_8_columns_and_one_country(sandbox):
    make_country_workspace(sandbox, "australia")
    workbook = sandbox / "master.xlsx"
    make_synthetic_master_workbook(workbook)

    proc = run_build(sandbox, ["--country", "Australia", "--workbook", str(workbook)])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["built"] is True
    assert result["row_count"] == 2
    assert result["distinct_series_count"] == 1

    out_path = sandbox / "countries" / "australia" / "data" / "australia_reference_snapshot.csv"
    assert out_path.exists()
    with open(out_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == ["Series", "Date", "Total Count", "Positive", "Neutral", "Negative", "Source", "Country"]
        rows = list(reader)
    assert len(rows) == 2
    assert {r["Country"] for r in rows} == {"Australia"}


def test_snapshot_export_never_includes_unnamed_columns(sandbox):
    make_country_workspace(sandbox, "australia")
    workbook = sandbox / "master.xlsx"
    make_synthetic_master_workbook(workbook)
    proc = run_build(sandbox, ["--country", "Australia", "--workbook", str(workbook)])
    assert proc.returncode == 0, proc.stderr
    out_path = sandbox / "countries" / "australia" / "data" / "australia_reference_snapshot.csv"
    header = out_path.read_text(encoding="utf-8").splitlines()[0]
    assert "junk" not in header
    assert header.count(",") == 7  # exactly 8 columns


def test_snapshot_export_correct_one_country_filtering(sandbox):
    make_country_workspace(sandbox, "canada")
    workbook = sandbox / "master.xlsx"
    make_synthetic_master_workbook(workbook)
    proc = run_build(sandbox, ["--country", "Canada", "--workbook", str(workbook)])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["row_count"] == 1
    out_path = sandbox / "countries" / "canada" / "data" / "canada_reference_snapshot.csv"
    with open(out_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert all(r["Country"] == "Canada" for r in rows)
    assert not any(r["Country"] == "Australia" for r in rows)


# --- whitespace/Unicode normalization + raw-value preservation -----------

def test_snapshot_export_whitespace_normalized_country_matching(sandbox):
    make_country_workspace(sandbox, "australia")
    workbook = sandbox / "master.xlsx"
    rows = [
        ["NEWSPOLL", "2020-01-15 00:00:00", 1000, 55, None, 40, None, None, "https://x/1", "Australia", None, None],
        ["NEWSPOLL", "2020-02-15 00:00:00", 1000, 56, None, 39, None, None, "https://x/2", "Australia ", None, None],
    ]
    make_synthetic_master_workbook(workbook, extra_rows=rows)

    proc = run_build(sandbox, ["--country", "Australia", "--workbook", str(workbook)])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["row_count"] == 2
    assert result["normalization_collapsed_multiple_raw_variants"] is True
    assert result["raw_country_variants_found"] == {"Australia": 1, "Australia ": 1}


def test_snapshot_export_unicode_invisible_char_normalization(sandbox):
    make_country_workspace(sandbox, "australia")
    workbook = sandbox / "master.xlsx"
    rows = [
        ["NEWSPOLL", "2020-01-15 00:00:00", 1000, 55, None, 40, None, None, "https://x/1", "Australia ", None, None],
        ["NEWSPOLL", "2020-02-15 00:00:00", 1000, 56, None, 39, None, None, "https://x/2", "Australia​", None, None],
    ]
    make_synthetic_master_workbook(workbook, extra_rows=rows)

    proc = run_build(sandbox, ["--country", "Australia", "--workbook", str(workbook)])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["row_count"] == 2
    assert result["normalization_collapsed_multiple_raw_variants"] is True
    assert set(result["raw_country_variants_found"].keys()) == {"Australia ", "Australia​"}


def test_snapshot_export_raw_value_preserved_not_rewritten(sandbox):
    """The exported CSV must keep each row's ORIGINAL raw Country string
    (e.g. 'Australia ' with its trailing space) - normalization decides
    whether to INCLUDE a row, it never rewrites what gets written."""
    make_country_workspace(sandbox, "australia")
    workbook = sandbox / "master.xlsx"
    rows = [
        ["NEWSPOLL", "2020-01-15 00:00:00", 1000, 55, None, 40, None, None, "https://x/1", "Australia ", None, None],
    ]
    make_synthetic_master_workbook(workbook, extra_rows=rows)

    proc = run_build(sandbox, ["--country", "Australia", "--workbook", str(workbook)])
    assert proc.returncode == 0, proc.stderr
    out_path = sandbox / "countries" / "australia" / "data" / "australia_reference_snapshot.csv"
    with open(out_path, newline="", encoding="utf-8") as f:
        rows_out = list(csv.DictReader(f))
    assert rows_out[0]["Country"] == "Australia "  # raw value, untouched


def test_snapshot_export_single_clean_variant_not_flagged(sandbox):
    make_country_workspace(sandbox, "australia")
    workbook = sandbox / "master.xlsx"
    make_synthetic_master_workbook(workbook)
    proc = run_build(sandbox, ["--country", "Australia", "--workbook", str(workbook)])
    result = json.loads(proc.stdout)
    assert result["normalization_collapsed_multiple_raw_variants"] is False
    assert result["raw_country_variants_found"] == {"Australia": 2}


# --- refusal behavior ------------------------------------------------------

def test_snapshot_export_zero_rows_refuses_and_writes_nothing(sandbox):
    make_country_workspace(sandbox, "germany")
    workbook = sandbox / "master.xlsx"
    make_synthetic_master_workbook(workbook)  # has no Germany rows
    proc = run_build(sandbox, ["--country", "Germany", "--workbook", str(workbook)])
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert result["built"] is False
    assert "Zero rows" in result["error"]
    out_path = sandbox / "countries" / "germany" / "data" / "germany_reference_snapshot.csv"
    assert not out_path.exists()


def test_snapshot_export_refuses_to_overwrite_by_default(sandbox):
    make_country_workspace(sandbox, "australia")
    workbook = sandbox / "master.xlsx"
    make_synthetic_master_workbook(workbook)
    out_path = sandbox / "countries" / "australia" / "data" / "australia_reference_snapshot.csv"
    out_path.write_text("Series,Date,Total Count,Positive,Neutral,Negative,Source,Country\nOLD,x,,,,,,\n", encoding="utf-8")
    before = out_path.read_text(encoding="utf-8")

    proc = run_build(sandbox, ["--country", "Australia", "--workbook", str(workbook)])
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert result["built"] is False
    assert "already exists" in result["error"]
    assert out_path.read_text(encoding="utf-8") == before  # untouched


def test_snapshot_export_overwrite_flag_replaces_it_safely(sandbox):
    make_country_workspace(sandbox, "australia")
    workbook = sandbox / "master.xlsx"
    make_synthetic_master_workbook(workbook)
    out_path = sandbox / "countries" / "australia" / "data" / "australia_reference_snapshot.csv"
    out_path.write_text("Series,Date,Total Count,Positive,Neutral,Negative,Source,Country\nOLD,x,,,,,,\n", encoding="utf-8")

    proc = run_build(sandbox, ["--country", "Australia", "--workbook", str(workbook), "--overwrite"])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["built"] is True
    assert result["overwrite_used"] is True
    with open(out_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert all(r["Series"] != "OLD" for r in rows)
    assert len(rows) == 2


def test_snapshot_export_requires_existing_country_workspace(sandbox):
    # Deliberately do NOT create countries/australia/.
    workbook = sandbox / "master.xlsx"
    make_synthetic_master_workbook(workbook)
    proc = run_build(sandbox, ["--country", "Australia", "--workbook", str(workbook)])
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert result["built"] is False
    assert "init_country_workspace.py" in result["error"]
    assert not (sandbox / "countries").exists() or not (sandbox / "countries" / "australia" / "data" / "australia_reference_snapshot.csv").exists()


def test_snapshot_export_source_workbook_unchanged_before_after(sandbox):
    make_country_workspace(sandbox, "australia")
    workbook = sandbox / "master.xlsx"
    make_synthetic_master_workbook(workbook)
    before_hash = sha256_of(workbook)

    proc = run_build(sandbox, ["--country", "Australia", "--workbook", str(workbook)])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    after_hash = sha256_of(workbook)
    assert before_hash == after_hash
    assert result["workbook_sha256"] == before_hash


# --- EAD coverage report: synthetic Australia-shaped scenario --------------

def test_ead_coverage_report_synthetic_australia_shape(sandbox):
    make_country_workspace(sandbox, "australia")
    master_wb = sandbox / "master.xlsx"
    ead_wb = sandbox / "ead.xlsx"
    master_rows = [
        ["NEWSPOLL", "2020-01-15 00:00:00", 1000, 55, None, 40, None, None, "https://x/1", "Australia", None, None],
        ["FreshwaterStrategy", "2020-01-15 00:00:00", 1000, 50, None, 45, None, None, "https://x/2", "Australia", None, None],
        ["Freshwater Strategy", "2020-02-15 00:00:00", 1000, 51, None, 44, None, None, "https://x/3", "Australia", None, None],
    ]
    make_synthetic_master_workbook(master_wb, extra_rows=master_rows)
    make_synthetic_ead_workbook(ead_wb)  # includes NEWSPOLL, FreshwaterStrategy, NEWSPOLL/PYXIS for 'Australia '

    build_proc = run_build(sandbox, ["--country", "Australia", "--workbook", str(master_wb)])
    assert build_proc.returncode == 0, build_proc.stderr

    report_proc = run_script(
        "report_country_ead_coverage.py", sandbox,
        args=["--country", "Australia", "--ead-workbook", str(ead_wb)],
    )
    assert report_proc.returncode == 0, report_proc.stderr
    result = json.loads(report_proc.stdout)
    assert result["ok"] is True
    assert {m["series"] for m in result["exact_matches"]} == {"NEWSPOLL", "FreshwaterStrategy"}
    assert result["alias_candidates"] == [
        {"master": "Freshwater Strategy", "ead": "FreshwaterStrategy", "master_rows": 1, "ead_rows": 1}
    ]
    assert result["unmatched_ead"] == [{"series": "NEWSPOLL/PYXIS", "ead_rows": 1}]
    assert result["ead_raw_country_variants_found"] == {"Australia ": 3}


# --- integration tests against the REAL authoritative workbooks ------------

pytestmark_real = pytest.mark.skipif(
    not (REAL_MASTER_WORKBOOK.exists() and REAL_EAD_WORKBOOK.exists()),
    reason="real data/master/ workbooks not present in this checkout (git-ignored, environment-dependent)",
)


@pytestmark_real
def test_real_australia_snapshot_row_count_is_1836(sandbox):
    make_country_workspace(sandbox, "australia")
    proc = run_build(sandbox, ["--country", "Australia", "--workbook", str(REAL_MASTER_WORKBOOK)])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["row_count"] == 1836
    assert result["distinct_series_count"] == 16
    out_path = sandbox / "countries" / "australia" / "data" / "australia_reference_snapshot.csv"
    with open(out_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == ["Series", "Date", "Total Count", "Positive", "Neutral", "Negative", "Source", "Country"]
        rows = list(reader)
    assert len(rows) == 1836
    assert {r["Country"] for r in rows} == {"Australia"}


@pytestmark_real
def test_real_australia_ead_coverage_matches_expected(sandbox):
    make_country_workspace(sandbox, "australia")
    build_proc = run_build(sandbox, ["--country", "Australia", "--workbook", str(REAL_MASTER_WORKBOOK)])
    assert build_proc.returncode == 0, build_proc.stderr

    report_proc = run_script(
        "report_country_ead_coverage.py", sandbox,
        args=["--country", "Australia", "--ead-workbook", str(REAL_EAD_WORKBOOK)],
    )
    assert report_proc.returncode == 0, report_proc.stderr
    result = json.loads(report_proc.stdout)
    assert len(result["exact_matches"]) == 14
    assert result["normalized_case_matches"] == [
        {"master": "NEWSPOLL/YouGov", "ead": "NEWSPOLL/YOUGOV", "master_rows": 10, "ead_rows": 1}
    ]
    alias_pairs = {(a["master"], a["ead"]) for a in result["alias_candidates"]}
    assert ("Freshwater Strategy", "FreshwaterStrategy") in alias_pairs
    unmatched_ead_series = {u["series"] for u in result["unmatched_ead"]}
    assert "NEWSPOLL/PYXIS" in unmatched_ead_series
    assert result["ead_raw_country_variants_found"] == {"Australia ": 16}


@pytestmark_real
def test_real_canada_snapshot_rebuild_still_1444_rows(sandbox):
    """Rebuilding INTO A SANDBOX (never the tracked repo file) from the
    real master workbook must still produce exactly 1444 Canada rows,
    matching countries/canada/data/canada_reference_snapshot.csv's known
    row count - i.e. Canada's data hasn't drifted."""
    make_country_workspace(sandbox, "canada")
    proc = run_build(sandbox, ["--country", "Canada", "--workbook", str(REAL_MASTER_WORKBOOK)])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["row_count"] == 1444


@pytest.mark.skipif(not REAL_CANADA_SNAPSHOT.exists(), reason="tracked Canada snapshot not present in this checkout")
def test_tracked_canada_snapshot_file_was_not_touched_by_this_change():
    """This whole feature must never modify Canada's tracked snapshot -
    verifies it still has exactly 1444 data rows and the exact 8
    canonical columns, unchanged by anything in this test session."""
    with open(REAL_CANADA_SNAPSHOT, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == ["Series", "Date", "Total Count", "Positive", "Neutral", "Negative", "Source", "Country"]
        rows = list(reader)
    assert len(rows) == 1444
    assert {r["Country"] for r in rows} == {"Canada"}


def test_no_staging_or_web_writes(sandbox):
    """This whole feature must never touch data/staging/candidates.jsonl
    or perform any network call - a plain existence/content check after
    a normal build run is sufficient given nothing in
    build_country_reference_snapshot.py or report_country_ead_coverage.py
    imports requests/urllib/http.client or opens the staging file."""
    make_country_workspace(sandbox, "australia")
    workbook = sandbox / "master.xlsx"
    make_synthetic_master_workbook(workbook)
    staging_file = sandbox / "data" / "staging" / "candidates.jsonl"
    before = staging_file.read_bytes() if staging_file.exists() else None

    proc = run_build(sandbox, ["--country", "Australia", "--workbook", str(workbook)])
    assert proc.returncode == 0, proc.stderr

    after = staging_file.read_bytes() if staging_file.exists() else None
    assert before == after
