"""Tests for python/build_reference_csv.py (the generic master workbook
-> shared ALL-country reference CSV exporter) and the fallback support
python/build_country_reference_snapshot.py gained for using that shared
CSV when the master workbook itself isn't present in a checkout.

Unit-level tests run against synthetic workbooks/CSVs inside an isolated
sandbox - never the real repo's data/master/. A small set of integration
tests at the bottom run against the REAL authoritative workbook and the
real tracked data/reference/pollitik_reference.csv, and are skipped (not
failed) when those git-ignored/build-time files aren't present in this
checkout.
"""

import csv
import hashlib
import json
import os

import openpyxl
import pytest

from .conftest import REPO_ROOT, run_script
from .test_country_reference_snapshot import make_country_workspace, make_synthetic_master_workbook

REAL_MASTER_WORKBOOK = REPO_ROOT / "data" / "master" / "pollitik_master.xlsx"
REAL_SHARED_REFERENCE_CSV = REPO_ROOT / "data" / "reference" / "pollitik_reference.csv"

CANON_HEADER = ["Series", "Date", "Total Count", "Positive", "Neutral", "Negative", "Source", "Country"]


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def run_build_csv(sandbox, args):
    return run_script("build_reference_csv.py", sandbox, args=args)


def run_build_snapshot(sandbox, args):
    return run_script("build_country_reference_snapshot.py", sandbox, args=args)


# --- build_reference_csv.py: core export behavior --------------------------

