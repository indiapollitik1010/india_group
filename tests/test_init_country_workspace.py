"""Tests for python/init_country_workspace.py - the deterministic
country-workspace scaffolding script (Step 1 of the country-scaffolding
architecture; see docs/country_blueprint.md and the "Creating a new
country workspace" rule in the root AGENTS.md).

These tests run entirely against tmp_path sandboxes - never the real
repo's countries/canada/, data/master/, data/staging/, or config/ - the
same isolation style test_build_country_assignment_snapshot.py and
test_resolve_assignment_dataset.py already use. A handful of tests read
the real repo's docs/AGENTS.md text (read-only) to prove the natural-
language routing rule and the corrected student-data policy are
actually documented where Codex would find them.
"""

import hashlib
import json
import re
import subprocess
import sys

import pytest

from .conftest import REPO_ROOT, run_script

sys.path.insert(0, str(REPO_ROOT / "python"))
import init_country_workspace as icw  # noqa: E402
from check_assignment_preflight import normalize_country_slug as preflight_normalize_country_slug  # noqa: E402

SCRIPT = REPO_ROOT / "python" / "init_country_workspace.py"

EXPECTED_RELATIVE_FILES = [
    "AGENTS.md",
    "README.md",
    "prompts/run_assignment.txt",
    "prompts/continue_research.txt",
    "prompts/review_results.txt",
    "prompts/recommend_graphs.txt",
    "prompts/generate_graph.txt",
    "data/README.md",
    "output/README.md",
]

# Real Canada blueprint content that must never leak into a new
# country's generated files - pollsters/series from
# countries/canada/data/canada_reference_snapshot.csv and
# .claude/skills/pollitik-executive-support/references/canada.md, plus
# the PM's name used throughout the Canada Assignment 1 tracked CSVs.
FORBIDDEN_CANADA_CONTENT = [
    "Mark Carney",
    "LIAISON",
    "ANGUSREID",
    "LEGER",
    "RESEARCHCO",
    "leger360.com",
    "angusreid.org",
    "researchco.ca",
]


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _hash_tree(paths):
    return {str(p): _sha256(p) for p in paths if p.is_file()}


# --------------------------------------------------------------------
# 1. Basic creation: expected files, correct substitution.
# --------------------------------------------------------------------

def test_creates_expected_files_with_country_and_slug_substituted(tmp_path):
    result = icw.init_country_workspace("Australia", project_dir=str(tmp_path))
    assert result["created"] is True
    assert result["country_slug"] == "australia"

    country_dir = tmp_path / "countries" / "australia"
    for relative in EXPECTED_RELATIVE_FILES:
        full_path = country_dir / relative
        assert full_path.is_file(), f"expected {relative} to be created"

    # Nothing extra was created alongside the 9 expected files.
    all_files = sorted(
        str(p.relative_to(country_dir)).replace("\\", "/")
        for p in country_dir.rglob("*") if p.is_file()
    )
    assert all_files == sorted(EXPECTED_RELATIVE_FILES)

    agents_md = (country_dir / "AGENTS.md").read_text(encoding="utf-8")
    assert "Australia assignment (SETUP REQUIRED)" in agents_md
    assert "countries/australia/data/australia_reference_snapshot.csv" in agents_md

    run_assignment = (country_dir / "prompts" / "run_assignment.txt").read_text(encoding="utf-8")
    assert "--country Australia" in run_assignment


def test_reported_files_created_list_matches_disk(tmp_path):
    result = icw.init_country_workspace("Australia", project_dir=str(tmp_path))
    reported = set(result["files_created"])
    expected = {f"countries/australia/{rel}" for rel in EXPECTED_RELATIVE_FILES}
    assert reported == expected


# --------------------------------------------------------------------
# 2. Slug normalization reuses check_assignment_preflight.py's logic -
#    never reimplemented, so the two scripts can never disagree.
# --------------------------------------------------------------------

def test_slug_normalization_is_the_same_function_preflight_uses():
    assert icw.normalize_country_slug is preflight_normalize_country_slug


