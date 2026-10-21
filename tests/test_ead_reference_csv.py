"""Tests for python/build_ead_reference_csv.py (the generic EAD workbook
-> shared ALL-country EAD reference CSV exporter) and
python/build_country_ead_snapshot.py (the per-country EAD exporter, which
prefers the real EAD workbook when present and falls back to that shared
CSV otherwise).

Unit-level tests run against synthetic EAD workbooks/CSVs inside an
isolated sandbox - never the real repo's data/master/. A small set of
integration tests at the bottom run against the REAL authoritative EAD
workbook and the real tracked data/reference/ead_series_question_wording.csv,
and are skipped (not failed) when those git-ignored/build-time files
aren't present in this checkout.
"""

import csv
import hashlib
import json

import pytest

from .conftest import REPO_ROOT, run_script
from .test_country_reference_snapshot import make_country_workspace, make_synthetic_ead_workbook

REAL_EAD_WORKBOOK = REPO_ROOT / "data" / "master" / "EAD Series and Question Wording.xlsx"
REAL_SHARED_EAD_CSV = REPO_ROOT / "data" / "reference" / "ead_series_question_wording.csv"

CANON_HEADER = ["Country", "Series", "Description", "Question Type", "Question Wording", "Method"]


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def run_build_ead_csv(sandbox, args):
    return run_script("build_ead_reference_csv.py", sandbox, args=args)


def run_build_country_ead(sandbox, args):
    return run_script("build_country_ead_snapshot.py", sandbox, args=args)


# --- build_ead_reference_csv.py: core export behavior -----------------------

