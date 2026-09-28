"""Characterization tests for the *actual* filesystem/repository access
boundary around the tracked Canada Assignment 1 CSVs, as distinct from
the response-policy tests in tests/test_student_facing_docs.py.

Context (2026-08-25 student-data-access policy correction): a student's
own assignment data (their APPROVED/REVIEW results) is documented as
learning material, not secret data - see "Student data-access policy" in
docs/student_workflow.md and countries/canada/AGENTS.md. This file
exercises the one thing in this repo that IS deterministically enforced
- .claude/hooks/pollitik_guard.py, a PreToolUse hook - and shows exactly
what it does and does not cover for the two tracked assignment CSVs:

    countries/canada/data/canada_assignment1_approved.csv
    countries/canada/data/canada_assignment1_review.csv

Under the current policy this is *intended* behavior, not a gap to
close: a student reading their own tracked assignment CSV directly (via
the Read tool, `cat`, or an editor) is exactly as acceptable as Codex
handing it to them on request, so the hook correctly has no opinion on
it. What the hook must keep blocking, unconditionally, is writing to the
production workbook and fetching outside the approved-domain allow-list
- the last two tests below prove those protections are unaffected by
the 2026-08-25 policy correction. If a future change narrows what
students may access, the corresponding assertions here would need to
flip deliberately - that is the intended signal, not a regression to
silence.
"""

from .conftest import REPO_ROOT, run_hook

APPROVED_CSV = REPO_ROOT / "countries" / "canada" / "data" / "canada_assignment1_approved.csv"
REVIEW_CSV = REPO_ROOT / "countries" / "canada" / "data" / "canada_assignment1_review.csv"

APPROVED_CSV_REL = "countries/canada/data/canada_assignment1_approved.csv"
REVIEW_CSV_REL = "countries/canada/data/canada_assignment1_review.csv"


# --------------------------------------------------------------------
# The files are tracked, plaintext, and sit in the ordinary working tree.
# --------------------------------------------------------------------

def test_tracked_assignment_csvs_exist_as_plain_files_in_the_repo():
    assert APPROVED_CSV.exists(), "expected the tracked APPROVED csv in a normal checkout"
    assert REVIEW_CSV.exists(), "expected the tracked REVIEW csv in a normal checkout"


def test_tracked_assignment_csvs_are_directly_readable_with_no_mediation():
    """No decryption, no service call, no tool required - ordinary
    filesystem read access is sufficient, exactly like any other tracked
    repo file. This is the concrete fact behind "Known limitation" in
    docs/student_workflow.md."""
    approved_text = APPROVED_CSV.read_text(encoding="utf-8")
    review_text = REVIEW_CSV.read_text(encoding="utf-8")
    assert "Date" in approved_text.splitlines()[0]  # header row, plain CSV
    assert "Validation Reason" in review_text.splitlines()[0]


# --------------------------------------------------------------------
# pollitik_guard.py (the one deterministic enforcement mechanism this
# repo has) does not restrict Read at all, for any path.
# --------------------------------------------------------------------

def test_hook_has_no_rule_for_the_read_tool_at_all():
    """pollitik_guard.py only branches on Bash/Write/Edit/NotebookEdit/
    WebFetch (see its main()) - Read is not one of the tool names it
    inspects, so it silently allows every Read call, including one
    against a tracked assignment CSV."""
    decision = run_hook("Read", {"file_path": APPROVED_CSV_REL})
    assert decision == {}  # no opinion -> allowed
    decision = run_hook("Read", {"file_path": REVIEW_CSV_REL})
    assert decision == {}


# --------------------------------------------------------------------
# pollitik_guard.py's Bash check only looks for shell-networking,
# destructive ops, and production-workbook writes - a plain read-only
# `cat`/`type` of these CSVs matches none of those patterns.
# --------------------------------------------------------------------

def test_hook_allows_plain_cat_of_the_approved_csv():
    decision = run_hook("Bash", {"command": f"cat {APPROVED_CSV_REL}"})
    assert decision == {}


def test_hook_allows_plain_cat_of_the_review_csv():
    decision = run_hook("Bash", {"command": f"cat {REVIEW_CSV_REL}"})
    assert decision == {}


def test_hook_allows_windows_type_of_the_approved_csv():
    decision = run_hook("Bash", {"command": f"type {APPROVED_CSV_REL}"})
    assert decision == {}


# --------------------------------------------------------------------
# pollitik_guard.py's Write/Edit check (check_write_or_edit) only
# matches EXCEL_EXT_RE (.xlsx/.xlsm/.xls) with a production indicator in
# the path - a brand-new .csv file is never an Excel path, so making a
# copy of a student's own approved data is not blocked by the hook. This
# is expected: under the 2026-08-25 policy, a student's own assignment
# CSV isn't restricted data, so there is nothing to "work around" here.
# --------------------------------------------------------------------

def test_hook_does_not_block_writing_a_copy_of_the_students_own_csv():
    decision = run_hook(
        "Write",
        {
            "file_path": "countries/canada/data/canada_assignment1_approved_copy_for_student.csv",
            "content": "Date,Approval,Prime Minister,Party,Series,Source,Status\n",
        },
    )
    assert decision == {}  # no opinion -> allowed; the student's own data isn't restricted


def test_hook_does_not_treat_csv_extension_as_a_production_workbook_path():
    """Sanity check on the regex itself: is_production_workbook_path only
    matches .xlsx/.xlsm/.xls, so pollitik + .csv never trips the
    production-workbook Write/Edit guard."""
    decision = run_hook(
        "Write",
        {"file_path": "data/processed/pollitik_master_copy.csv", "content": "x"},
    )
    assert decision == {}


# --------------------------------------------------------------------
# Contrast: the production workbook and web-fetch allow-list ARE real,
# deterministic boundaries - included here so this file's "the CSVs are
# unprotected" findings aren't mistaken for "the hook doesn't work".
# --------------------------------------------------------------------

def test_hook_still_blocks_direct_write_to_the_production_workbook():
    decision = run_hook(
        "Write",
        {"file_path": "data/master/pollitik_master.xlsx", "content": "junk"},
    )
    assert decision.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def test_hook_still_blocks_webfetch_outside_the_allowed_domain_list():
    decision = run_hook("WebFetch", {"url": "https://not-an-approved-domain.example/page"})
    assert decision.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
