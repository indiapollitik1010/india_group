#!/usr/bin/env python3
"""Create a new country's assignment workspace skeleton.

Step 1 of the country-scaffolding architecture (see
docs/country_blueprint.md and docs/student_workflow.md): the Canada
blueprint (countries/canada/) is the completed, worked-example country
assignment. This script is the deterministic, tested equivalent of
"copy the directory, then edit the country-specific content" - it
creates the same nine-file skeleton described in
docs/country_blueprint.md for a NEW country, without ever copying any
of the Canada blueprint's actual content into it.

What this script does:

  - Normalizes the country name to the same countries/<slug>/ folder
    convention python/check_assignment_preflight.py already uses -
    imported from there directly (see normalize_country_slug below),
    never reimplemented, so the two scripts can never disagree about
    what a country's slug is.
  - Refuses to touch anything if countries/<slug>/ already exists - no
    silent overwrite, ever. Re-running this script against an existing
    country workspace is a safe no-op that reports why it did nothing.
  - Writes exactly nine files (see TEMPLATES below), all generic,
    templated content with only the country name/slug substituted in.
  - Never writes polling data, series, pollsters, sources, an
    executive's name, a reference snapshot, or Assignment-1 results -
    those all require real, country-specific research and must never
    be fabricated (the canonical Skill's "never guess" rule applies to
    workspace scaffolding exactly as much as to a research candidate).
  - Never creates a country Skill (.claude/skills/<slug>-*-approval/)
    or a reference profile - both require real judgment about that
    country's political system, which this script has no way to
    determine and must not guess at.
  - Never writes outside countries/<slug>/ - data/master/,
    data/staging/, config/, and every other country's folder are
    completely untouched; this script doesn't import or call anything
    that could write to them.
  - Validates every rendered file's content BEFORE writing anything
    (render_files() below), including a guard against any accidental
    literal "Canada" outside an allowed "Canada blueprint" phrase - so
    a template bug fails loudly instead of silently leaking a stray
    reference into a new country's files.

What this script deliberately does NOT do:

  - It does not run preflight, fetch the web, or start research.
    Creating a workspace and running the research assignment are
    separate actions (see the root AGENTS.md "Creating a new country
    workspace" rule) - this script only ever creates the skeleton and
    stops.
  - It does not decide whether a student's prompt actually means
    "create a workspace" vs. "ask a question about a country" - that
    routing decision belongs to whatever calls this script (Codex,
    per the root AGENTS.md rule), not to this script itself.

Usage:
    python python/init_country_workspace.py --country Australia
"""

import argparse
import json
import os
import re
import sys

import pollitik_common as pc
from check_assignment_preflight import normalize_country_slug


class InitError(Exception):
    """A clearly-reportable setup problem. Always caught in main() and
    printed as one clean JSON error, never an unhandled traceback."""


# Folder names under countries/ must stay simple and predictable - no
# path separators, no "..", nothing that could make os.path.join(...)
# escape countries/<slug>/. normalize_country_slug() only lowercases,
# strips outer whitespace, and hyphenates internal whitespace, so this
# is a separate, additional check (e.g. against punctuation it leaves
# untouched, like "Bosnia & Herzegovina").
_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$")


def _validate_slug(slug):
    if not _SLUG_RE.match(slug):
        raise InitError(
            "'{}' does not normalize to a safe countries/<slug>/ folder "
            "name (letters, digits, '-', '_' only, must start and end "
            "with a letter or digit). Refusing to create anything."
            .format(slug)
        )


# Every generated file may reference the completed Canada blueprint/
# example assignment by name, but never anything else about Canada -
# no data, series, pollster, source, or executive name should ever be
# templated in. "Canada" is only allowed immediately before "blueprint"
# or "example" (e.g. "the Canada blueprint", "the Canada example
# assignment") - any other occurrence is treated as an accidental leak.
_STRAY_CANADA_RE = re.compile(r"canada(?!\s+(?:blueprint|example))", re.IGNORECASE)


def assert_no_stray_canada(label, text):
    match = _STRAY_CANADA_RE.search(text)
    if match:
        start = max(match.start() - 40, 0)
        end = min(match.end() + 40, len(text))
        context = text[start:end].replace("\n", " ")
        raise InitError(
            "Generated content for '{}' contains a literal 'Canada' "
            "outside an allowed 'Canada blueprint'/'Canada example' "
            "phrase - refusing to write it. Context: ...{}..."
            .format(label, context)
        )


