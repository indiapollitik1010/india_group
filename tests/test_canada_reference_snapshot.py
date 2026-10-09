"""Content regression tests for the tracked Canada reference snapshot
(countries/canada/data/canada_reference_snapshot.csv).

This is a small, read-only export of ONLY the ORIGINAL master workbook's
existing Canada rows - it exists so a fresh student workspace can build
a local reference index without the production master workbook (see
python/check_assignment_preflight.py's COUNTRY_SNAPSHOT_BUILDABLE state
and python/build_reference_index.py's CSV input support).

These tests read the real, tracked snapshot file directly - never the
production master workbook, never the Canada Assignment 1 processed
workbook copy - and never write anywhere. If the snapshot file has not
been added to this checkout yet, every test here is skipped rather than
failing the whole suite, since the file is a deliberate, reviewable
addition to the repo rather than something any test/build step
generates on the fly.
"""

import csv
import hashlib
import json

import pytest

from .conftest import REPO_ROOT, run_script

SNAPSHOT_PATH = REPO_ROOT / "countries" / "canada" / "data" / "canada_reference_snapshot.csv"

EXPECTED_COLUMNS = [
    "Series", "Date", "Total Count", "Positive", "Neutral", "Negative", "Source", "Country",
]

# The 29 Canada Assignment 1 observations that were written ONLY to the
# processed workbook copy (data/processed/canada_assignment1/...), never
# to the real production master workbook. Identified by
# (Series, Date-prefix, Positive, Negative) - the same key used to
# dedupe them against the original master when that assignment ran.
# None of these may appear in a snapshot exported from the ORIGINAL
# master state.
ASSIGNMENT1_ONLY_OBSERVATIONS = {
    ("ANGUSREID", "2026-04-17", "59", "33"),
    ("ANGUSREID", "2026-04-20", "58", "35"),
    ("LIAISON", "2026-03-21", "64", "32"),
    ("LIAISON", "2026-05-02", "60", "32"),
    ("LIAISON", "2026-05-09", "58", "34"),
    ("LIAISON", "2026-05-16", "56", ""),
    ("LIAISON", "2026-05-23", "59", "35"),
    ("LIAISON", "2026-05-30", "57", "38"),
    ("LIAISON", "2026-06-06", "55", "39"),
    ("LIAISON", "2026-06-13", "57", "37"),
    ("LIAISON", "2026-06-20", "57", "36"),
    ("LIAISON", "2026-06-27", "58", "36"),
    ("LIAISON", "2026-07-04", "58", "35"),
    ("LIAISON", "2026-07-11", "56", "36"),
    ("LIAISON", "2026-07-18", "57", "35"),
    ("LIAISON", "2026-07-25", "56", "35"),
    ("LIAISON", "2026-08-01", "57", "34"),
    ("LIAISON", "2026-08-08", "57", "33"),
    ("LEGER", "2025-10-05", "47", "41"),
    ("LEGER", "2025-11-30", "51", "38"),
    ("LEGER", "2026-03-02", "61", "31"),
    ("LEGER", "2026-04-26", "59", "33"),
    ("LEGER", "2026-06-01", "56", "34"),
    ("LEGER", "2026-08-03", "55", ""),
    ("IPSOS", "2026-02-26", "58", "33"),
    ("RESEARCHCO", "2025-09-12", "56", ""),
    ("RESEARCHCO", "2026-02-06", "55", ""),
    ("RESEARCHCO", "2026-05-08", "56", ""),
    ("RESEARCHCO", "2026-08-07", "59", ""),
}


def _read_snapshot_rows():
    with open(SNAPSHOT_PATH, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _numeric_key(value):
    """Normalizes "64.0" / "64" / "" to a comparable string ("64" / "")
    for matching against ASSIGNMENT1_ONLY_OBSERVATIONS, since the CSV may
    store whole numbers as floats (e.g. openpyxl round-tripping)."""
    value = (value or "").strip()
    if not value:
        return ""
    try:
        f = float(value)
        return str(int(f)) if f.is_integer() else str(f)
    except ValueError:
        return value


pytestmark = pytest.mark.skipif(
    not SNAPSHOT_PATH.exists(),
    reason="countries/canada/data/canada_reference_snapshot.csv not present in this checkout",
)


def test_snapshot_has_exactly_the_8_required_columns():
    rows = _read_snapshot_rows()
    assert rows, "snapshot must not be empty"
    assert list(rows[0].keys()) == EXPECTED_COLUMNS


def test_snapshot_contains_canada_only():
    rows = _read_snapshot_rows()
    countries = {row["Country"] for row in rows}
    assert countries == {"Canada"}


def test_snapshot_has_no_unnamed_columns():
    with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
        header = f.readline().strip().split(",")
    assert not any(col.strip().lower().startswith("unnamed") for col in header)


def test_snapshot_does_not_contain_assignment1_processed_only_observations():
    rows = _read_snapshot_rows()
    present = set()
    for row in rows:
        date_prefix = (row["Date"] or "").split(" ")[0]
        key = (row["Series"], date_prefix, _numeric_key(row["Positive"]), _numeric_key(row["Negative"]))
        if key in ASSIGNMENT1_ONLY_OBSERVATIONS:
            present.add(key)
    assert not present, (
        "snapshot must reflect only the ORIGINAL master state - found "
        "Assignment-1-processed-only observation(s): {}".format(present)
    )


def test_snapshot_row_count_matches_original_master_canada_count():
    """Regression pin: at generation time, the original master workbook
    had exactly 1444 Canada rows (confirmed via the Canada Assignment 1
    safety baseline in the same session this snapshot was exported).
    This is a point-in-time snapshot (see countries/canada/data/README.md)
    - if the master's Canada data is later re-exported, this number is
    expected to change and this pin should be updated deliberately, not
    silently."""
    rows = _read_snapshot_rows()
    assert len(rows) == 1444


REAL_MASTER_WORKBOOK = REPO_ROOT / "data" / "master" / "pollitik_master.xlsx"


@pytest.mark.skipif(
    not REAL_MASTER_WORKBOOK.exists(),
    reason="data/master/pollitik_master.xlsx not present in this checkout (git-ignored, environment-dependent)",
)
def test_building_index_from_snapshot_never_touches_production_master(sandbox):
    """The snapshot-build path (python/build_reference_index.py given a
    CSV) must never read or write the real production master workbook -
    it only ever needs the CSV. This hashes the REAL repo's master
    workbook (never the sandbox's) before and after running a CSV-based
    build entirely inside an isolated CLAUDE_PROJECT_DIR sandbox."""
    def sha256_of(path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            h.update(f.read())
        return h.hexdigest()

    before = sha256_of(REAL_MASTER_WORKBOOK)

    sandbox_snapshot = sandbox / "canada_reference_snapshot.csv"
    sandbox_snapshot.write_text(
        "Series,Date,Total Count,Positive,Neutral,Negative,Source,Country\n"
        "LIAISON,3/21/2026,1000,64,,32,https://example.test/liaison-1,Canada\n",
        encoding="utf-8",
    )
    build_proc = run_script(
        "build_reference_index.py", sandbox,
        args=["--workbook", str(sandbox_snapshot), "--index", str(sandbox / "data" / "reference_index.duckdb")],
    )
    assert build_proc.returncode == 0, build_proc.stderr
    assert json.loads(build_proc.stdout)["built"] is True

    after = sha256_of(REAL_MASTER_WORKBOOK)
    assert after == before, "the real production master workbook must never be touched by a CSV-snapshot index build"
