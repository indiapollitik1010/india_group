"""Regression coverage for python/check_assignment_preflight.py.

Bug this guards against: a fresh student workspace (e.g. a new Codex
sandbox) can contain the repo code and a country's AGENTS.md without
containing data/reference_index.duckdb, data/master/pollitik_master.xlsx,
or any local staging history. In that state nothing stopped the student
workflow from starting web research/staging with no real duplicate check
behind it - python/reference_lookup.py silently reports
found_index=false and zero rows when the index is missing, which looks
identical to "checked, no duplicates" if you don't know to look for it.

These tests run the real python/check_assignment_preflight.py as a
subprocess against isolated sandbox directories (never the real repo's
data/master/, data/staging/, or config/), exactly the way
service/agent.py and the other tests in this suite invoke pipeline
scripts. Nothing here fetches the web, stages a candidate, or writes
production data.
"""

import json
import subprocess
import sys
from pathlib import Path

from .conftest import REPO_ROOT, run_script


def write_country_index(index_path, country_display, series="TESTSERIES"):
    """Writes a real, minimal, valid duckdb index at index_path whose
    'master' table has one row with a Country value of `country_display`
    - the same shape build_reference_index.py produces (verbatim source
    header names, a _index_metadata table). Used instead of an empty/
    placeholder byte string now that check_assignment_preflight.py
    actually opens and queries the index to confirm it covers the
    requested country (pc.reference_index_contains_country) - a 0-byte
    file is not a valid duckdb database and would fail to open."""
    import duckdb

    index_path = Path(index_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    if index_path.exists():
        index_path.unlink()
    con = duckdb.connect(str(index_path))
    try:
        con.execute(
            'CREATE TABLE master AS SELECT ? AS "Series", ? AS "Country"',
            [series, country_display],
        )
        con.execute(
            "CREATE TABLE _index_metadata AS SELECT 'test-fixture' AS workbook_path, "
            "'2026-01-01T00:00:00Z' AS built_at, 0.0 AS workbook_mtime, 'csv' AS source_kind"
        )
    finally:
        con.close()
    return index_path


def make_safe_sandbox(sandbox, country_slug="testcountry", country_display=None):
    """Populates `sandbox` (from the shared `sandbox` fixture) with
    everything the preflight check requires for SAFE_TO_RESEARCH=true:
    root AGENTS.md, a country AGENTS.md, a non-empty approved-domain list
    (the sandbox fixture already writes one), a REAL reference index that
    actually covers `country_display` (see write_country_index - required
    now that preflight verifies index content, not just existence), and
    a placeholder master workbook (still existence-only: preflight never
    opens/parses the workbook itself)."""
    country_display = country_display or "TestCountry"
    (sandbox / "AGENTS.md").write_text("# repo map (test fixture)\n", encoding="utf-8")
    country_dir = sandbox / "countries" / country_slug
    country_dir.mkdir(parents=True, exist_ok=True)
    (country_dir / "AGENTS.md").write_text("# country rules (test fixture)\n", encoding="utf-8")
    write_country_index(sandbox / "data" / "reference_index.duckdb", country_display)
    (sandbox / "data" / "master" / "pollitik_master.xlsx").write_bytes(b"")
    return sandbox


def run_preflight(sandbox, country="TestCountry", extra_args=None):
    proc = run_script(
        "check_assignment_preflight.py", sandbox,
        args=["--country", country, *(extra_args or [])],
    )
    return proc, json.loads(proc.stdout)


def write_country_snapshot(sandbox, country_slug="testcountry"):
    """The minimal shape of a real country reference-snapshot CSV (e.g.
    countries/canada/data/canada_reference_snapshot.csv) - exactly the 8
    columns, one row is enough since preflight only checks existence."""
    snapshot_dir = sandbox / "countries" / country_slug / "data"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / "{}_reference_snapshot.csv".format(country_slug)
    snapshot_path.write_text(
        "Series,Date,Total Count,Positive,Neutral,Negative,Source,Country\n"
        "LIAISON,3/21/2026,1000,64,,32,https://example.test/liaison-1,TestCountry\n",
        encoding="utf-8",
    )
    return snapshot_path


def test_index_present_workbook_present_is_safe(sandbox):
    make_safe_sandbox(sandbox)
    proc, result = run_preflight(sandbox)
    assert result["SAFE_TO_RESEARCH"] is True
    assert result["unsafe_reasons"] == []
    assert result["reference_index_exists"] is True
    assert result["master_workbook_exists"] is True
    assert result["reference_data_status"] == "REFERENCE_INDEX_PRESENT"
    assert proc.returncode == 0


def test_index_present_workbook_absent_is_safe(sandbox):
    make_safe_sandbox(sandbox)
    (sandbox / "data" / "master" / "pollitik_master.xlsx").unlink()
    proc, result = run_preflight(sandbox)
    assert result["SAFE_TO_RESEARCH"] is True
    assert result["unsafe_reasons"] == []
    assert result["reference_index_exists"] is True
    assert result["master_workbook_exists"] is False
    assert result["reference_data_status"] == "REFERENCE_INDEX_PRESENT"
    assert proc.returncode == 0


def test_both_reference_index_and_workbook_missing_is_unsafe(sandbox):
    make_safe_sandbox(sandbox)
    (sandbox / "data" / "reference_index.duckdb").unlink()
    (sandbox / "data" / "master" / "pollitik_master.xlsx").unlink()
    proc, result = run_preflight(sandbox)
    assert result["SAFE_TO_RESEARCH"] is False
    assert result["reference_index_exists"] is False
    assert result["master_workbook_exists"] is False
    assert result["reference_data_status"] == "NO_REFERENCE_DATA"
    assert any("reference index" in r and "master workbook" in r for r in result["unsafe_reasons"])
    assert result["reason"] is not None
    assert "STOP" in result["instruction"]
    assert proc.returncode == 1


def test_country_snapshot_present_no_index_reports_snapshot_buildable_and_unsafe(sandbox):
    """The core new behavior: a fresh workspace that has the tracked
    country snapshot but no local index yet must NOT be treated as
    SAFE_TO_RESEARCH - the snapshot's mere presence is not a substitute
    for an actually-built index."""
    make_safe_sandbox(sandbox)
    (sandbox / "data" / "reference_index.duckdb").unlink()
    (sandbox / "data" / "master" / "pollitik_master.xlsx").unlink()
    snapshot_path = write_country_snapshot(sandbox)

    proc, result = run_preflight(sandbox)
    assert result["country_snapshot_exists"] is True
    assert result["reference_index_exists"] is False
    assert result["reference_data_status"] == "COUNTRY_SNAPSHOT_BUILDABLE"
    assert result["SAFE_TO_RESEARCH"] is False, (
        "a tracked snapshot alone (no index built yet) must not be safe"
    )
    assert result["suggested_index_build_command"] is not None
    assert str(snapshot_path) in result["suggested_index_build_command"]
    assert any("has not been built" in r for r in result["unsafe_reasons"])
    assert proc.returncode == 1


def test_building_index_from_snapshot_then_preflight_is_safe(sandbox):
    """The full loop item 3 of the architecture describes: preflight ->
    COUNTRY_SNAPSHOT_BUILDABLE -> build the index from the snapshot ->
    preflight again -> SAFE_TO_RESEARCH=true."""
    make_safe_sandbox(sandbox)
    index_path = sandbox / "data" / "reference_index.duckdb"
    index_path.unlink()
    (sandbox / "data" / "master" / "pollitik_master.xlsx").unlink()
    snapshot_path = write_country_snapshot(sandbox)

    proc1, result1 = run_preflight(sandbox)
    assert result1["reference_data_status"] == "COUNTRY_SNAPSHOT_BUILDABLE"
    assert result1["SAFE_TO_RESEARCH"] is False

    build_proc = run_script(
        "build_reference_index.py", sandbox,
        args=["--workbook", str(snapshot_path), "--index", str(index_path)],
    )
    assert build_proc.returncode == 0, build_proc.stderr
    built = json.loads(build_proc.stdout)
    assert built["built"] is True
    assert index_path.exists()

    proc2, result2 = run_preflight(sandbox)
    assert result2["reference_index_exists"] is True
    assert result2["reference_data_status"] == "REFERENCE_INDEX_PRESENT"
    assert result2["SAFE_TO_RESEARCH"] is True
    assert result2["unsafe_reasons"] == []
    assert proc2.returncode == 0


def test_reference_index_present_but_covers_only_a_different_country_is_unsafe(sandbox):
    """The core stale-index regression guard: a reference index that
    genuinely exists on disk but was built for a DIFFERENT country (e.g.
    a leftover whole-master index from an earlier session, or another
    country's snapshot-built index) must never be silently accepted as
    reference data for THIS country just because the file is present."""
    make_safe_sandbox(sandbox)
    index_path = sandbox / "data" / "reference_index.duckdb"
    write_country_index(index_path, "SomeOtherCountry")
    (sandbox / "data" / "master" / "pollitik_master.xlsx").unlink()
    # Deliberately no country snapshot either, so the only candidate
    # reference data is the (unrelated) index.
    proc, result = run_preflight(sandbox)
    assert result["reference_index_exists"] is True
    assert result["reference_index_covers_country"] is False
    assert result["reference_index_stale_warning"] is not None
    assert "TestCountry" in result["reference_index_stale_warning"]
    assert result["reference_data_status"] == "NO_REFERENCE_DATA"
    assert result["SAFE_TO_RESEARCH"] is False
    assert any(r == result["reference_index_stale_warning"] for r in result["unsafe_reasons"])
    assert proc.returncode == 1


def test_stale_index_plus_country_snapshot_is_still_country_snapshot_buildable(sandbox):
    """A stale (wrong-country) index sitting next to a genuine tracked
    snapshot for THIS country must not short-circuit the normal
    COUNTRY_SNAPSHOT_BUILDABLE -> build -> re-check loop, and the stale
    fact should be visible in unsafe_reasons alongside the "not built
    yet" reason."""
    make_safe_sandbox(sandbox)
    index_path = sandbox / "data" / "reference_index.duckdb"
    write_country_index(index_path, "SomeOtherCountry")
    (sandbox / "data" / "master" / "pollitik_master.xlsx").unlink()
    write_country_snapshot(sandbox)

    proc, result = run_preflight(sandbox)
    assert result["reference_index_covers_country"] is False
    assert result["reference_data_status"] == "COUNTRY_SNAPSHOT_BUILDABLE"
    assert result["SAFE_TO_RESEARCH"] is False
    assert len(result["unsafe_reasons"]) == 2
    assert proc.returncode == 1


def test_stale_index_with_master_workbook_present_stays_safe_but_flagged(sandbox):
    """MASTER_ONLY_INDEX_BUILDABLE is deliberately still SAFE_TO_RESEARCH
    (the master workbook itself is authoritative even with a wrong/stale
    local index cached) - but the stale index must still be surfaced,
    just not as an unsafe_reasons entry that would flip safety."""
    make_safe_sandbox(sandbox)
    index_path = sandbox / "data" / "reference_index.duckdb"
    write_country_index(index_path, "SomeOtherCountry")
    # master_workbook already present from make_safe_sandbox; no country
    # snapshot written, so this falls through to MASTER_ONLY_INDEX_BUILDABLE.
    proc, result = run_preflight(sandbox)
    assert result["reference_index_covers_country"] is False
    assert result["reference_index_stale_warning"] is not None
    assert result["reference_data_status"] == "MASTER_ONLY_INDEX_BUILDABLE"
    assert result["SAFE_TO_RESEARCH"] is True
    assert result["unsafe_reasons"] == []
    assert result["reference_index_stale_warning"] in result["reference_data_note"]
    assert proc.returncode == 0


def test_reference_index_covering_country_is_accepted_as_safe(sandbox):
    """The positive counterpart: an index that genuinely contains a row
    for the requested country (e.g. freshly built from that country's
    own tracked snapshot) is accepted exactly as before."""
    make_safe_sandbox(sandbox, country_display="TestCountry")
    proc, result = run_preflight(sandbox, country="TestCountry")
    assert result["reference_index_exists"] is True
    assert result["reference_index_covers_country"] is True
    assert result["reference_index_stale_warning"] is None
    assert result["reference_data_status"] == "REFERENCE_INDEX_PRESENT"
    assert result["SAFE_TO_RESEARCH"] is True
    assert proc.returncode == 0


def test_reference_index_covers_country_is_none_when_index_absent(sandbox):
    make_safe_sandbox(sandbox)
    (sandbox / "data" / "reference_index.duckdb").unlink()
    (sandbox / "data" / "master" / "pollitik_master.xlsx").unlink()
    proc, result = run_preflight(sandbox)
    assert result["reference_index_exists"] is False
    assert result["reference_index_covers_country"] is None
    assert result["reference_index_stale_warning"] is None


def test_no_snapshot_no_index_no_master_is_unsafe(sandbox):
    make_safe_sandbox(sandbox)
    (sandbox / "data" / "reference_index.duckdb").unlink()
    (sandbox / "data" / "master" / "pollitik_master.xlsx").unlink()
    # Deliberately do NOT write a country snapshot either.
    proc, result = run_preflight(sandbox)
    assert result["reference_index_exists"] is False
    assert result["master_workbook_exists"] is False
    assert result["country_snapshot_exists"] is False
    assert result["reference_data_status"] == "NO_REFERENCE_DATA"
    assert result["SAFE_TO_RESEARCH"] is False
    assert proc.returncode == 1


def test_empty_allowed_domain_list_is_unsafe(sandbox):
    make_safe_sandbox(sandbox)
    # Comments/blank lines only - zero usable domains, even though the
    # file itself exists.
    (sandbox / "config" / "allowed_domains.txt").write_text(
        "# nothing approved yet\n\n", encoding="utf-8"
    )
    proc, result = run_preflight(sandbox)
    assert result["allowed_domains_exists"] is True
    assert result["allowed_domains_usable_count"] == 0
    assert result["allowed_domains_ok"] is False
    assert result["SAFE_TO_RESEARCH"] is False
    assert any("approved-domain" in r.lower() or "allowed_domains" in r.lower()
               for r in result["unsafe_reasons"])
    assert proc.returncode == 1


def test_missing_allowed_domain_file_is_unsafe(sandbox):
    make_safe_sandbox(sandbox)
    (sandbox / "config" / "allowed_domains.txt").unlink()
    proc, result = run_preflight(sandbox)
    assert result["allowed_domains_exists"] is False
    assert result["allowed_domains_ok"] is False
    assert result["SAFE_TO_RESEARCH"] is False
    assert proc.returncode == 1


def test_empty_or_new_staging_file_alone_does_not_grant_safety(sandbox):
    """An empty/new staging file must never be treated as evidence that
    an observation is new, and must never make an otherwise-unsafe
    workspace SAFE_TO_RESEARCH on its own."""
    make_safe_sandbox(sandbox)
    (sandbox / "data" / "reference_index.duckdb").unlink()
    (sandbox / "data" / "master" / "pollitik_master.xlsx").unlink()
    # Freshly created, empty staging file - the exact "looks like it has
    # already been checked" trap this script exists to prevent.
    (sandbox / "data" / "staging" / "candidates.jsonl").write_text("", encoding="utf-8")

    proc, result = run_preflight(sandbox)
    assert result["staging_file_exists"] is True
    assert result["SAFE_TO_RESEARCH"] is False, (
        "an empty staging file must not make a workspace with no "
        "reference index and no master workbook look safe"
    )
    assert proc.returncode == 1

    # And the converse: a fully safe workspace stays safe even with no
    # staging file at all (its absence isn't held against it either).
    make_safe_sandbox(sandbox)
    (sandbox / "data" / "staging" / "candidates.jsonl").unlink()
    assert not (sandbox / "data" / "staging" / "candidates.jsonl").exists()
    proc2, result2 = run_preflight(sandbox)
    assert result2["staging_file_exists"] is False
    assert result2["SAFE_TO_RESEARCH"] is True


def test_country_agents_md_missing_is_unsafe(sandbox):
    make_safe_sandbox(sandbox)
    (sandbox / "countries" / "testcountry" / "AGENTS.md").unlink()
    proc, result = run_preflight(sandbox, country="TestCountry")
    assert result["country_agents_md_exists"] is False
    assert result["SAFE_TO_RESEARCH"] is False
    assert any("AGENTS.md" in r and "testcountry" in r for r in result["unsafe_reasons"])
    assert proc.returncode == 1


def test_country_argument_is_case_normalized_to_folder_slug(sandbox):
    make_safe_sandbox(sandbox, country_slug="canada", country_display="Canada")
    proc, result = run_preflight(sandbox, country="Canada")
    assert result["country_slug"] == "canada"
    assert result["country_agents_md_exists"] is True
    assert result["SAFE_TO_RESEARCH"] is True


def test_explicit_claude_project_dir_sandbox_behavior(tmp_path, sandbox):
    """Mirrors tests/test_project_root_resolution.py: an explicitly-set
    CLAUDE_PROJECT_DIR must win over the caller's cwd, and every path in
    the report must resolve under the sandbox, not the real repo -
    proving preflight honors the same override every other pipeline
    script does."""
    make_safe_sandbox(sandbox)
    outside_dir = tmp_path / "outside_repo_cwd"
    outside_dir.mkdir()

    import os
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "python" / "check_assignment_preflight.py"),
         "--country", "TestCountry"],
        cwd=str(outside_dir),
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(sandbox)},
        capture_output=True,
        text=True,
    )
    result = json.loads(proc.stdout)

    assert result["repo_root"] == str(sandbox)
    assert result["root_agents_md_path"].startswith(str(sandbox))
    assert result["country_agents_md_path"].startswith(str(sandbox))
    assert result["reference_index_path"].startswith(str(sandbox))
    assert result["master_workbook_path"].startswith(str(sandbox))
    # None of it silently fell back to the outside cwd or the real repo.
    assert not result["repo_root"].startswith(str(outside_dir))
    assert result["repo_root"] != str(REPO_ROOT)

    assert result["SAFE_TO_RESEARCH"] is True
    assert proc.returncode == 0