_AGENTS_MD_TEMPLATE = """\
# AGENTS.md — %%COUNTRY%% assignment (SETUP REQUIRED)

Narrows the root `AGENTS.md` and `CLAUDE.md` to this one country
assignment, the same way every other country's `AGENTS.md` narrows
them. This file was generated by `python/init_country_workspace.py` as
a skeleton - it does not yet define a working assignment. Nothing in it
should be treated as researched, approved, or safe to act on until a
human resolves every SETUP REQUIRED item below.

This structure follows the Canada blueprint (see
`docs/country_blueprint.md`) - the completed, worked-example country
assignment used as the template for every new country. No data, series,
pollsters, sources, executive name, reference profile, or results from
the Canada blueprint are copied into this file or anywhere else in this
workspace. Everything below must come from real %%COUNTRY%% research.

## SETUP REQUIRED — assignment scope

- Which executive office does this assignment cover (President, Prime
  Minister, Chancellor, or an equivalent office)? **Not yet
  determined.**
- Which support-measure types are in scope (job approval, favorability,
  satisfaction, performance, etc.)? **Not yet determined.**
- Which series/questions are explicitly excluded (government-as-a-whole
  approval, issue-specific approval, vote-intention, trust/confidence
  unless `config/country_rules.yaml` grants an exception for
  %%COUNTRY%%)? **Not yet determined - do not assume the Canada
  blueprint's exclusions apply here without re-confirming them for
  %%COUNTRY%% specifically.**

Once resolved, state the scope here in the same shape the Canada
blueprint's own country `AGENTS.md` uses (a short "Scope" section) -
see `docs/country_blueprint.md` for the pattern.

## SETUP REQUIRED — reference profile and Skill

- No reference profile exists yet for %%COUNTRY%%. Build one only from
  real %%COUNTRY%% data (the master workbook,
  `python/reference_lookup.py --country %%COUNTRY%%`, or genuine
  research) - never from general knowledge, and never by copying the
  Canada blueprint's reference profile.
- No country-specific Skill exists yet for %%COUNTRY%%. Create one
  under `.claude/skills/` (analogous to the Canada blueprint's country
  Skill) only once the scope above is resolved - this initializer
  deliberately does not create it, since it requires real judgment
  about %%COUNTRY%%'s political system that must not be guessed.

## SETUP REQUIRED — reference data

- `countries/%%SLUG%%/data/%%SLUG%%_reference_snapshot.csv` does not
  exist yet. It must be exported from real %%COUNTRY%% rows in the
  master workbook (see `docs/country_blueprint.md`) - never fabricated,
  never copied from the Canada blueprint's snapshot.
- Until it exists, `python python/check_assignment_preflight.py
  --country %%COUNTRY%%` will correctly report `NO_REFERENCE_DATA` (or
  `MASTER_ONLY_INDEX_BUILDABLE` if the master workbook already has
  %%COUNTRY%% rows) and `SAFE_TO_RESEARCH=false`. **This is the
  expected, correct state for a freshly initialized country - do not
  fetch the web or stage anything until it changes.**

## SETUP REQUIRED — approved sources

`config/allowed_domains.txt` is shared across every country and is not
edited by this initializer. No domain in it is assumed relevant to
%%COUNTRY%% just because it is approved for another country. Once real
%%COUNTRY%% sources are found, curate the relevant subset here - do not
assume the Canada blueprint's pollsters or media sources apply.

## Assignment-1 outputs

No tracked worked-example results exist yet for %%COUNTRY%%
(`%%SLUG%%_assignment1_approved.csv` / `..._review.csv`). These files
are only ever produced by `python/build_country_assignment_snapshot.py`
from a real, completed local research/staging run for %%COUNTRY%% -
never hand-written, never copied from the Canada blueprint's results.

## Student data-access policy

Same policy as every other country (see `docs/student_workflow.md`,
"Student data-access policy"): a student's own %%COUNTRY%% assignment
data - their APPROVED results, REVIEW results and validation reasons,
and the underlying rows - is learning material, not secret data. It may
be shown, explained, or provided to the student on request once real
data exists. Only the production/master Pollitik workbook, and other
students'/countries' data, stay protected.

## Where to go next

- `docs/country_blueprint.md` - the full structure this workspace
  follows and what's shared vs. country-specific.
- `docs/student_workflow.md` - the pipeline this assignment will run
  once the SETUP REQUIRED items above are resolved.
- `countries/%%SLUG%%/prompts/run_assignment.txt` - the same
  short-prompt pattern every country uses, already updated for
  %%COUNTRY%%.
"""