def test_shared_csv_exports_all_countries_in_canonical_columns(sandbox):
    workbook = sandbox / "master.xlsx"
    make_synthetic_master_workbook(workbook)  # 2 Australia rows + 1 Canada row
    out_path = sandbox / "data" / "reference" / "pollitik_reference.csv"

    proc = run_build_csv(sandbox, ["--workbook", str(workbook), "--output", str(out_path)])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["built"] is True
    assert result["row_count"] == 3
    assert result["country_count"] == 2

    assert out_path.exists()
    with open(out_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == CANON_HEADER
        rows = list(reader)
    assert len(rows) == 3
    assert {r["Country"] for r in rows} == {"Australia", "Canada"}


def test_shared_csv_never_includes_unnamed_columns(sandbox):
    workbook = sandbox / "master.xlsx"
    make_synthetic_master_workbook(workbook)
    out_path = sandbox / "data" / "reference" / "pollitik_reference.csv"
    proc = run_build_csv(sandbox, ["--workbook", str(workbook), "--output", str(out_path)])
    assert proc.returncode == 0, proc.stderr
    header = out_path.read_text(encoding="utf-8").splitlines()[0]
    assert "junk" not in header
    assert header.count(",") == 7  # exactly 8 columns


def test_shared_csv_refuses_to_overwrite_by_default(sandbox):
    workbook = sandbox / "master.xlsx"
    make_synthetic_master_workbook(workbook)
    out_path = sandbox / "data" / "reference" / "pollitik_reference.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("Series,Date,Total Count,Positive,Neutral,Negative,Source,Country\nOLD,x,,,,,,\n", encoding="utf-8")
    before = out_path.read_text(encoding="utf-8")

    proc = run_build_csv(sandbox, ["--workbook", str(workbook), "--output", str(out_path)])
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert result["built"] is False
    assert "already exists" in result["error"]
    assert out_path.read_text(encoding="utf-8") == before


def test_shared_csv_overwrite_flag_replaces_it(sandbox):
    workbook = sandbox / "master.xlsx"
    make_synthetic_master_workbook(workbook)
    out_path = sandbox / "data" / "reference" / "pollitik_reference.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("Series,Date,Total Count,Positive,Neutral,Negative,Source,Country\nOLD,x,,,,,,\n", encoding="utf-8")

    proc = run_build_csv(sandbox, ["--workbook", str(workbook), "--output", str(out_path), "--overwrite"])
    assert proc.returncode == 0, proc.stderr
    with open(out_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert all(r["Series"] != "OLD" for r in rows)
    assert len(rows) == 3


def test_shared_csv_zero_rows_refuses_and_writes_nothing(sandbox):
    workbook = sandbox / "master.xlsx"
    make_synthetic_master_workbook(workbook, extra_rows=[])
    out_path = sandbox / "data" / "reference" / "pollitik_reference.csv"
    proc = run_build_csv(sandbox, ["--workbook", str(workbook), "--output", str(out_path)])
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert result["built"] is False
    assert "Zero rows" in result["error"]
    assert not out_path.exists()


def test_shared_csv_source_workbook_unchanged_before_after(sandbox):
    workbook = sandbox / "master.xlsx"
    make_synthetic_master_workbook(workbook)
    out_path = sandbox / "data" / "reference" / "pollitik_reference.csv"
    before_hash = sha256_of(workbook)

    proc = run_build_csv(sandbox, ["--workbook", str(workbook), "--output", str(out_path)])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    after_hash = sha256_of(workbook)
    assert before_hash == after_hash
    assert result["workbook_sha256"] == before_hash


# --- build_country_reference_snapshot.py: shared-CSV fallback --------------

def test_country_snapshot_falls_back_to_shared_csv_when_workbook_missing(sandbox):
    make_country_workspace(sandbox, "canada")
    shared_csv = sandbox / "shared_reference.csv"
    with open(shared_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CANON_HEADER)
        writer.writeheader()
        writer.writerow({"Series": "ABACUSJOBPM", "Date": "2019-01-15", "Total Count": "1000",
                          "Positive": "45", "Neutral": "", "Negative": "50",
                          "Source": "https://abacusdata.ca/1", "Country": "Canada"})
        writer.writerow({"Series": "NEWSPOLL", "Date": "2020-01-15", "Total Count": "1000",
                          "Positive": "55", "Neutral": "", "Negative": "40",
                          "Source": "https://newspoll.com.au/1", "Country": "Australia"})

    missing_workbook = sandbox / "does_not_exist.xlsx"
    proc = run_build_snapshot(sandbox, [
        "--country", "Canada",
        "--workbook", str(missing_workbook),
        "--shared-reference-csv", str(shared_csv),
    ])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["built"] is True
    assert result["source"] == "shared_reference_csv"
    assert result["row_count"] == 1

    out_path = sandbox / "countries" / "canada" / "data" / "canada_reference_snapshot.csv"
    with open(out_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == CANON_HEADER
        rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["Country"] == "Canada"


def test_country_snapshot_prefers_workbook_over_shared_csv_when_both_present(sandbox):
    make_country_workspace(sandbox, "canada")
    workbook = sandbox / "master.xlsx"
    make_synthetic_master_workbook(workbook)  # has 1 real Canada row

    shared_csv = sandbox / "shared_reference.csv"
    with open(shared_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CANON_HEADER)
        writer.writeheader()
        for _ in range(5):
            writer.writerow({"Series": "FAKE", "Date": "2000-01-01", "Total Count": "1",
                              "Positive": "1", "Neutral": "", "Negative": "1",
                              "Source": "https://fake", "Country": "Canada"})

    proc = run_build_snapshot(sandbox, [
        "--country", "Canada", "--workbook", str(workbook),
        "--shared-reference-csv", str(shared_csv),
    ])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["source"] == "master_workbook"
    assert result["row_count"] == 1  # from the workbook, not the 5-row shared CSV


def test_country_snapshot_errors_clearly_when_neither_source_available(sandbox):
    make_country_workspace(sandbox, "canada")
    missing_workbook = sandbox / "does_not_exist.xlsx"
    missing_csv = sandbox / "also_does_not_exist.csv"
    proc = run_build_snapshot(sandbox, [
        "--country", "Canada",
        "--workbook", str(missing_workbook),
        "--shared-reference-csv", str(missing_csv),
    ])
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert result["built"] is False
    assert "Neither the master workbook" in result["error"]


def test_country_snapshot_shared_csv_fallback_zero_rows_refuses(sandbox):
    make_country_workspace(sandbox, "germany")
    shared_csv = sandbox / "shared_reference.csv"
    with open(shared_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CANON_HEADER)
        writer.writeheader()
        writer.writerow({"Series": "X", "Date": "2000-01-01", "Total Count": "1",
                          "Positive": "1", "Neutral": "", "Negative": "1",
                          "Source": "https://x", "Country": "Canada"})

    missing_workbook = sandbox / "does_not_exist.xlsx"
    proc = run_build_snapshot(sandbox, [
        "--country", "Germany",
        "--workbook", str(missing_workbook),
        "--shared-reference-csv", str(shared_csv),
    ])
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert result["built"] is False
    assert "Zero rows" in result["error"]


def test_country_snapshot_no_staging_or_web_writes_via_shared_csv(sandbox):
    make_country_workspace(sandbox, "canada")
    shared_csv = sandbox / "shared_reference.csv"
    with open(shared_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CANON_HEADER)
        writer.writeheader()
        writer.writerow({"Series": "X", "Date": "2000-01-01", "Total Count": "1",
                          "Positive": "1", "Neutral": "", "Negative": "1",
                          "Source": "https://x", "Country": "Canada"})
    staging_file = sandbox / "data" / "staging" / "candidates.jsonl"
    before = staging_file.read_bytes() if staging_file.exists() else None

    missing_workbook = sandbox / "does_not_exist.xlsx"
    proc = run_build_snapshot(sandbox, [
        "--country", "Canada",
        "--workbook", str(missing_workbook),
        "--shared-reference-csv", str(shared_csv),
    ])
    assert proc.returncode == 0, proc.stderr

    after = staging_file.read_bytes() if staging_file.exists() else None
    assert before == after


# --- integration tests against the REAL authoritative workbook/CSV ---------

pytestmark_real_workbook = pytest.mark.skipif(
    not REAL_MASTER_WORKBOOK.exists(),
    reason="real data/master/pollitik_master.xlsx not present in this checkout (git-ignored, environment-dependent)",
)

pytestmark_real_shared_csv = pytest.mark.skipif(
    not REAL_SHARED_REFERENCE_CSV.exists(),
    reason="tracked data/reference/pollitik_reference.csv not present in this checkout",
)


@pytestmark_real_workbook
def test_real_shared_csv_rebuild_row_and_country_counts(sandbox):
    out_path = sandbox / "pollitik_reference.csv"
    proc = run_build_csv(sandbox, ["--workbook", str(REAL_MASTER_WORKBOOK), "--output", str(out_path)])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["row_count"] == 81518
    assert result["country_count"] == 268
    assert result["country_row_counts"]["new zealand"] == 487
    with open(out_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == CANON_HEADER
        rows = list(reader)
    assert len(rows) == 81518


@pytestmark_real_shared_csv
def test_tracked_shared_reference_csv_row_count_and_columns():
    """The tracked data/reference/pollitik_reference.csv must keep its
    known shape - verifies it wasn't hand-edited or partially written."""
    with open(REAL_SHARED_REFERENCE_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == CANON_HEADER
        rows = list(reader)
    assert len(rows) == 81518
    countries = {r["Country"].strip().casefold() for r in rows}
    assert "new zealand" in countries
    assert "canada" in countries
    assert "australia" in countries


@pytestmark_real_shared_csv
def test_real_new_zealand_snapshot_buildable_from_shared_csv_alone(sandbox):
    """New Zealand's per-country snapshot must be buildable from the
    tracked shared CSV even with no master workbook present at all -
    this is the whole point of the fallback. Uses the real "new-zealand"
    slug (normalize_country_slug("New Zealand") == "new-zealand"),
    matching the repo's existing countries/new-zealand/ folder."""
    slug = "new-zealand"
    make_country_workspace(sandbox, slug)
    missing_workbook = sandbox / "does_not_exist.xlsx"
    proc = run_build_snapshot(sandbox, [
        "--country", "New Zealand",
        "--workbook", str(missing_workbook),
        "--shared-reference-csv", str(REAL_SHARED_REFERENCE_CSV),
    ])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["source"] == "shared_reference_csv"
    assert result["row_count"] == 487
    assert result["country_slug"] == slug

    out_path = sandbox / "countries" / slug / "data" / "{}_reference_snapshot.csv".format(slug)
    with open(out_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == CANON_HEADER
        rows = list(reader)
    assert len(rows) == 487
    assert all(r["Country"].strip().casefold() == "new zealand" for r in rows)