@pytest.mark.parametrize("name", ["Australia", "AUSTRALIA", "  Australia  ", "australia"])
def test_slug_normalized_consistently_regardless_of_casing_or_whitespace(name, tmp_path):
    result = icw.init_country_workspace(name, project_dir=str(tmp_path))
    assert result["country_slug"] == "australia"
    assert icw.normalize_country_slug(name) == preflight_normalize_country_slug(name)


@pytest.mark.parametrize("name", ["New Zealand", "NEW ZEALAND", "  New Zealand  ", "new zealand"])
def test_multi_word_country_slug_hyphenates_to_match_existing_folder_convention(name, tmp_path):
    """countries/new-zealand/ is the existing tracked folder - a fresh
    workspace init for any casing/whitespace variant of "New Zealand"
    must resolve to that same hyphenated slug, not "new zealand" (space)."""
    result = icw.init_country_workspace(name, project_dir=str(tmp_path))
    assert result["country_slug"] == "new-zealand"
    assert (tmp_path / "countries" / "new-zealand").is_dir()
    assert icw.normalize_country_slug(name) == preflight_normalize_country_slug(name)


# --------------------------------------------------------------------
# 3. Refuses to overwrite an existing countries/<slug>/ directory -
#    running it twice is a safe no-op.
# --------------------------------------------------------------------

def test_refuses_to_overwrite_existing_country_dir(tmp_path):
    country_dir = tmp_path / "countries" / "australia"
    country_dir.mkdir(parents=True)
    marker = country_dir / "AGENTS.md"
    marker.write_text("# a student's own customized file\n", encoding="utf-8")

    result = icw.init_country_workspace("Australia", project_dir=str(tmp_path))

    assert result["created"] is False
    assert "already exists" in result["reason"]
    assert marker.read_text(encoding="utf-8") == "# a student's own customized file\n"
    # Nothing else was created either.
    assert sorted(p.name for p in country_dir.iterdir()) == ["AGENTS.md"]


def test_running_initialization_twice_refuses_safely(tmp_path):
    result1 = icw.init_country_workspace("Australia", project_dir=str(tmp_path))
    assert result1["created"] is True

    country_dir = tmp_path / "countries" / "australia"
    before = _hash_tree(list(country_dir.rglob("*")))

    result2 = icw.init_country_workspace("Australia", project_dir=str(tmp_path))
    assert result2["created"] is False
    assert "refusing to overwrite" in result2["reason"]

    after = _hash_tree(list(country_dir.rglob("*")))
    assert before == after, "second run must not modify any file from the first run"


# --------------------------------------------------------------------
# 4. No Canada polling data, series, pollsters, sources, or leader name
#    leaks into a new country's generated files.
# --------------------------------------------------------------------

def test_no_canada_polling_data_leaks_into_generated_files(tmp_path):
    icw.init_country_workspace("Australia", project_dir=str(tmp_path))
    country_dir = tmp_path / "countries" / "australia"

    for path in country_dir.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_CANADA_CONTENT:
            assert forbidden not in text, (
                f"'{forbidden}' (real Canada blueprint content) leaked into {path}"
            )


def test_every_canada_mention_is_part_of_an_allowed_phrase(tmp_path):
    """Black-box re-check of the same guard init_country_workspace.py
    runs internally (icw.assert_no_stray_canada) - every literal
    'canada' in generated content must be immediately followed by
    'blueprint' or 'example', never a bare/accidental reference."""
    icw.init_country_workspace("Australia", project_dir=str(tmp_path))
    country_dir = tmp_path / "countries" / "australia"

    stray_re = re.compile(r"canada(?!\s+(?:blueprint|example))", re.IGNORECASE)
    found_any_canada_mention = False
    for path in country_dir.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if "canada" in text.lower():
            found_any_canada_mention = True
        match = stray_re.search(text)
        assert match is None, f"stray 'Canada' outside an allowed phrase in {path}: {match}"
    assert found_any_canada_mention, (
        "expected at least one intentional 'Canada blueprint' reference somewhere "
        "in the generated skeleton"
    )


def test_render_files_guard_rejects_a_stray_canada_reference():
    """Direct unit test of the guard function itself."""
    with pytest.raises(icw.InitError):
        icw.assert_no_stray_canada("test-label", "This mentions Canada directly, not the blueprint.")
    # Allowed phrasing does not raise.
    icw.assert_no_stray_canada("test-label", "This follows the Canada blueprint pattern.")