_README_TEMPLATE = """\
# %%COUNTRY%% — assignment (SETUP REQUIRED)

This workspace was generated by `python/init_country_workspace.py`
using the same structure as the Canada blueprint (see
`docs/country_blueprint.md`, the completed worked-example country
assignment). It is a skeleton, not a working assignment yet: read
`countries/%%SLUG%%/AGENTS.md` before doing any work here, and resolve
every SETUP REQUIRED item there first.

## What this assignment is

Not yet defined. Once the assignment scope is resolved (which
executive office, which support-measure types), describe it here the
same way the Canada blueprint's own country `README.md` describes its
assignment.

## Where the data actually lives

No %%COUNTRY%%-specific data exists yet:

- No reference snapshot (`%%SLUG%%_reference_snapshot.csv`).
- No tracked Assignment-1 results (`%%SLUG%%_assignment1_approved.csv`
  / `..._review.csv`).

These are only ever created from real %%COUNTRY%% research and results
- see `docs/country_blueprint.md` and the SETUP REQUIRED notes in
`countries/%%SLUG%%/AGENTS.md`. Once real data exists, it lives in the
same shared, country-agnostic locations every country uses
(`data/staging/`, `data/processed/`, `data/master/`) - see
`countries/%%SLUG%%/data/README.md` and
`countries/%%SLUG%%/output/README.md`.

## How a student runs the workflow

1. Resolve the SETUP REQUIRED items in `countries/%%SLUG%%/AGENTS.md`
   first (scope, reference profile, country Skill, reference data,
   approved sources). None of this happens automatically, and Codex
   must not guess any of it.
2. Once resolved, use the prompts in `countries/%%SLUG%%/prompts/` -
   see `docs/prompt_guide.md` for how short prompts work in this
   project.
"""

_RUN_ASSIGNMENT_TEMPLATE = """\
Run the %%COUNTRY%% executive-approval assignment using the repo workflow.

SETUP REQUIRED: this country workspace was generated by
python/init_country_workspace.py and has not yet been configured for
real research (see the SETUP REQUIRED sections in
countries/%%SLUG%%/AGENTS.md). Before doing anything else, confirm
whether assignment scope, reference profile, country Skill, reference
data, and approved sources have been resolved. If any are still
unresolved, stop and report exactly which ones instead of proceeding.

Once configured, follow the same steps every country's assignment uses:
First run `python python/check_python_dependencies.py`.
- If it reports dependencies_ready=false, STOP before preflight and before any research or staging. This is an environment/setup problem, not a data problem. Tell the student to run `pip install -r requirements.txt` once, from the repo root, then retry - never install packages yourself, and never record a NOT_FOUND/REVIEW/REJECTED observation because of it.
- Only once it reports dependencies_ready=true, continue: run `python python/check_assignment_preflight.py --country %%COUNTRY%%`.
- If it reports SAFE_TO_RESEARCH=true, continue directly.
- If it reports reference_data_status=COUNTRY_SNAPSHOT_BUILDABLE, build the local reference index from the tracked snapshot using the exact command in its `suggested_index_build_command` field, then re-run the preflight check. Do not start research until that re-run reports SAFE_TO_RESEARCH=true.
- If it reports reference_data_status=NO_REFERENCE_DATA, that is the expected state for a freshly initialized country until the SETUP REQUIRED reference data above is resolved - stop and report it, do not fetch the web or stage anything.
- If it still reports SAFE_TO_RESEARCH=false for any other reason, stop and report the reason instead of researching or staging anything.
Only once SAFE_TO_RESEARCH=true, inspect the existing assignment/reference state and continue with research on approved domains. Do this automatically - never ask the student to type the build command themselves.
"""

_CONTINUE_RESEARCH_TEMPLATE = """\
Continue the next %%COUNTRY%% source batch: resume research at the
next unresolved batch instead of restarting from scratch. Run the same
dependency check and preflight steps as
countries/%%SLUG%%/prompts/run_assignment.txt first; stop if any SETUP
REQUIRED item in countries/%%SLUG%%/AGENTS.md is still unresolved, or
if SAFE_TO_RESEARCH is false.
"""

_REVIEW_RESULTS_TEMPLATE = """\
Show current %%COUNTRY%% assignment results: APPROVED/REVIEW/REJECTED
counts, and what the REVIEW cases need. Resolve the dataset via
`python python/resolve_assignment_dataset.py --country %%COUNTRY%%
--purpose approved` and `--purpose review`, the same way every country
resolves it - never guess which file answers the question. If no local
or tracked results exist yet for %%COUNTRY%%, say so plainly instead of
fabricating a summary.
"""

