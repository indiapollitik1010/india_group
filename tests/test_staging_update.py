"""Regression tests for in-place staging updates (stage_changes.py
--update / update_batch) and the matching apply_changes.py duplicate-
record_id write guard.

Motivation: stage_changes.py was originally append-only. Revalidating an
already-staged candidate (e.g. after a new deterministic rule like the
EAD canonical-wording inheritance check changes its outcome) had no safe
way to replace the existing staged line - re-staging would append a
duplicate line sharing the same or a fresh record_id, and
apply_changes.py did not protect against multiple lines sharing one
record_id, which could have written the same observation to production
twice. This file exercises the fix: an explicit, atomic, fail-safe
update-by-record_id mode, plus a defensive duplicate check in
apply_changes.py.

Real subprocess invocations against isolated sandbox directories, same
pattern as test_batch_validation.py / test_pipeline_write_guards.py. See
tests/conftest.py for how CLAUDE_PROJECT_DIR isolation works.
"""

import json

import openpyxl

from .conftest import run_hook, run_script


def make_record(**overrides):
    base = {
        "country": "TestCountry",
        "series": "Job Approval",
        "pollster": "Test Pollster",
        "question_wording_status": "EXACT_WORDING",
        "positive": 58,
        "negative": 36,
        "neutral": None,
        "response_categories": {"Very poorly": 14, "Poorly": 22, "Well": 40, "Very well": 18},
        "category_classification": {
            "Very poorly": "negative",
            "Poorly": "negative",
            "Well": "positive",
            "Very well": "positive",
        },
        "sample_size": 1204,
        "fieldwork_date_normalized": "1/8/2026",
        "fieldwork_date_status": "OBSERVED",
        "requested_url": "https://approved-pollster.example/report",
        "final_url": "https://approved-pollster.example/report",
        "http_status": 200,
        "retrieved_at": "2026-08-12T14:03:00Z",
        "evidence_text": "Very poorly 14, Poorly 22, Well 40, Very well 18.",
    }
    base.update(overrides)
    return base


def make_fixture_workbook(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(["Record Id", "Country", "Series", "Pollster", "Positive", "Negative", "Sample Size"])
    wb.save(path)


def staging_path(sandbox):
    return sandbox / "data" / "staging" / "candidates.jsonl"


def read_staging_lines(sandbox):
    path = staging_path(sandbox)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def stage_one(sandbox, record):
    proc = run_script("stage_changes.py", sandbox, input_json=record)
    assert proc.returncode in (0, 1), proc.stderr
    return json.loads(proc.stdout)


def update_one(sandbox, record):
    return run_script("stage_changes.py", sandbox, args=["--update"], input_json=record)


def update_batch_records(sandbox, records):
    return run_script(
        "stage_changes.py", sandbox, args=["--update", "--batch"], raw_input=json.dumps(records),
    )


def _first_result(stdout_text):
    """apply_changes.py prints either a bare {"error": ...} dict (for the
    checks that run before per-record processing: unknown record_id,
    duplicate record_id) or a JSON array of one-result-per-target dicts
    (for anything that reaches per-record apply_one/validate). Normalize
    both shapes to a single dict so callers don't need to care which
    path produced it."""
    if not stdout_text.strip():
        return None
    parsed = json.loads(stdout_text)
    return parsed[0] if isinstance(parsed, list) else parsed


def apply_(sandbox, record_id, workbook_path, sheet="Data"):
    proc = run_script(
        "apply_changes.py",
        sandbox,
        args=["--record-id", record_id, "--workbook", str(workbook_path), "--sheet", sheet],
    )
    return proc, _first_result(proc.stdout)


def apply_all(sandbox, workbook_path, sheet="Data"):
    proc = run_script(
        "apply_changes.py",
        sandbox,
        args=["--apply-all-approved", "--workbook", str(workbook_path), "--sheet", sheet],
    )
    return proc, _first_result(proc.stdout)


# --- New record still appends normally --------------------------------

def test_new_record_still_appends_normally(sandbox):
    assert read_staging_lines(sandbox) == []
    staged = stage_one(sandbox, make_record())
    assert staged["validation_status"] == "APPROVED"
    lines = read_staging_lines(sandbox)
    assert len(lines) == 1
    assert lines[0]["record_id"] == staged["record_id"]


# --- One existing record can be safely replaced by record_id ----------

def test_update_replaces_existing_record_in_place(sandbox):
    staged = stage_one(sandbox, make_record(pollster="Original Firm"))
    record_id = staged["record_id"]

    updated_input = dict(staged)
    updated_input["pollster"] = "Corrected Firm"

    proc = update_one(sandbox, updated_input)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["record_id"] == record_id
    assert result["pollster"] == "Corrected Firm"
    assert result["validation_status"] == "APPROVED"

    lines = read_staging_lines(sandbox)
    assert len(lines) == 1
    assert lines[0]["record_id"] == record_id
    assert lines[0]["pollster"] == "Corrected Firm"


# --- Replacing does not increase candidates.jsonl line count ----------

def test_update_does_not_increase_line_count(sandbox):
    a = stage_one(sandbox, make_record(pollster="Firm A"))
    b = stage_one(sandbox, make_record(pollster="Firm B"))
    assert len(read_staging_lines(sandbox)) == 2

    updated_input = dict(a)
    updated_input["pollster"] = "Firm A Revised"
    proc = update_one(sandbox, updated_input)
    assert proc.returncode == 0, proc.stderr

    lines = read_staging_lines(sandbox)
    assert len(lines) == 2  # unchanged - no duplicate appended
    ids = {line["record_id"] for line in lines}
    assert ids == {a["record_id"], b["record_id"]}


# --- Zero matching record_id fails safely ------------------------------

def test_update_with_unknown_record_id_fails_safely(sandbox):
    record = make_record(record_id="does-not-exist-in-staging")
    proc = update_one(sandbox, record)
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert "error" in result
    assert "does-not-exist-in-staging" in result["error"]
    # Nothing was written.
    assert read_staging_lines(sandbox) == []


# --- Duplicate existing record_id fails safely -------------------------

def test_update_with_duplicate_existing_record_id_fails_safely(sandbox):
    dupe_record = make_record(record_id="dupe-id-123")
    dupe_record["validation_status"] = "REVIEW"
    path = staging_path(sandbox)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(dupe_record) + "\n")
        f.write(json.dumps(dupe_record) + "\n")
    assert len(read_staging_lines(sandbox)) == 2

    update_input = make_record(record_id="dupe-id-123", pollster="Attempted Fix")
    proc = update_one(sandbox, update_input)
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert "error" in result
    assert "dupe-id-123" in result["error"]
    assert "duplicated" in result["error"] or "ambiguous" in result["error"]
    # Staging file is untouched - still exactly the two original lines.
    lines = read_staging_lines(sandbox)
    assert len(lines) == 2
    assert all(line["pollster"] != "Attempted Fix" for line in lines)


