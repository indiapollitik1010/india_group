"""Tests for python/resolve_assignment_dataset.py - the deterministic
result-precedence resolver for student-facing analysis/visualization.

Root cause this guards against: a fresh clone ships a tracked, frozen
worked-example result per country (countries/<country>/data/
<country>_assignment1_approved.csv / ..._review.csv) alongside the real,
gitignored pipeline outputs a student's own session may produce
(data/processed/<country>_pm_approval_main.csv / ..._review.csv). Which
one is "the" validated dataset for a given question must never be left
to model inference - see countries/canada/AGENTS.md and
docs/student_workflow.md.

These tests exercise the resolve() function directly against a tmp_path
sandbox of local/tracked file pairs (never the real repo's data), plus a
couple of CLI-level checks.
"""

import json
import os
import subprocess
import sys
import time

from .conftest import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "python"))
import resolve_assignment_dataset as rad  # noqa: E402

SCRIPT = REPO_ROOT / "python" / "resolve_assignment_dataset.py"


def run_cli(args, project_dir=None):
    cmd = [sys.executable, str(SCRIPT)] + args
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project_dir)} if project_dir else os.environ
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def touch(path, content="Date,Approval,Prime Minister,Party,Series,Source,Status\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# --------------------------------------------------------------------
# 1. Neither file exists: unresolved, clearly reported.
# --------------------------------------------------------------------

def test_neither_local_nor_tracked_exists_is_unresolved(tmp_path):
    local = tmp_path / "local.csv"
    tracked = tmp_path / "tracked.csv"
    result = rad.resolve("Testland", "approved", local_path=str(local), tracked_path=str(tracked))
    assert result["resolved"] is False
    assert result["resolved_path"] is None
    assert result["source"] is None


# --------------------------------------------------------------------
# 2. Only tracked exists (the fresh-clone case): tracked wins.
# --------------------------------------------------------------------

def test_fresh_clone_only_tracked_exists_uses_tracked(tmp_path):
    local = tmp_path / "local.csv"
    tracked = tmp_path / "tracked.csv"
    touch(tracked)
    result = rad.resolve("Testland", "approved", local_path=str(local), tracked_path=str(tracked))
    assert result["resolved"] is True
    assert result["source"] == "tracked_worked_example"
    assert result["resolved_path"] == str(tracked)


# --------------------------------------------------------------------
# 3. Only local exists: local wins.
# --------------------------------------------------------------------

def test_only_local_exists_uses_local(tmp_path):
    local = tmp_path / "local.csv"
    tracked = tmp_path / "tracked.csv"
    touch(local)
    result = rad.resolve("Testland", "approved", local_path=str(local), tracked_path=str(tracked))
    assert result["resolved"] is True
    assert result["source"] == "local_session_result"
    assert result["resolved_path"] == str(local)


# --------------------------------------------------------------------
# 4. Both exist, local is newer (this session produced a fresher result):
#    local wins.
# --------------------------------------------------------------------

def test_both_exist_newer_local_wins(tmp_path):
    local = tmp_path / "local.csv"
    tracked = tmp_path / "tracked.csv"
    touch(tracked)
    time.sleep(0.05)
    touch(local)  # written after tracked -> strictly newer mtime
    result = rad.resolve("Testland", "approved", local_path=str(local), tracked_path=str(tracked))
    assert result["resolved"] is True
    assert result["source"] == "local_session_result"
    assert result["resolved_path"] == str(local)


# --------------------------------------------------------------------
# 5. Both exist, tracked is newer or equal (stale/no-newer local): tracked
#    wins - this is the "never silently prefer a stale local artifact"
#    guarantee.
# --------------------------------------------------------------------

def test_both_exist_stale_local_falls_back_to_tracked(tmp_path):
    local = tmp_path / "local.csv"
    tracked = tmp_path / "tracked.csv"
    touch(local)
    time.sleep(0.05)
    touch(tracked)  # written after local -> strictly newer mtime
    result = rad.resolve("Testland", "approved", local_path=str(local), tracked_path=str(tracked))
    assert result["resolved"] is True
    assert result["source"] == "tracked_worked_example"
    assert result["resolved_path"] == str(tracked)


# --------------------------------------------------------------------
# 6. An empty (e.g. zero-byte, failed-write) local file is never treated
#    as a finalized result.
# --------------------------------------------------------------------

def test_empty_local_file_is_not_treated_as_finalized(tmp_path):
    local = tmp_path / "local.csv"
    tracked = tmp_path / "tracked.csv"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text("", encoding="utf-8")
    touch(tracked)
    result = rad.resolve("Testland", "approved", local_path=str(local), tracked_path=str(tracked))
    assert result["source"] == "tracked_worked_example"


# --------------------------------------------------------------------
# 7. purpose="review" never resolves to a reference-snapshot-shaped path;
#    the function has no code path that can return one at all (it only
#    ever compares the two paths it was given/computed from purpose).
# --------------------------------------------------------------------

def test_review_purpose_uses_review_paths_only(tmp_path):
    local = tmp_path / "x_pm_approval_review.csv"
    tracked = tmp_path / "x_assignment1_review.csv"
    touch(tracked)
    result = rad.resolve("Testland", "review", local_path=str(local), tracked_path=str(tracked))
    assert result["purpose"] == "review"
    assert "reference_snapshot" not in (result["resolved_path"] or "")
    assert "reference_snapshot" not in result["local_path"]
    assert "reference_snapshot" not in result["tracked_path"]


def test_invalid_purpose_rejected():
    import pytest
    with pytest.raises(ValueError):
        rad.resolve("Testland", "reference", local_path="a", tracked_path="b")


# --------------------------------------------------------------------
# 8. Default path construction matches the real Canada convention.
# --------------------------------------------------------------------

def test_default_paths_match_canada_convention(tmp_path):
    approved_local = rad.default_local_path(str(tmp_path), "canada", "approved")
    approved_tracked = rad.default_tracked_path(str(tmp_path), "canada", "approved")
    review_local = rad.default_local_path(str(tmp_path), "canada", "review")
    review_tracked = rad.default_tracked_path(str(tmp_path), "canada", "review")

    assert approved_local.endswith("data/processed/canada_pm_approval_main.csv".replace("/", __import__("os").sep))
    assert approved_tracked.endswith(
        "countries/canada/data/canada_assignment1_approved.csv".replace("/", __import__("os").sep)
    )
    assert review_local.endswith("data/processed/canada_pm_approval_review.csv".replace("/", __import__("os").sep))
    assert review_tracked.endswith(
        "countries/canada/data/canada_assignment1_review.csv".replace("/", __import__("os").sep)
    )


# --------------------------------------------------------------------
# 9. CLI smoke test against the real repo-resident Canada tracked file
#    (read-only; never writes anything).
# --------------------------------------------------------------------

def test_cli_resolves_real_canada_data_and_never_returns_reference_snapshot():
    """Sanity check against the real repo (read-only). Whether the local
    or tracked file wins depends on this dev workspace's current mtimes
    (not this test's concern - see the mtime-precedence tests above) but
    it must always resolve to *something*, and never to the reference
    snapshot path."""
    real_tracked = REPO_ROOT / "countries" / "canada" / "data" / "canada_assignment1_approved.csv"
    if not real_tracked.exists():
        return  # nothing to check yet
    result = run_cli(["--country", "Canada", "--purpose", "approved"], project_dir=REPO_ROOT)
    assert result.returncode in (0, 1)
    payload = json.loads(result.stdout)
    assert payload["resolved"] is True
    assert "reference_snapshot" not in payload["resolved_path"]
    assert payload["source"] in ("local_session_result", "tracked_worked_example")


def test_cli_unresolved_reports_clear_reason_and_nonzero_exit(tmp_path):
    result = run_cli([
        "--country", "Nowhereland", "--purpose", "approved",
        "--local-path", str(tmp_path / "missing_local.csv"),
        "--tracked-path", str(tmp_path / "missing_tracked.csv"),
    ])
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["resolved"] is False
    assert "does not exist" not in payload["reason"]  # phrased as "neither ... exists", not a traceback
    assert "Neither" in payload["reason"]