_RECOMMEND_GRAPHS_TEMPLATE = """\
Recommend graphs for the current %%COUNTRY%% APPROVED results. Resolve
the current APPROVED dataset via `python
python/resolve_assignment_dataset.py --country %%COUNTRY%% --purpose
approved`, rank the top eligible graph types from
`config/visualization_rules.yaml`, and present them as a numbered,
human-readable list (never an internal graph type id). Generate nothing
yet. If no APPROVED %%COUNTRY%% data exists yet, say so plainly instead
of recommending against empty or fabricated data.
"""

_GENERATE_GRAPH_TEMPLATE = """\
Generate the %%COUNTRY%% graph the student picked from the saved
recommendation state (by option number, display name, or natural
description) using `python python/generate_visualization.py`, against
the resolved APPROVED dataset for %%COUNTRY%%
(`python/resolve_assignment_dataset.py --country %%COUNTRY%% --purpose
approved`). Never guess an ambiguous reply; ask again with the same
numbered list instead.
"""

_DATA_README_TEMPLATE = """\
# %%COUNTRY%% data

This folder is organizational/student-facing only, the same as every
other country's `data/README.md` in the Canada blueprint structure.
Nothing should be copied in here except the same two kinds of tracked
exceptions every country has, and only once they are genuinely built
for %%COUNTRY%%:

- `%%SLUG%%_reference_snapshot.csv` - **SETUP REQUIRED, does not exist
  yet.** Must be a real, tracked, read-only export of %%COUNTRY%%'s
  existing reference observations from the master workbook (see
  `docs/country_blueprint.md`) - never fabricated, never copied from
  the Canada blueprint's snapshot.
- `%%SLUG%%_assignment1_approved.csv` / `%%SLUG%%_assignment1_review.csv`
  - **SETUP REQUIRED, do not exist yet.** Only ever built by
  `python/build_country_assignment_snapshot.py` from a real, completed
  local research/staging run for %%COUNTRY%%.

## Real data locations

Same shared, country-agnostic locations every country uses:

- `data/reference_index.duckdb` - local reference index, queried via
  `python/reference_lookup.py --country %%COUNTRY%%`.
- `data/master/pollitik_master.xlsx` - the production workbook.
  Read-only except via `python/apply_changes.py`.
- `data/staging/candidates.jsonl` - every %%COUNTRY%% candidate that
  has gone through validation.
- `data/cache/sources.jsonl` - already-verified retrievals.

Do not create a %%COUNTRY%%-specific copy of `data/master/` or
`data/staging/` here - see `docs/country_blueprint.md` for why those
stay shared.
"""

_OUTPUT_README_TEMPLATE = """\
# %%COUNTRY%% output (placeholder folder)

This folder is organizational/student-facing only - it does not hold
any real output files yet, the same as every other country's
`output/README.md` in the Canada blueprint structure. Nothing should be
copied into it.

## Real output locations (once real %%COUNTRY%% research has run)

- `data/processed/%%SLUG%%_assignment1/` - full staging-schema audit
  trail for a real research run.
- `data/processed/%%SLUG%%_pm_approval_main.csv` / `..._review.csv` -
  the visualization-ready APPROVED/REVIEW datasets (local run) that
  `python/resolve_assignment_dataset.py` and
  `python/build_country_assignment_snapshot.py` look for by default.
  These default filenames currently assume a Prime-Minister-shaped
  pipeline (a convention inherited from the Canada blueprint) - if
  %%COUNTRY%%'s office is not a Prime Minister, pass that script's
  explicit `--*-input`/`--local-path`/`--tracked-path` overrides
  instead of assuming the default names apply.
- `countries/%%SLUG%%/data/%%SLUG%%_assignment1_approved.csv` /
  `..._review.csv` - tracked worked-example snapshot, once built by
  `python/build_country_assignment_snapshot.py`.
- `data/processed/visualizations/` - generated charts.

`python/resolve_assignment_dataset.py --country %%COUNTRY%% --purpose
approved` (and `--purpose review`) is the single deterministic decider
for which file answers a student's question, exactly as it is for every
other country.
"""

