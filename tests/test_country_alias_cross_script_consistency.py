"""Regression tests proving the country-alias/slug fix: every
country-workspace/pipeline script must derive the SAME
countries/<slug>/ folder for the same student-typed country name, via
the one centralized resolver in pollitik_common.py
(resolve_country_input / canonical_country_slug), never a
reimplementation.

This is exactly the bug class found in the pre-merge review: before this
fix, init_country_workspace.py created countries/uk/ for "UK" while
build_country_reference_snapshot.py looked for countries/united-kingdom/
- an unrecoverable dead end for a student. These tests exercise each
fixed script's real entry-point function directly (not just the shared
resolver in isolation) against a shared sandbox, chaining them the way a
real student workflow would (init -> preflight -> snapshot -> EAD ->
coverage), so a regression in any ONE script's wiring is caught here.
"""

import csv
import json
import os
import sys

import openpyxl
import pytest

from .conftest import REPO_ROOT, run_script

sys.path.insert(0, str(REPO_ROOT / "python"))
import init_country_workspace as icw  # noqa: E402
import check_assignment_preflight as cap  # noqa: E402
import build_country_reference_snapshot as bcrs  # noqa: E402
import build_country_ead_snapshot as bces  # noqa: E402
import resolve_assignment_dataset as rad  # noqa: E402
import report_country_ead_coverage as rcec  # noqa: E402

REF_HEADER = ["Series", "Date", "Total Count", "Positive", "Neutral", "Negative", "Source", "Country"]
EAD_HEADER = ["Country", "Series", "Description", "Question Type", "Question Wording", "Method"]

# (alias input, expected canonical slug, expected resolved Master Country value)
ALIAS_CASES = [
    ("UK", "united-kingdom", "United Kingdom"),
    ("USA", "united-states", "United States"),
    ("South-Korea", "south-korea", "South Korea"),
    ("France President", "france-president", "France_Pres"),
    ("France Prime Minister", "france-prime-minister", "France_PM"),
]


def _write_shared_reference_csv(path, country):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REF_HEADER)
        writer.writeheader()
        writer.writerow({"Series": "X", "Date": "2020-01-01", "Total Count": "1000",
                          "Positive": "50", "Neutral": "", "Negative": "40",
                          "Source": "https://example", "Country": country})


def _write_shared_ead_csv(path, country):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=EAD_HEADER)
        writer.writeheader()
        writer.writerow({"Country": country, "Series": "X", "Description": "d",
                          "Question Type": "Approval", "Question Wording": "Do you approve...",
                          "Method": ""})


def _write_ead_workbook(path, country):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["Country", "Series", "Description", "Question Type", "Question Wording",
               "Method (face to face, telephone, mixed, etc.)"])
    ws.append([country, "X", "d", "Approval", "Do you approve...", None])
    wb.save(path)


@pytest.mark.parametrize("alias,expected_slug,expected_resolved", ALIAS_CASES)
def test_alias_resolves_to_same_slug_across_the_whole_pipeline(alias, expected_slug, expected_resolved, tmp_path):
    sandbox = str(tmp_path)

    # 1. init_country_workspace.py - the documented entry point.
    result_init = icw.init_country_workspace(alias, project_dir=sandbox)
    assert result_init["created"] is True, result_init
    assert result_init["country_slug"] == expected_slug
    assert result_init["resolved_country"] == expected_resolved

    # 2. check_assignment_preflight.py - must look at the SAME folder
    #    init just created, not a different one.
    result_preflight = cap.check(alias, project_dir=sandbox)
    assert result_preflight["country_slug"] == expected_slug
    assert result_preflight["resolved_country"] == expected_resolved
    assert result_preflight["country_agents_md_exists"] is True
    assert result_preflight["country_agents_md_path"] == os.path.join(
        sandbox, "countries", expected_slug, "AGENTS.md"
    )

    # 3. build_country_reference_snapshot.py - shared-CSV fallback only,
    #    no Excel workbook, exactly the real fresh-clone path.
    shared_ref_csv = tmp_path / "shared_reference.csv"
    _write_shared_reference_csv(shared_ref_csv, expected_resolved)
    result_ref = bcrs.build(
        alias, str(tmp_path / "does_not_exist.xlsx"), project_dir=sandbox,
        shared_reference_csv_path=str(shared_ref_csv),
    )
    assert result_ref["country_slug"] == expected_slug
    assert result_ref["resolved_country"] == expected_resolved
    assert result_ref["row_count"] == 1
    assert result_ref["source"] == "shared_reference_csv"

    # 4. build_country_ead_snapshot.py - same pattern.
    shared_ead_csv = tmp_path / "shared_ead.csv"
    _write_shared_ead_csv(shared_ead_csv, expected_resolved)
    result_ead = bces.build(
        alias, project_dir=sandbox, ead_workbook_path=str(tmp_path / "does_not_exist.xlsx"),
        shared_ead_csv_path=str(shared_ead_csv),
    )
    assert result_ead["country_slug"] == expected_slug
    assert result_ead["resolved_country"] == expected_resolved
    assert result_ead["row_count"] == 1
    assert result_ead["source"] == "shared_ead_reference_csv"

    # 5. resolve_assignment_dataset.py - must resolve to the same slug
    #    even though neither a local nor tracked assignment result exists
    #    yet in this sandbox.
    result_resolve = rad.resolve(alias, "approved", project_dir=sandbox)
    assert result_resolve["country_slug"] == expected_slug

    # 6. report_country_ead_coverage.py - uses the snapshot build_country_
    #    reference_snapshot.py just wrote, plus a tiny real EAD workbook.
    ead_workbook = tmp_path / "ead.xlsx"
    _write_ead_workbook(ead_workbook, expected_resolved)
    result_coverage = rcec.build_report(
        alias, project_dir=sandbox,
        snapshot_path=result_ref["output_path"],
        ead_path=str(ead_workbook),
    )
    assert result_coverage["country_slug"] == expected_slug
    assert result_coverage["resolved_country"] == expected_resolved


