"""Tests for python/build_country_assignment_snapshot.py - the
maintainer/build-time tool that produces the tracked, student-facing
countries/<country>/data/<country>_assignment1_approved.csv and
..._review.csv files from a country's real local pipeline outputs.

Guards against inventing/transcribing values by hand: every APPROVED row
must be copied verbatim, every REVIEW row's "Validation Reason" must be
joined deterministically from the real audit-schema REVIEW file (never
left blank/guessed unless the source truly cannot be matched, in which
case the whole build fails loudly rather than silently guessing).
"""

import csv
import json
import subprocess
import sys

from .conftest import REPO_ROOT

SCRIPT = REPO_ROOT / "python" / "build_country_assignment_snapshot.py"


def run_cli(args):
    cmd = [sys.executable, str(SCRIPT)] + args
    return subprocess.run(cmd, capture_output=True, text=True)


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def make_workspace(tmp_path):
    approved_input = tmp_path / "data" / "processed" / "testland_pm_approval_main.csv"
    review_input = tmp_path / "data" / "processed" / "testland_pm_approval_review.csv"
    review_audit_input = tmp_path / "data" / "processed" / "testland_assignment1" / "testland_pm_review.csv"

    write_csv(approved_input, ["Date", "Approval", "Prime Minister", "Party", "Series", "Source", "Status"], [
        {"Date": "1/1/2026", "Approval": "50", "Prime Minister": "Test Leader", "Party": "Test Party",
         "Series": "TESTPOLL", "Source": "https://example.test/poll-1", "Status": "APPROVED"},
        {"Date": "2/1/2026", "Approval": "52", "Prime Minister": "Test Leader", "Party": "Test Party",
         "Series": "TESTPOLL", "Source": "https://example.test/poll-2", "Status": "APPROVED"},
    ])
    write_csv(review_input, ["Date", "Approval", "Prime Minister", "Party", "Series", "Source", "Status"], [
        {"Date": "3/1/2026", "Approval": "55", "Prime Minister": "Test Leader", "Party": "Test Party",
         "Series": "TESTPOLL", "Source": "https://example.test/poll-3", "Status": "REVIEW"},
    ])
    write_csv(
        review_audit_input,
        ["record_id", "series", "fieldwork_date_normalized", "executive_name", "sample_size",
         "positive", "neutral", "negative", "source_url", "final_url", "validation_status",
         "validation_reason", "validation_flags"],
        [
            {"record_id": "abc123", "series": "TESTPOLL", "fieldwork_date_normalized": "3/1/2026",
             "executive_name": "Test Leader", "sample_size": "1000", "positive": "55", "neutral": "",
             "negative": "", "source_url": "https://example.test/poll-3", "final_url": "https://example.test/poll-3",
             "validation_status": "REVIEW", "validation_reason": "Flagged for human review: ['TEST_FLAG']",
             "validation_flags": '["TEST_FLAG"]'},
        ],
    )
    return {
        "approved_input": approved_input,
        "review_input": review_input,
        "review_audit_input": review_audit_input,
        "approved_output": tmp_path / "countries" / "testland" / "data" / "testland_assignment1_approved.csv",
        "review_output": tmp_path / "countries" / "testland" / "data" / "testland_assignment1_review.csv",
    }


def test_builds_approved_and_review_with_matched_reasons(tmp_path):
    paths = make_workspace(tmp_path)
    result = run_cli([
        "--country", "Testland",
        "--approved-input", str(paths["approved_input"]),
        "--review-input", str(paths["review_input"]),
        "--review-audit-input", str(paths["review_audit_input"]),
        "--approved-output", str(paths["approved_output"]),
        "--review-output", str(paths["review_output"]),
    ])
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["approved_row_count"] == 2
    assert summary["review_row_count"] == 1
    assert summary["review_reasons_matched"] == 1

    with open(paths["approved_output"], newline="", encoding="utf-8") as f:
        approved_rows = list(csv.DictReader(f))
    assert len(approved_rows) == 2
    assert approved_rows[0]["Source"] == "https://example.test/poll-1"
    assert set(approved_rows[0].keys()) == {"Date", "Approval", "Prime Minister", "Party", "Series", "Source", "Status"}

    with open(paths["review_output"], newline="", encoding="utf-8") as f:
        review_rows = list(csv.DictReader(f))
    assert len(review_rows) == 1
    assert review_rows[0]["Validation Reason"] == "Flagged for human review: ['TEST_FLAG']"
    assert review_rows[0]["Status"] == "REVIEW"


def test_unmatched_review_source_fails_loudly_instead_of_inventing(tmp_path):
    paths = make_workspace(tmp_path)
    # Change the review row's Source so it can no longer be matched to the
    # audit file's source_url/final_url.
    write_csv(paths["review_input"], ["Date", "Approval", "Prime Minister", "Party", "Series", "Source", "Status"], [
        {"Date": "3/1/2026", "Approval": "55", "Prime Minister": "Test Leader", "Party": "Test Party",
         "Series": "TESTPOLL", "Source": "https://example.test/no-matching-audit-row", "Status": "REVIEW"},
    ])
    result = run_cli([
        "--country", "Testland",
        "--approved-input", str(paths["approved_input"]),
        "--review-input", str(paths["review_input"]),
        "--review-audit-input", str(paths["review_audit_input"]),
        "--approved-output", str(paths["approved_output"]),
        "--review-output", str(paths["review_output"]),
    ])
    assert result.returncode != 0
    assert "ERROR" in result.stderr
    assert "Could not find a matching validation reason" in result.stderr
    assert not paths["approved_output"].exists()
    assert not paths["review_output"].exists()


def test_non_approved_row_in_approved_input_fails_loudly(tmp_path):
    paths = make_workspace(tmp_path)
    write_csv(paths["approved_input"], ["Date", "Approval", "Prime Minister", "Party", "Series", "Source", "Status"], [
        {"Date": "1/1/2026", "Approval": "50", "Prime Minister": "Test Leader", "Party": "Test Party",
         "Series": "TESTPOLL", "Source": "https://example.test/poll-1", "Status": "REVIEW"},
    ])
    result = run_cli([
        "--country", "Testland",
        "--approved-input", str(paths["approved_input"]),
        "--review-input", str(paths["review_input"]),
        "--review-audit-input", str(paths["review_audit_input"]),
        "--approved-output", str(paths["approved_output"]),
        "--review-output", str(paths["review_output"]),
    ])
    assert result.returncode != 0
    assert "must be APPROVED-only" in result.stderr


def test_real_canada_tracked_files_match_row_counts():
    """Sanity-check the actual tracked Canada snapshot files, read only."""
    approved = REPO_ROOT / "countries" / "canada" / "data" / "canada_assignment1_approved.csv"
    review = REPO_ROOT / "countries" / "canada" / "data" / "canada_assignment1_review.csv"
    if not approved.exists() or not review.exists():
        return
    with open(approved, newline="", encoding="utf-8") as f:
        approved_rows = list(csv.DictReader(f))
    with open(review, newline="", encoding="utf-8") as f:
        review_rows = list(csv.DictReader(f))
    assert len(approved_rows) == 29
    assert all(r["Status"] == "APPROVED" for r in approved_rows)
    assert len(review_rows) == 10
    assert all(r["Status"] == "REVIEW" for r in review_rows)
    assert all(r["Validation Reason"].strip() for r in review_rows)