# --------------------------------------------------------------------
# 5. No fake reference snapshot, no fake APPROVED/REVIEW dataset.
# --------------------------------------------------------------------

def test_no_fake_reference_snapshot_created(tmp_path):
    icw.init_country_workspace("Australia", project_dir=str(tmp_path))
    data_dir = tmp_path / "countries" / "australia" / "data"
    assert not (data_dir / "australia_reference_snapshot.csv").exists()
    assert sorted(p.name for p in data_dir.iterdir()) == ["README.md"]


def test_no_fake_approved_or_review_dataset_created(tmp_path):
    icw.init_country_workspace("Australia", project_dir=str(tmp_path))
    country_dir = tmp_path / "countries" / "australia"
    assert not (country_dir / "data" / "australia_assignment1_approved.csv").exists()
    assert not (country_dir / "data" / "australia_assignment1_review.csv").exists()
    # No .csv file of any kind exists anywhere in the new workspace.
    assert list(country_dir.rglob("*.csv")) == []


def test_no_skill_or_reference_profile_created(tmp_path):
    icw.init_country_workspace("Australia", project_dir=str(tmp_path))
    # This script only ever writes under countries/<slug>/ - it must
    # never create anything under .claude/, including a country Skill
    # or a reference profile.
    assert not (tmp_path / ".claude").exists()


# --------------------------------------------------------------------
# 6. Never touches data/master/, data/staging/, config/, or another
#    country's folder.
# --------------------------------------------------------------------

def test_never_touches_other_repo_paths(tmp_path):
    (tmp_path / "data" / "master").mkdir(parents=True)
    (tmp_path / "data" / "staging").mkdir(parents=True)
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "countries" / "canada").mkdir(parents=True)

    master_wb = tmp_path / "data" / "master" / "pollitik_master.xlsx"
    master_wb.write_bytes(b"pretend workbook bytes")
    staging = tmp_path / "data" / "staging" / "candidates.jsonl"
    staging.write_text('{"fake": "candidate"}\n', encoding="utf-8")
    domains = tmp_path / "config" / "allowed_domains.txt"
    domains.write_text("approved-pollster.example\n", encoding="utf-8")
    canada_agents = tmp_path / "countries" / "canada" / "AGENTS.md"
    canada_agents.write_text("# real Canada blueprint content\n", encoding="utf-8")

    watched = [master_wb, staging, domains, canada_agents]
    before = _hash_tree(watched)

    result = icw.init_country_workspace("Australia", project_dir=str(tmp_path))
    assert result["created"] is True

    after = _hash_tree(watched)
    assert before == after, "no untouched path may change"
    # And the Canada folder gained no new files either.
    assert sorted(p.name for p in (tmp_path / "countries" / "canada").iterdir()) == ["AGENTS.md"]


# --------------------------------------------------------------------
# 7. Unsafe country names never write anything (path-traversal guard).
# --------------------------------------------------------------------

def test_rejects_unsafe_slug_without_writing_anything(tmp_path):
    with pytest.raises(icw.InitError):
        icw.init_country_workspace("../../evil", project_dir=str(tmp_path))
    assert not (tmp_path / "countries").exists()


# --------------------------------------------------------------------
# 8. Preflight after initialization: clean structured setup/reference-
#    discovery-required state, never a traceback, never fabricated data.
# --------------------------------------------------------------------

def test_preflight_after_init_reports_clean_setup_required_state(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# repo map (test fixture)\n", encoding="utf-8")
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / "allowed_domains.txt").write_text(
        "approved-pollster.example\n", encoding="utf-8"
    )

    init_result = icw.init_country_workspace("Australia", project_dir=str(tmp_path))
    assert init_result["created"] is True

    proc = run_script(
        "check_assignment_preflight.py", tmp_path, args=["--country", "Australia"]
    )
    assert "Traceback" not in proc.stderr
    result = json.loads(proc.stdout)

    assert result["country_agents_md_exists"] is True
    assert result["reference_data_status"] == "NO_REFERENCE_DATA"
    assert result["SAFE_TO_RESEARCH"] is False
    assert result["reason"] is not None
    assert proc.returncode == 1