# --- Batch update of multiple existing records works -------------------

def test_batch_update_of_multiple_existing_records(sandbox):
    proc = run_script(
        "stage_changes.py", sandbox, args=["--batch"],
        raw_input=json.dumps([make_record(pollster="Firm A"), make_record(pollster="Firm B")]),
    )
    staged_list = json.loads(proc.stdout)
    assert len(staged_list) == 2

    updates = []
    for staged in staged_list:
        rec = dict(staged)
        rec["pollster"] = rec["pollster"] + " (revised)"
        updates.append(rec)

    proc = update_batch_records(sandbox, updates)
    assert proc.returncode == 0, proc.stderr
    results = json.loads(proc.stdout)
    assert len(results) == 2
    assert {r["record_id"] for r in results} == {s["record_id"] for s in staged_list}
    assert all(r["pollster"].endswith("(revised)") for r in results)

    lines = read_staging_lines(sandbox)
    assert len(lines) == 2  # still no duplicates
    assert all(line["pollster"].endswith("(revised)") for line in lines)


def test_batch_update_targeting_same_record_id_twice_fails_safely(sandbox):
    staged = stage_one(sandbox, make_record())
    rec = dict(staged)
    proc = update_batch_records(sandbox, [rec, dict(rec)])
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert "error" in result
    # Original state untouched.
    lines = read_staging_lines(sandbox)
    assert len(lines) == 1
    assert lines[0]["record_id"] == staged["record_id"]


def test_batch_update_is_all_or_nothing_when_one_target_is_missing(sandbox):
    a = stage_one(sandbox, make_record(pollster="Firm A"))
    good_update = dict(a)
    good_update["pollster"] = "Firm A Revised"
    bad_update = make_record(record_id="not-a-real-id", pollster="Ghost Firm")

    proc = update_batch_records(sandbox, [good_update, bad_update])
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert "error" in result
    assert "not-a-real-id" in result["error"]

    # The valid half of the batch was NOT partially applied.
    lines = read_staging_lines(sandbox)
    assert len(lines) == 1
    assert lines[0]["pollster"] == "Firm A"


# --- REVIEW remains REVIEW after update ---------------------------------

def test_review_record_remains_review_after_update(sandbox):
    staged = stage_one(sandbox, make_record(sample_size=-5))  # SAMPLE_SIZE_REVIEW_REQUIRED
    assert staged["validation_status"] == "REVIEW"

    updated_input = dict(staged)  # nothing that fixes the review reason changes
    proc = update_one(sandbox, updated_input)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["validation_status"] == "REVIEW"
    assert "SAMPLE_SIZE_REVIEW_REQUIRED" in result["validation_flags"]


