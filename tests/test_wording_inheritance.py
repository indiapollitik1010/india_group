"""Regression tests for Skill section 48: canonical question-wording
inheritance from docs/ead/reference/EAD Series and Question Wording.xlsx
("Ryan's rule"). Exercises validate_record.py/verify_wording.py as real
subprocesses against isolated sandbox directories, same pattern as
test_pipeline_write_guards.py.
"""

import json

import openpyxl

from .conftest import run_script

EAD_FILENAME = "EAD Series and Question Wording.xlsx"
LIAISON_WORDING = (
    "Do you approve or disapprove of the job [PM name] is doing as prime minister?"
)


def make_ead_workbook(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append([
        "Country", "Series", "Description", "Question Type",
        "Question Wording", "Method (face to face, telephone, mixed, etc.)",
    ])
    for row in rows:
        ws.append(row)
    wb.save(path)


def make_record(**overrides):
    base = {
        "country": "Canada",
        "series": "LIAISON",
        "pollster": "Liaison Strategies",
        "question_wording_status": "INHERITED_FROM_SERIES_REFERENCE",
        "positive": 64,
        "negative": 32,
        "neutral": None,
        "response_categories": {"Approve": 64, "Disapprove": 32},
        "category_classification": {"Approve": "positive", "Disapprove": "negative"},
        "sample_size": 1000,
        "fieldwork_date_normalized": "3/21/2026",
        "fieldwork_date_status": "OBSERVED",
        "requested_url": "https://approved-pollster.example/report",
        "final_url": "https://approved-pollster.example/report",
        "http_status": 200,
        "retrieved_at": "2026-08-14T00:00:00Z",
        "evidence_text": "Approve 64, Disapprove 32.",
    }
    base.update(overrides)
    return base


def validate(sandbox, record):
    proc = run_script("validate_record.py", sandbox, input_json=record)
    assert proc.returncode in (0, 1), proc.stderr
    return json.loads(proc.stdout)


# --- 1: valid inheritance from one exact Country+Series approval row ------

def test_inherited_wording_with_single_matching_row_is_approved(sandbox):
    make_ead_workbook(
        sandbox / "docs" / "ead" / "reference" / EAD_FILENAME,
        [["Canada", "LIAISON", "Liaison Strategies", "Approval", LIAISON_WORDING, None]],
    )
    result = validate(sandbox, make_record())
    assert result["validation_status"] == "APPROVED", result
    assert "WORDING_INHERITED_FROM_SERIES_REFERENCE" in result["validation_flags"]
    assert "QUESTION_WORDING_UNKNOWN" not in result["validation_flags"]
    assert result["question_wording_source"] == "EAD_SERIES_REFERENCE"
    assert result["question_wording_english"] == LIAISON_WORDING


# --- 2: no matching reference row -> REVIEW --------------------------------

def test_inherited_wording_with_no_matching_row_is_review(sandbox):
    make_ead_workbook(sandbox / "docs" / "ead" / "reference" / EAD_FILENAME, [])
    result = validate(sandbox, make_record())
    assert result["validation_status"] == "REVIEW", result
    assert "QUESTION_WORDING_UNKNOWN" in result["validation_flags"]
    assert result["wording_inheritance_check"]["row_count"] == 0


# --- 3: multiple/ambiguous applicable rows -> REVIEW -----------------------

def test_inherited_wording_with_multiple_rows_is_review(sandbox):
    make_ead_workbook(
        sandbox / "docs" / "ead" / "reference" / EAD_FILENAME,
        [
            ["Canada", "LIAISON", "Liaison Strategies", "Approval", LIAISON_WORDING, None],
            ["Canada", "LIAISON", "Liaison Strategies", "Favourability",
             "Do you have a favourable or unfavourable view of [PM name]?", None],
        ],
    )
    result = validate(sandbox, make_record())
    assert result["validation_status"] == "REVIEW", result
    assert "QUESTION_WORDING_UNKNOWN" in result["validation_flags"]
    assert result["wording_inheritance_check"]["row_count"] == 2


# --- 4: series ambiguity forces REVIEW regardless of wording eligibility --

def test_series_review_required_forces_review_even_with_eligible_wording(sandbox):
    make_ead_workbook(
        sandbox / "docs" / "ead" / "reference" / EAD_FILENAME,
        [["Canada", "LIAISON", "Liaison Strategies", "Approval", LIAISON_WORDING, None]],
    )
    result = validate(sandbox, make_record(series_match_status="SERIES_REVIEW_REQUIRED"))
    assert result["validation_status"] == "REVIEW", result
    assert "SERIES_REVIEW_REQUIRED" in result["validation_flags"]
    # Wording itself still resolves - only series ambiguity blocks approval.
    assert "WORDING_INHERITED_FROM_SERIES_REFERENCE" in result["validation_flags"]


# --- 5: existing UNKNOWN_WORDING behavior unchanged ------------------------

def test_unknown_wording_still_review(sandbox):
    result = validate(sandbox, make_record(question_wording_status="UNKNOWN_WORDING"))
    assert result["validation_status"] == "REVIEW", result
    assert "QUESTION_WORDING_UNKNOWN" in result["validation_flags"]


# --- 6: existing directly-verified wording behavior unchanged -------------

def test_exact_wording_from_source_unaffected(sandbox):
    result = validate(sandbox, make_record(
        question_wording_status="EXACT_WORDING",
        question_wording_original="Approuvez-vous la facon dont ... premier ministre?",
        question_wording_english="Do you approve of the way ... is doing as prime minister?",
    ))
    assert result["validation_status"] == "APPROVED", result
    assert "QUESTION_WORDING_UNKNOWN" not in result["validation_flags"]
    assert "WORDING_INHERITED_FROM_SERIES_REFERENCE" not in result["validation_flags"]
    assert "question_wording_source" not in result


# --- 7: unrelated REVIEW reasons remain REVIEW -----------------------------

def test_unrelated_review_reason_untouched_by_wording_change(sandbox):
    result = validate(sandbox, make_record(
        question_wording_status="UNKNOWN_WORDING",
        sample_size=-5,
    ))
    assert result["validation_status"] == "REVIEW", result
    assert "SAMPLE_SIZE_REVIEW_REQUIRED" in result["validation_flags"]
    assert "QUESTION_WORDING_UNKNOWN" in result["validation_flags"]


# --- 8: a LIAISON-style clean record becomes APPROVED-eligible ------------

def test_liaison_style_clean_record_becomes_approved(sandbox):
    make_ead_workbook(
        sandbox / "docs" / "ead" / "reference" / EAD_FILENAME,
        [["Canada", "LIAISON", "Liaison Strategies", "Approval", LIAISON_WORDING, None]],
    )
    result = validate(sandbox, make_record())
    assert result["validation_status"] == "APPROVED", result


# --- 9: a LIAISON-style record with inferred sample size stays REVIEW -----

def test_liaison_style_record_with_inferred_sample_size_stays_review(sandbox):
    make_ead_workbook(
        sandbox / "docs" / "ead" / "reference" / EAD_FILENAME,
        [["Canada", "LIAISON", "Liaison Strategies", "Approval", LIAISON_WORDING, None]],
    )
    result = validate(sandbox, make_record(
        sample_size=None, sample_size_status="INFERRED_FROM_FIRM_PATTERN",
    ))
    assert result["validation_status"] == "REVIEW", result
    assert "SAMPLE_SIZE_INFERRED_FROM_PATTERN" in result["validation_flags"]
    assert "WORDING_INHERITED_FROM_SERIES_REFERENCE" in result["validation_flags"]
    assert "QUESTION_WORDING_UNKNOWN" not in result["validation_flags"]
