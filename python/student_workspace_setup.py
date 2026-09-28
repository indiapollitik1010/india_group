#!/usr/bin/env python3
"""Dependency-free classroom setup: create a country workspace and build
its two student-facing snapshot CSVs, using ONLY the Python standard
library and the two tracked shared reference CSVs
(data/reference/pollitik_reference.csv,
data/reference/ead_series_question_wording.csv).

Why this script exists
-----------------------
A fresh student laptop can fail before a student ever does anything
research-related, if the workflow insists on `pip install -r
requirements.txt` (duckdb, pandas, PyYAML, openpyxl) just to:

  1. create a country workspace,
  2. generate the country's reference snapshot, and
  3. generate the country's EAD series/question-wording CSV.

None of those three steps actually needs any third-party package. This
script is the single, explicit, stdlib-only entry point for exactly that
slice of the student workflow - a thin wrapper around three already-
existing, already-tested functions:

  - init_country_workspace.init_country_workspace()
  - build_country_reference_snapshot.build()
  - build_country_ead_snapshot.build()

reused exactly as they are (same centralized alias/slug resolution via
pollitik_common.resolve_country_input()/canonical_country_slug(), same
France President vs. France Prime Minister disambiguation, same refusal
behavior on an existing file/workspace) rather than reimplementing any
of that logic here. This module itself imports nothing beyond the
standard library and the three modules above; none of those three
imports duckdb, pandas, PyYAML, or openpyxl at module level either -
openpyxl is imported lazily, only inside the branch that reads a real
data/master/*.xlsx workbook, which a student's fresh clone never has
(data/master/ is git-ignored). On a fresh clone, both snapshot builds
fall back to the two tracked shared CSVs above automatically.

What this script deliberately does NOT do:
  - It never runs python/check_python_dependencies.py or
    python/check_assignment_preflight.py - those gate the RESEARCH
    pipeline (the duckdb reference index, web fetch, matching, staging),
    which this script never touches.
  - It never fetches the web, stages a candidate, or writes to
    data/master/ or data/staging/.
  - It never overwrites an existing workspace, reference snapshot, or
    EAD snapshot unless --overwrite is passed (and --overwrite never
    applies to the workspace step, which never overwrites - same as
    init_country_workspace.py standalone).

See the root AGENTS.md "Classroom setup (dependency-free)" section and
docs/student_workflow.md for how this fits into the rest of the
pipeline.

Usage:
    python python/student_workspace_setup.py --country Argentina
    python python/student_workspace_setup.py --country UK --steps reference,ead
    python python/student_workspace_setup.py --country "France President"
"""

import argparse
import json
import os
import sys

import pollitik_common as pc
from init_country_workspace import init_country_workspace, InitError
from build_country_reference_snapshot import (
    build as build_reference_snapshot,
    default_output_path as reference_snapshot_path,
    SnapshotBuildError,
)
from build_country_ead_snapshot import (
    build as build_ead_snapshot,
    default_output_path as ead_snapshot_path,
    EadSnapshotBuildError,
)

ALL_STEPS = ["workspace", "reference", "ead"]


def _run_workspace_step(country, project_dir):
    try:
        result = init_country_workspace(country, project_dir=project_dir)
    except InitError as exc:
        return {"step": "workspace", "ok": False, "error": str(exc)}
    if result["created"]:
        return {
            "step": "workspace", "ok": True, "skipped": False,
            "country_slug": result["country_slug"], "country_dir": result["country_dir"],
            "files_created": result["files_created"],
        }
    return {
        "step": "workspace", "ok": True, "skipped": True,
        "country_slug": result["country_slug"], "country_dir": result["country_dir"],
        "reason": result["reason"],
    }


def _run_reference_step(country, project_dir, overwrite):
    try:
        slug = pc.canonical_country_slug(country)
    except pc.AmbiguousCountryError as exc:
        return {"step": "reference", "ok": False, "error": str(exc)}
    out_path = reference_snapshot_path(project_dir, slug)
    if os.path.exists(out_path) and not overwrite:
        return {
            "step": "reference", "ok": True, "skipped": True, "output_path": out_path,
            "reason": "'{}' already exists - pass --overwrite to rebuild it.".format(out_path),
        }
    try:
        result = build_reference_snapshot(
            country, pc.DEFAULT_MASTER_WORKBOOK, project_dir=project_dir, overwrite=overwrite,
        )
    except SnapshotBuildError as exc:
        return {"step": "reference", "ok": False, "error": str(exc)}
    return {"step": "reference", "ok": True, "skipped": False, **result}


def _run_ead_step(country, project_dir, overwrite):
    try:
        slug = pc.canonical_country_slug(country)
    except pc.AmbiguousCountryError as exc:
        return {"step": "ead", "ok": False, "error": str(exc)}
    out_path = ead_snapshot_path(project_dir, slug)
    if os.path.exists(out_path) and not overwrite:
        return {
            "step": "ead", "ok": True, "skipped": True, "output_path": out_path,
            "reason": "'{}' already exists - pass --overwrite to rebuild it.".format(out_path),
        }
    try:
        result = build_ead_snapshot(country, project_dir=project_dir, overwrite=overwrite)
    except EadSnapshotBuildError as exc:
        return {"step": "ead", "ok": False, "error": str(exc)}
    return {"step": "ead", "ok": True, "skipped": False, **result}


def run_student_setup(country, steps=None, project_dir=None, overwrite=False):
    """Runs the requested subset of {workspace, reference, ead} steps, in
    that fixed dependency order regardless of the order `steps` lists
    them in (a workspace must exist before either snapshot can be built).
    Stops at the first hard failure (does not attempt later steps), but
    an already-exists skip is never a failure. Pure orchestration - no
    step's own logic is reimplemented here."""
    project_dir = project_dir or pc.PROJECT_DIR
    steps = steps if steps is not None else ALL_STEPS

    unknown = [s for s in steps if s not in ALL_STEPS]
    if unknown:
        raise ValueError("Unknown step(s) {}: must be a subset of {}".format(unknown, ALL_STEPS))

    ordered = [s for s in ALL_STEPS if s in steps]

    results = {}
    for step in ordered:
        if step == "workspace":
            step_result = _run_workspace_step(country, project_dir)
        elif step == "reference":
            step_result = _run_reference_step(country, project_dir, overwrite)
        else:
            step_result = _run_ead_step(country, project_dir, overwrite)
        results[step] = step_result
        if not step_result["ok"]:
            break

    overall_ok = bool(results) and all(r["ok"] for r in results.values())
    return {"country": country, "steps_run": list(results.keys()), "ok": overall_ok, "results": results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--country", required=True, help='e.g. "Argentina", "UK", "France President"')
    parser.add_argument(
        "--steps", default="workspace,reference,ead",
        help="Comma-separated subset of workspace,reference,ead (default: all three).",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Rebuild an already-existing reference/EAD snapshot. Never applies to the workspace step.",
    )
    parser.add_argument("--project-dir", default=None)
    args = parser.parse_args(argv)

    steps = [s.strip() for s in args.steps.split(",") if s.strip()]
    try:
        result = run_student_setup(
            args.country, steps=steps, project_dir=args.project_dir, overwrite=args.overwrite,
        )
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, ensure_ascii=True))
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