TEMPLATES = {
    "AGENTS.md": _AGENTS_MD_TEMPLATE,
    "README.md": _README_TEMPLATE,
    "prompts/run_assignment.txt": _RUN_ASSIGNMENT_TEMPLATE,
    "prompts/continue_research.txt": _CONTINUE_RESEARCH_TEMPLATE,
    "prompts/review_results.txt": _REVIEW_RESULTS_TEMPLATE,
    "prompts/recommend_graphs.txt": _RECOMMEND_GRAPHS_TEMPLATE,
    "prompts/generate_graph.txt": _GENERATE_GRAPH_TEMPLATE,
    "data/README.md": _DATA_README_TEMPLATE,
    "output/README.md": _OUTPUT_README_TEMPLATE,
}


def render_files(country, slug):
    """Returns {relative_path: content} for every file this script
    creates, fully rendered (placeholders substituted) and verified to
    contain no accidental literal 'Canada' outside an allowed phrase.
    Pure function - no filesystem access - so every template can be
    validated before anything is written to disk."""
    rendered = {}
    for relative_path, template in TEMPLATES.items():
        content = template.replace("%%COUNTRY%%", country).replace("%%SLUG%%", slug)
        assert_no_stray_canada(relative_path, content)
        rendered[relative_path] = content
    return rendered


def init_country_workspace(country, project_dir=None):
    """Create countries/<slug>/ with the nine-file skeleton, or report
    why it refused to. Never partially writes: every file is rendered
    and validated (render_files) before any file is written, and the
    existing-directory check happens before rendering."""
    project_dir = project_dir or pc.PROJECT_DIR

    # Resolve aliases (e.g. "UK" -> "United Kingdom") through the one
    # centralized resolver in pollitik_common.py - never reimplemented
    # here - so the folder this creates is the same countries/<slug>/
    # every other pipeline script (build_country_reference_snapshot.py,
    # build_country_ead_snapshot.py, check_assignment_preflight.py, ...)
    # will look for. A deliberately-ambiguous input (bare "France") is
    # refused the same way an invalid slug already is (InitError).
    try:
        resolved_country = pc.resolve_country_input(country)
        slug = pc.canonical_country_slug(country)
    except pc.AmbiguousCountryError as exc:
        raise InitError(str(exc))
    _validate_slug(slug)

    country_dir = os.path.join(project_dir, "countries", slug)
    country_dir_abs = os.path.abspath(country_dir)

    if os.path.isdir(country_dir):
        return {
            "created": False,
            "country": country,
            "resolved_country": resolved_country,
            "country_slug": slug,
            "country_dir": country_dir,
            "reason": (
                "countries/{}/ already exists - refusing to overwrite it. "
                "Remove or rename it first if you really want to recreate "
                "this workspace from scratch.".format(slug)
            ),
        }

    rendered = render_files(country, slug)

    files_created = []
    for relative_path, content in rendered.items():
        full_path = os.path.join(country_dir, relative_path)
        full_path_abs = os.path.abspath(full_path)
        # Defense in depth: every path this script writes must stay
        # under country_dir, even if a future template/slug change
        # somehow tried to escape it.
        if os.path.commonpath([full_path_abs, country_dir_abs]) != country_dir_abs:
            raise InitError(
                "Refusing to write outside the new country directory: "
                "'{}'.".format(full_path)
            )
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        files_created.append(
            os.path.join("countries", slug, relative_path).replace("\\", "/")
        )

    return {
        "created": True,
        "country": country,
        "resolved_country": resolved_country,
        "country_slug": slug,
        "country_dir": country_dir,
        "files_created": sorted(files_created),
        "reference_data_created": False,
        "assignment1_results_created": False,
        "skill_created": False,
        "reference_profile_created": False,
        "setup_required": [
            "Define assignment scope (executive office, eligible/excluded "
            "series) in countries/{}/AGENTS.md.".format(slug),
            "Build a real reference profile and country Skill from genuine "
            "{} research - never invented.".format(country),
            "Export a real reference snapshot from the master workbook once "
            "{} rows exist there, or confirm none exist yet.".format(country),
            "Curate which entries in config/allowed_domains.txt are "
            "relevant to {}.".format(country),
        ],
        "next_check": (
            "python python/check_assignment_preflight.py --country {}"
            .format(country)
        ),
        "note": (
            "This only creates the workspace skeleton. It does not run "
            "preflight, fetch the web, or research anything - run the "
            "command above next, and expect SAFE_TO_RESEARCH=false until "
            "the setup_required items are resolved."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--country", required=True, help="e.g. Australia")
    args = parser.parse_args(argv)

    try:
        result = init_country_workspace(args.country)
    except InitError as exc:
        print(json.dumps({"created": False, "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["created"] else 1


if __name__ == "__main__":
    sys.exit(main())