def test_repo_root_resolution_matches_real_repo_when_env_unset(tmp_path):
    """From a cwd outside the repo with CLAUDE_PROJECT_DIR unset, preflight
    must resolve to the real repo root (same fallback pollitik_common.py
    uses) - and the repo-committed files (root AGENTS.md, the country
    AGENTS.md, the non-empty approved-domain list) must be found there.
    Deliberately does NOT assert SAFE_TO_RESEARCH here: whether the real
    repo's data/master/pollitik_master.xlsx or data/reference_index.duckdb
    happen to exist locally is environment-dependent (both are
    git-ignored) and isn't what this test is checking."""
    import os
    outside_dir = tmp_path / "somewhere_else_entirely"
    outside_dir.mkdir()
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}

    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "python" / "check_assignment_preflight.py"),
         "--country", "Canada"],
        cwd=str(outside_dir),
        env=env,
        capture_output=True,
        text=True,
    )
    result = json.loads(proc.stdout)

    assert result["repo_root"] == str(REPO_ROOT)
    assert result["root_agents_md_exists"] is True
    assert result["country_agents_md_exists"] is True
    assert result["allowed_domains_ok"] is True
    assert result["reference_data_status"] in (
        "REFERENCE_INDEX_PRESENT", "COUNTRY_SNAPSHOT_BUILDABLE",
        "MASTER_ONLY_INDEX_BUILDABLE", "NO_REFERENCE_DATA",
    )
    assert isinstance(result["SAFE_TO_RESEARCH"], bool)