def test_shared_ead_csv_exports_all_countries_in_canonical_columns(sandbox):
    ead_wb = sandbox / "ead.xlsx"
    make_synthetic_ead_workbook(ead_wb)  # 3 Australia rows + 1 Canada row
    out_path = sandbox / "data" / "reference" / "ead_series_question_wording.csv"

    proc = run_build_ead_csv(sandbox, ["--ead-workbook", str(ead_wb), "--output", str(out_path)])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["built"] is True
    assert result["row_count"] == 4
    assert result["country_count"] == 2

    assert out_path.exists()
    with open(out_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == CANON_HEADER
        rows = list(reader)
    assert len(rows) == 4
    assert {r["Country"].strip() for r in rows} == {"Australia", "Canada"}
    # The verbose real "Method (face to face, telephone, mixed, etc.)"
    # header must be matched and canonicalized to "Method".
    assert all(r["Method"] == "" for r in rows)  # fixture leaves Method blank


def test_shared_ead_csv_refuses_to_overwrite_by_default(sandbox):
    ead_wb = sandbox / "ead.xlsx"
    make_synthetic_ead_workbook(ead_wb)
    out_path = sandbox / "data" / "reference" / "ead_series_question_wording.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("Country,Series,Description,Question Type,Question Wording,Method\nOLD,X,,,,\n", encoding="utf-8")
    before = out_path.read_text(encoding="utf-8")

    proc = run_build_ead_csv(sandbox, ["--ead-workbook", str(ead_wb), "--output", str(out_path)])
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert result["built"] is False
    assert "already exists" in result["error"]
    assert out_path.read_text(encoding="utf-8") == before


def test_shared_ead_csv_overwrite_flag_replaces_it(sandbox):
    ead_wb = sandbox / "ead.xlsx"
    make_synthetic_ead_workbook(ead_wb)
    out_path = sandbox / "data" / "reference" / "ead_series_question_wording.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("Country,Series,Description,Question Type,Question Wording,Method\nOLD,X,,,,\n", encoding="utf-8")

    proc = run_build_ead_csv(sandbox, ["--ead-workbook", str(ead_wb), "--output", str(out_path), "--overwrite"])
    assert proc.returncode == 0, proc.stderr
    with open(out_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert all(r["Series"] != "X" for r in rows)
    assert len(rows) == 4


def test_shared_ead_csv_zero_rows_refuses_and_writes_nothing(sandbox):
    ead_wb = sandbox / "ead.xlsx"
    make_synthetic_ead_workbook(ead_wb, rows=[])
    out_path = sandbox / "data" / "reference" / "ead_series_question_wording.csv"
    proc = run_build_ead_csv(sandbox, ["--ead-workbook", str(ead_wb), "--output", str(out_path)])
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert result["built"] is False
    assert "Zero rows" in result["error"]
    assert not out_path.exists()


def test_shared_ead_csv_source_workbook_unchanged_before_after(sandbox):
    ead_wb = sandbox / "ead.xlsx"
    make_synthetic_ead_workbook(ead_wb)
    out_path = sandbox / "data" / "reference" / "ead_series_question_wording.csv"
    before_hash = sha256_of(ead_wb)

    proc = run_build_ead_csv(sandbox, ["--ead-workbook", str(ead_wb), "--output", str(out_path)])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    after_hash = sha256_of(ead_wb)
    assert before_hash == after_hash
    assert result["workbook_sha256"] == before_hash


# --- build_country_ead_snapshot.py: shared-CSV fallback --------------------

def test_country_ead_falls_back_to_shared_csv_when_workbook_missing(sandbox):
    make_country_workspace(sandbox, "canada")
    shared_csv = sandbox / "shared_ead.csv"
    with open(shared_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CANON_HEADER)
        writer.writeheader()
        writer.writerow({"Country": "Canada", "Series": "ABACUSJOBPM",
                          "Description": "Abacus Data Approve Job of Gov led by PM",
                          "Question Type": "Approval", "Question Wording": "Do you approve of...",
                          "Method": ""})
        writer.writerow({"Country": "Australia ", "Series": "NEWSPOLL",
                          "Description": "Prime Minister Satisfaction",
                          "Question Type": "Satisfaction", "Question Wording": "Do you approve of...",
                          "Method": ""})

    missing_workbook = sandbox / "does_not_exist.xlsx"
    proc = run_build_country_ead(sandbox, [
        "--country", "Canada",
        "--ead-workbook", str(missing_workbook),
        "--shared-ead-csv", str(shared_csv),
    ])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["built"] is True
    assert result["source"] == "shared_ead_reference_csv"
    assert result["row_count"] == 1

    out_path = sandbox / "countries" / "canada" / "data" / "canada_ead_series_question_wording.csv"
    with open(out_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == CANON_HEADER
        rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["Country"] == "Canada"


def test_country_ead_prefers_workbook_over_shared_csv_when_both_present(sandbox):
    make_country_workspace(sandbox, "australia")
    ead_wb = sandbox / "ead.xlsx"
    make_synthetic_ead_workbook(ead_wb)  # 3 real "Australia " rows

    shared_csv = sandbox / "shared_ead.csv"
    with open(shared_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CANON_HEADER)
        writer.writeheader()
        for _ in range(5):
            writer.writerow({"Country": "Australia", "Series": "FAKE", "Description": "",
                              "Question Type": "", "Question Wording": "", "Method": ""})

    proc = run_build_country_ead(sandbox, [
        "--country", "Australia", "--ead-workbook", str(ead_wb),
        "--shared-ead-csv", str(shared_csv),
    ])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["source"] == "ead_workbook"
    assert result["row_count"] == 3  # from the workbook, not the 5-row shared CSV


def test_country_ead_errors_clearly_when_neither_source_available(sandbox):
    make_country_workspace(sandbox, "canada")
    missing_workbook = sandbox / "does_not_exist.xlsx"
    missing_csv = sandbox / "also_does_not_exist.csv"
    proc = run_build_country_ead(sandbox, [
        "--country", "Canada",
        "--ead-workbook", str(missing_workbook),
        "--shared-ead-csv", str(missing_csv),
    ])
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert result["built"] is False
    assert "Neither the EAD workbook" in result["error"]


def test_country_ead_shared_csv_fallback_zero_rows_refuses(sandbox):
    make_country_workspace(sandbox, "germany")
    shared_csv = sandbox / "shared_ead.csv"
    with open(shared_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CANON_HEADER)
        writer.writeheader()
        writer.writerow({"Country": "Canada", "Series": "X", "Description": "",
                          "Question Type": "", "Question Wording": "", "Method": ""})

    missing_workbook = sandbox / "does_not_exist.xlsx"
    proc = run_build_country_ead(sandbox, [
        "--country", "Germany",
        "--ead-workbook", str(missing_workbook),
        "--shared-ead-csv", str(shared_csv),
    ])
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert result["built"] is False
    assert "Zero rows" in result["error"]


# --- integration tests against the REAL authoritative EAD workbook/CSV -----

pytestmark_real_workbook = pytest.mark.skipif(
    not REAL_EAD_WORKBOOK.exists(),
    reason="real data/master/EAD Series and Question Wording.xlsx not present in this checkout (git-ignored, environment-dependent)",
)

pytestmark_real_shared_csv = pytest.mark.skipif(
    not REAL_SHARED_EAD_CSV.exists(),
    reason="tracked data/reference/ead_series_question_wording.csv not present in this checkout",
)


@pytestmark_real_workbook
def test_real_shared_ead_csv_rebuild_row_and_country_counts(sandbox):
    out_path = sandbox / "ead_series_question_wording.csv"
    proc = run_build_ead_csv(sandbox, ["--ead-workbook", str(REAL_EAD_WORKBOOK), "--output", str(out_path)])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["row_count"] == 1820
    assert result["country_count"] == 231
    assert result["country_row_counts"]["new zealand"] == 13
    with open(out_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == CANON_HEADER
        rows = list(reader)
    assert len(rows) == 1820


@pytestmark_real_shared_csv
def test_tracked_shared_ead_csv_row_count_and_columns():
    """The tracked data/reference/ead_series_question_wording.csv must
    keep its known shape - verifies it wasn't hand-edited or partially
    written."""
    with open(REAL_SHARED_EAD_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == CANON_HEADER
        rows = list(reader)
    assert len(rows) == 1820
    countries = {r["Country"].strip().casefold() for r in rows}
    assert "new zealand" in countries
    assert "canada" in countries
    assert "australia" in countries


@pytestmark_real_shared_csv
def test_real_new_zealand_ead_snapshot_buildable_from_shared_csv_alone(sandbox):
    """New Zealand's per-country EAD snapshot must be buildable from the
    tracked shared CSV even with no EAD workbook present at all - this is
    the whole point of the fallback."""
    slug = "new-zealand"
    make_country_workspace(sandbox, slug)
    missing_workbook = sandbox / "does_not_exist.xlsx"
    proc = run_build_country_ead(sandbox, [
        "--country", "New Zealand",
        "--ead-workbook", str(missing_workbook),
        "--shared-ead-csv", str(REAL_SHARED_EAD_CSV),
    ])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["source"] == "shared_ead_reference_csv"
    assert result["row_count"] == 13
    assert result["country_slug"] == slug

    out_path = sandbox / "countries" / slug / "data" / "{}_ead_series_question_wording.csv".format(slug)
    with open(out_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == CANON_HEADER
        rows = list(reader)
    assert len(rows) == 13
    assert all(r["Country"].strip().casefold() == "new zealand" for r in rows)
