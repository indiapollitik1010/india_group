"""Regression tests for student-facing routing/wording guidance (docs
only - no code path exists for "how Codex phrases an answer", so these
assert directly on the doc text that governs it).

Covers:
  - the 2026-08-25 student-data-access policy correction: a student's
    own assignment data (APPROVED/REVIEW results, validation reasons,
    the underlying rows, and the file path/CSV itself on request) is
    documented as visible/inspectable, not refused - while the
    production/master workbook and other students'/countries' data stay
    protected.
  - the 2026-08-23 Codex acceptance-test cleanup: both graph-request
    workflows (student unsure -> recommend only; student names/implies a
    specific type -> generate directly) and the vague-request fallback
    to recommendations are documented.
"""

import re

from .conftest import REPO_ROOT


def _normalize(text):
    """Collapse markdown line-wrapping so a phrase that happens to wrap
    across two source lines still matches as one substring."""
    return re.sub(r"\s+", " ", text)


STUDENT_WORKFLOW = (REPO_ROOT / "docs" / "student_workflow.md").read_text(encoding="utf-8")
PROMPT_GUIDE = (REPO_ROOT / "docs" / "prompt_guide.md").read_text(encoding="utf-8")
STUDENT_WORKFLOW_FLAT = _normalize(STUDENT_WORKFLOW)
PROMPT_GUIDE_FLAT = _normalize(PROMPT_GUIDE)


def test_student_workflow_documents_safe_answer_phrasing():
    assert "Student data-access policy" in STUDENT_WORKFLOW
    assert "validated Canada Assignment 1 data" in STUDENT_WORKFLOW_FLAT
    assert "Canada Assignment 1 REVIEW records" in STUDENT_WORKFLOW_FLAT


def test_student_workflow_permits_students_own_data_on_request():
    """2026-08-25 policy correction: a student's own assignment data is
    not secret - explicit requests for the CSV, the file path, or the
    raw rows must be honored, not refused."""
    section = _normalize(STUDENT_WORKFLOW[STUDENT_WORKFLOW.index("Student data-access policy"):])
    assert "Explicitly request their assignment CSV" in section
    assert "be given it" in section
    assert "no reason to withhold a student's own data" in section


# --------------------------------------------------------------------
# 2026-08-25 student-data-access policy correction: a student's own
# tracked assignment data is learning material, not secret data.
# Students may inspect summaries, aggregate questions, REVIEW awareness,
# graphs, the underlying rows, and the CSV/file path itself on request.
# Only the production/master workbook and other students'/countries'
# data stay protected (see the filesystem-access tests in
# tests/test_student_data_access_boundary.py for what is, and is not,
# enforced at the tool/hook layer - the two are consistent now).
# --------------------------------------------------------------------

def test_student_workflow_documents_permitted_actions():
    section = _normalize(STUDENT_WORKFLOW[STUDENT_WORKFLOW.index("Student data-access policy"):])
    for phrase in (
        "Ask to see their own APPROVED results",
        "underlying rows and columns",
        "Ask to see their own REVIEW records",
        "Explicitly request their assignment CSV",
    ):
        assert phrase in section


def test_student_workflow_documents_production_protection_unchanged():
    """What must stay protected: the production workbook, and other
    students'/countries' data - never weakened by the 2026-08-25 policy
    correction."""
    section = _normalize(STUDENT_WORKFLOW[STUDENT_WORKFLOW.index("Student data-access policy"):])
    assert "production/master Pollitik workbook" in section
    assert "must never write to it directly" in section
    assert "python/apply_changes.py" in section
    assert "Another student's or another country's assignment data" in section


def test_student_workflow_documents_policy_reversal_history():
    assert "History: prior response-only restriction (reversed 2026-08-25)" in STUDENT_WORKFLOW
    section = _normalize(
        STUDENT_WORKFLOW[STUDENT_WORKFLOW.index("History: prior response-only restriction"):]
    )
    assert "reversed" in section
    assert "never actually secret" in section
    assert "tests/test_student_data_access_boundary.py" in section


def test_canada_agents_md_documents_corrected_student_data_policy():
    canada_agents = (REPO_ROOT / "countries" / "canada" / "AGENTS.md").read_text(encoding="utf-8")
    section = _normalize(canada_agents[canada_agents.index("## Student data-access policy"):])
    assert "not secret" in section
    assert "request the CSV itself or its file path" in section
    assert "production/master workbook" in section
    assert "python/apply_changes.py" in section