def test_preflight_after_init_never_fabricates_a_reference_index(tmp_path):
    """init_country_workspace.py must not build/create a reference index
    or snapshot itself - only preflight/build_reference_index.py may,
    and only from real data."""
    (tmp_path / "AGENTS.md").write_text("# repo map (test fixture)\n", encoding="utf-8")
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / "allowed_domains.txt").write_text(
        "approved-pollster.example\n", encoding="utf-8"
    )
    icw.init_country_workspace("Australia", project_dir=str(tmp_path))
    assert not (tmp_path / "data" / "reference_index.duckdb").exists()


# --------------------------------------------------------------------
# 9. CLI smoke test (subprocess), matching the style of the other
#    python/*.py scripts' tests.
# --------------------------------------------------------------------

def test_cli_creates_workspace_and_reports_json(tmp_path):
    proc = run_script("init_country_workspace.py", tmp_path, args=["--country", "Australia"])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["created"] is True
    assert (tmp_path / "countries" / "australia" / "AGENTS.md").is_file()


def test_cli_second_run_exits_nonzero_without_traceback(tmp_path):
    run_script("init_country_workspace.py", tmp_path, args=["--country", "Australia"])
    proc = run_script("init_country_workspace.py", tmp_path, args=["--country", "Australia"])
    assert proc.returncode == 1
    assert "Traceback" not in proc.stderr
    result = json.loads(proc.stdout)
    assert result["created"] is False


# --------------------------------------------------------------------
# 10. Generated AGENTS.md documents the corrected student-data policy
#     and unchanged production protection for the new country too.
# --------------------------------------------------------------------

def test_generated_agents_md_documents_student_data_as_visible(tmp_path):
    icw.init_country_workspace("Australia", project_dir=str(tmp_path))
    agents_md = (tmp_path / "countries" / "australia" / "AGENTS.md").read_text(encoding="utf-8")
    section = agents_md[agents_md.index("Student data-access policy"):]
    assert "learning material, not secret data" in section
    assert "shown, explained, or provided to the student on request" in section


def test_generated_agents_md_documents_production_data_protected(tmp_path):
    icw.init_country_workspace("Australia", project_dir=str(tmp_path))
    agents_md = (tmp_path / "countries" / "australia" / "AGENTS.md").read_text(encoding="utf-8")
    section = agents_md[agents_md.index("Student data-access policy"):]
    assert "production/master Pollitik workbook" in section
    assert "stay protected" in section


# --------------------------------------------------------------------
# 11. Root-level documentation proves the natural-language routing rule
#     exists and correctly requires more than folder non-existence.
# --------------------------------------------------------------------

ROOT_AGENTS_MD = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
COUNTRY_BLUEPRINT = (REPO_ROOT / "docs" / "country_blueprint.md").read_text(encoding="utf-8")


def _normalize(text):
    return re.sub(r"\s+", " ", text)


def test_root_agents_md_documents_creation_routing_rule():
    assert "Creating a new country workspace" in ROOT_AGENTS_MD
    section = ROOT_AGENTS_MD[ROOT_AGENTS_MD.index("Creating a new country workspace"):]
    assert "python python/init_country_workspace.py --country" in section
    assert "**stop**" in section


def test_root_agents_md_requires_more_than_folder_nonexistence_for_creation_intent():
    section = _normalize(ROOT_AGENTS_MD[ROOT_AGENTS_MD.index("Creating a new country workspace"):])
    assert "never sufficient evidence of creation intent" in section
    assert "What do we know about polling in Australia?" in section
    assert "must never itself trigger file creation" in section


def test_root_agents_md_documents_creation_and_research_as_separate_actions():
    section = _normalize(ROOT_AGENTS_MD[ROOT_AGENTS_MD.index("Creating a new country workspace"):])
    assert "creating a workspace and running the research assignment are two separate actions" in section


def test_country_blueprint_points_at_the_initializer_script():
    assert "python python/init_country_workspace.py --country" in COUNTRY_BLUEPRINT
    assert "refuses to overwrite an existing" in COUNTRY_BLUEPRINT