# --- APPROVED can replace its previous REVIEW version -------------------

def test_approved_can_replace_previous_review_version(sandbox):
    staged = stage_one(sandbox, make_record(question_wording_status="UNKNOWN_WORDING"))
    assert staged["validation_status"] == "REVIEW"
    record_id = staged["record_id"]

    fixed_input = dict(staged)
    fixed_input["question_wording_status"] = "EXACT_WORDING"

    proc = update_one(sandbox, fixed_input)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["record_id"] == record_id
    assert result["validation_status"] == "APPROVED"

    lines = read_staging_lines(sandbox)
    assert len(lines) == 1
    assert lines[0]["record_id"] == record_id
    assert lines[0]["validation_status"] == "APPROVED"

    # staged_at (first-staged time) is preserved; updated_at is new.
    assert lines[0]["staged_at"] == staged["staged_at"]
    assert "updated_at" in lines[0]


# --- apply_changes.py refuses duplicate record_id staging state --------

def test_apply_changes_refuses_duplicate_record_id_by_record_id(sandbox):
    good = make_record(record_id="dupe-apply-1")
    path = staging_path(sandbox)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Two independently-staged lines that happen to share a record_id
    # (the exact corrupt/ambiguous state the guard must catch).
    with open(path, "w", encoding="utf-8") as f:
        for _ in range(2):
            proc_record = dict(good)
            f.write(json.dumps(proc_record) + "\n")

    # Re-validate through the normal pipeline so both lines look APPROVED.
    lines = read_staging_lines(sandbox)
    for line in lines:
        assert line["record_id"] == "dupe-apply-1"

    workbook = sandbox / "fixture.xlsx"
    make_fixture_workbook(workbook)

    proc, result = apply_(sandbox, "dupe-apply-1", workbook)
    assert "error" in result
    assert "dupe-apply-1" in result["error"]

    wb = openpyxl.load_workbook(workbook, read_only=True)
    assert wb["Data"].max_row == 1  # nothing written


def test_apply_changes_refuses_apply_all_when_any_duplicate_exists(sandbox):
    clean = stage_one(sandbox, make_record(pollster="Clean Firm"))

    dupe = make_record(record_id="dupe-apply-2", pollster="Dupe Firm")
    path = staging_path(sandbox)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(dupe) + "\n")
        f.write(json.dumps(dupe) + "\n")

    workbook = sandbox / "fixture.xlsx"
    make_fixture_workbook(workbook)

    proc, result = apply_all(sandbox, workbook)
    assert "error" in result
    assert "dupe-apply-2" in result["error"]

    wb = openpyxl.load_workbook(workbook, read_only=True)
    assert wb["Data"].max_row == 1  # refused entirely - not even the clean record was written


# --- Existing production write guards still work ------------------------

def test_apply_still_works_normally_after_an_update(sandbox):
    """An update followed by a normal apply on the now-unique,
    now-APPROVED line still succeeds - the new guard only fires on
    actual duplicates, never on ordinary unique staged state."""
    staged = stage_one(sandbox, make_record(question_wording_status="UNKNOWN_WORDING"))
    assert staged["validation_status"] == "REVIEW"

    fixed_input = dict(staged)
    fixed_input["question_wording_status"] = "EXACT_WORDING"
    proc = update_one(sandbox, fixed_input)
    updated = json.loads(proc.stdout)
    assert updated["validation_status"] == "APPROVED"

    workbook = sandbox / "fixture.xlsx"
    make_fixture_workbook(workbook)
    proc, result = apply_(sandbox, updated["record_id"], workbook)
    assert "error" not in result, result
    assert result["verified_after_save"] is True

    wb = openpyxl.load_workbook(workbook, read_only=True)
    assert wb["Data"].max_row == 2


def test_review_record_still_cannot_be_applied(sandbox):
    staged = stage_one(sandbox, make_record(sample_size=-5))
    assert staged["validation_status"] == "REVIEW"

    workbook = sandbox / "fixture.xlsx"
    make_fixture_workbook(workbook)
    proc, result = apply_(sandbox, staged["record_id"], workbook)
    assert "error" in result
    assert "REVIEW" in result["error"]
    wb = openpyxl.load_workbook(workbook, read_only=True)
    assert wb["Data"].max_row == 1


def test_hook_still_blocks_direct_production_write():
    decision = run_hook(
        "Write",
        {"file_path": "data/master/pollitik_master.xlsx", "content": "junk"},
    )
    assert decision.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def test_hook_still_allows_staging_writes():
    decision = run_hook(
        "Write",
        {"file_path": "data/staging/candidates.jsonl", "content": "{}"},
    )
    assert decision == {}  # no opinion -> allowed