# --- plain "France" must fail safely and identically everywhere ------------

def test_bare_france_ambiguous_across_the_whole_pipeline(tmp_path):
    """Every script's own real entry-point function must refuse bare
    "France" - each wraps the shared pc.AmbiguousCountryError in its own
    established error type (matching how it already reports every other
    setup problem), never lets it propagate as a raw/unexpected
    exception, and never silently proceeds."""
    sandbox = str(tmp_path)

    with pytest.raises(icw.InitError) as exc_info:
        icw.init_country_workspace("France", project_dir=sandbox)
    assert "France_Pres" in str(exc_info.value)
    assert "France_PM" in str(exc_info.value)
    assert not (tmp_path / "countries" / "france").exists()

    result_preflight = cap.check("France", project_dir=sandbox)
    assert result_preflight["SAFE_TO_RESEARCH"] is False
    assert "France_Pres" in result_preflight["reason"]
    assert "France_PM" in result_preflight["reason"]

    with pytest.raises(bcrs.SnapshotBuildError) as exc_info:
        bcrs.build("France", str(tmp_path / "does_not_exist.xlsx"), project_dir=sandbox)
    assert "France_Pres" in str(exc_info.value)
    assert "France_PM" in str(exc_info.value)

    with pytest.raises(bces.EadSnapshotBuildError) as exc_info:
        bces.build("France", project_dir=sandbox)
    assert "France_Pres" in str(exc_info.value)
    assert "France_PM" in str(exc_info.value)

    result_resolve = rad.resolve("France", "approved", project_dir=sandbox)
    assert result_resolve["resolved"] is False
    assert "France_Pres" in result_resolve["reason"]
    assert "France_PM" in result_resolve["reason"]

    with pytest.raises(rcec.ReportError) as exc_info:
        rcec.build_report("France", project_dir=sandbox)
    assert "France_Pres" in str(exc_info.value)
    assert "France_PM" in str(exc_info.value)


def test_bare_france_ambiguous_via_cli_subprocess(sandbox):
    """Same check via the real CLI entry points (subprocess), proving
    the ambiguity is reported as a clean JSON error/non-zero exit code -
    never an unhandled traceback - for every script with a CLI."""
    for script, extra_args in [
        ("init_country_workspace.py", []),
        ("check_assignment_preflight.py", []),
        ("build_country_reference_snapshot.py", ["--workbook", str(sandbox / "does_not_exist.xlsx")]),
        ("build_country_ead_snapshot.py", ["--ead-workbook", str(sandbox / "does_not_exist.xlsx")]),
        ("build_country_assignment_snapshot.py", ["--project-dir", str(sandbox)]),
    ]:
        proc = run_script(script, sandbox, args=["--country", "France", *extra_args])
        assert proc.returncode != 0, "{} unexpectedly succeeded for bare 'France'".format(script)
        combined = (proc.stdout or "") + (proc.stderr or "")
        assert "France_Pres" in combined, "{}: {}".format(script, combined)
        assert "France_PM" in combined, "{}: {}".format(script, combined)

    proc = run_script("resolve_assignment_dataset.py", sandbox, args=["--country", "France", "--purpose", "approved"])
    assert proc.returncode != 0
    result = json.loads(proc.stdout)
    assert result["resolved"] is False
    assert "France_Pres" in result["reason"]
    assert "France_PM" in result["reason"]