def test_canada_agents_md_documents_filesystem_access_note():
    canada_agents = (REPO_ROOT / "countries" / "canada" / "AGENTS.md").read_text(encoding="utf-8")
    assert "Filesystem access note" in canada_agents
    section = _normalize(canada_agents[canada_agents.index("Filesystem access note"):])
    assert "no longer a" in section and "gap" in section
    assert "pollitik_guard.py" in section
    assert "production workbook" in section


def test_prompt_guide_documents_student_unsure_workflow():
    assert "I'm not sure which graph" in PROMPT_GUIDE_FLAT
    assert "student unsure" in PROMPT_GUIDE_FLAT
    assert "Generates nothing yet" in PROMPT_GUIDE_FLAT


def test_prompt_guide_documents_direct_unambiguous_graph_request():
    assert "Mark Carney's validated approval over time" in PROMPT_GUIDE_FLAT
    assert "--graph approval_over_time" in PROMPT_GUIDE_FLAT
    assert "does **not** force the recommend-first step" in PROMPT_GUIDE_FLAT


def test_prompt_guide_documents_vague_request_falls_back_to_recommendations():
    idx = PROMPT_GUIDE_FLAT.index("Generate a graph of the Canada results.")
    section = PROMPT_GUIDE_FLAT[idx: idx + 400]
    assert "Too vague" in section
    assert "recommendations instead of guessing" in section


def test_prompt_guide_permits_naming_the_file_or_path_on_request():
    """2026-08-25 policy correction: no rule against naming the file/path
    or handing over the underlying rows if the student asks for either -
    it's their own assignment data."""
    idx = PROMPT_GUIDE_FLAT.index("Give me a summary of Mark Carney")
    section = PROMPT_GUIDE_FLAT[idx: idx + 700]
    assert "validated Canada Assignment 1 data" in section
    assert "own assignment data" in section
    assert "handing over the underlying rows" in section


def test_prompt_guide_documents_country_creation_routing():
    assert "init_country_workspace.py" in PROMPT_GUIDE_FLAT
    assert "a question never creates files on its own" in PROMPT_GUIDE_FLAT


# --------------------------------------------------------------------
# Issue 2 (2026-08-23 Codex acceptance-test cleanup): graph-selection
# guidance must present numbered, human-readable options and accept a
# natural reply (number, name, description, or "all three") - never
# require the internal graph_type id.
# --------------------------------------------------------------------

VISUALIZATION_RULES = (REPO_ROOT / "docs" / "visualization_rules.md").read_text(encoding="utf-8")
VISUALIZATION_RULES_FLAT = _normalize(VISUALIZATION_RULES)
CANADA_AGENTS_MD = (REPO_ROOT / "countries" / "canada" / "AGENTS.md").read_text(encoding="utf-8")
CANADA_README = (REPO_ROOT / "countries" / "canada" / "README.md").read_text(encoding="utf-8")


def test_visualization_rules_documents_numbered_human_readable_presentation():
    section = VISUALIZATION_RULES_FLAT[
        VISUALIZATION_RULES_FLAT.index("Recommend, then the student chooses"):
    ]
    assert "numbered, human-readable list" in section
    assert "never" in section
    assert "internal graph type id" in section


def test_visualization_rules_documents_natural_reply_and_all_three():
    section = VISUALIZATION_RULES_FLAT[
        VISUALIZATION_RULES_FLAT.index("Recommend, then the student chooses"):
    ]
    assert "option number" in section
    assert "display name" in section
    assert "natural description" in section
    assert "all three" in section
    assert "resolve_student_choice" in section


def test_canada_agents_md_forbids_internal_graph_ids_in_student_wording():
    section = CANADA_AGENTS_MD[CANADA_AGENTS_MD.index("## Graph workflow"):]
    assert "never" in section
    assert "internal graph type id" in section
    assert "all three" in section


def test_canada_readme_graph_instructions_avoid_internal_ids():
    section = CANADA_README[CANADA_README.index("How a student gets graph recommendations"):]
    assert "internal graph type id" in section
    assert "all three" in section
    assert "natural description" in section
