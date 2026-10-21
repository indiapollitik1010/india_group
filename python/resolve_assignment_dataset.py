#!/usr/bin/env python3
"""Deterministic result-precedence resolver for student-facing analysis
and visualization (see docs/student_workflow.md, countries/<country>/AGENTS.md).

A fresh clone of this repo ships a tracked, frozen worked-example result
per country (countries/<country>/data/<country>_assignment1_approved.csv
and ..._review.csv) alongside the real, gitignored pipeline outputs a
student's own session may produce (data/processed/<country>_pm_approval_main.csv
and ..._review.csv). Two files can legitimately exist for the same
purpose at once, and which one is "the" validated dataset for a given
question must never be left to model inference - this script is the
single deterministic answer:

  1. If a newer finalized local result exists in this workspace/session
     (data/processed/<country>_pm_approval_*.csv, newer than the tracked
     file), use it.
  2. Otherwise fall back to the tracked worked-example result under
     countries/<country>/data/.
  3. Never resolves to <country>_reference_snapshot.csv - that file is
     historical/reference data for duplicate-checking only, never
     completed assignment output, and this script has no code path that
     can return it.

This script is read-only: it only checks existence/mtime of the two
candidate paths and reports which one to use and why. It never builds,
fetches, or writes anything. Reference/duplicate lookup is a completely
separate tool (python/reference_lookup.py against the DuckDB index built
from <country>_reference_snapshot.csv) and never goes through this
resolver.

Usage:
    python python/resolve_assignment_dataset.py --country Canada --purpose approved
    python python/resolve_assignment_dataset.py --country Canada --purpose review
"""

import argparse
import json
import os
import sys

import pollitik_common as pc

PURPOSES = ("approved", "review")


def default_local_path(project_dir, slug, purpose):
    suffix = "main" if purpose == "approved" else "review"
    return os.path.join(project_dir, "data", "processed", "{}_pm_approval_{}.csv".format(slug, suffix))


def default_tracked_path(project_dir, slug, purpose):
    return os.path.join(project_dir, "countries", slug, "data", "{}_assignment1_{}.csv".format(slug, purpose))


def _usable(path):
    """Exists and is non-empty - an empty file left over from a failed
    run is never treated as a finalized result."""
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False


def resolve(country, purpose, project_dir=None, local_path=None, tracked_path=None):
    if purpose not in PURPOSES:
        raise ValueError("purpose must be one of {}, got {!r}".format(PURPOSES, purpose))

    project_dir = project_dir or pc.PROJECT_DIR

    # Resolve aliases (e.g. "UK" -> "United Kingdom") through the one
    # centralized resolver in pollitik_common.py - never reimplemented
    # here - so this looks in the same countries/<slug>/ folder every
    # other pipeline script uses for that country. This function never
    # raises (matches its own "read-only, reports why it can't resolve"
    # contract), so a deliberately-ambiguous input (bare "France") is
    # reported as an unresolved result instead of propagating.
    try:
        slug = pc.canonical_country_slug(country)
    except pc.AmbiguousCountryError as exc:
        return {
            "country": country,
            "country_slug": None,
            "purpose": purpose,
            "local_path": None,
            "local_exists": None,
            "tracked_path": None,
            "tracked_exists": None,
            "resolved_path": None,
            "source": None,
            "reason": str(exc),
            "resolved": False,
        }

    local_path = local_path or default_local_path(project_dir, slug, purpose)
    tracked_path = tracked_path or default_tracked_path(project_dir, slug, purpose)

    local_exists = _usable(local_path)
    tracked_exists = _usable(tracked_path)

    resolved_path = None
    source = None
    if local_exists and tracked_exists:
        if os.path.getmtime(local_path) > os.path.getmtime(tracked_path):
            resolved_path, source = local_path, "local_session_result"
            reason = (
                "A finalized local result exists at '{}' and is newer than the tracked "
                "worked-example snapshot - using the local result.".format(local_path)
            )
        else:
            resolved_path, source = tracked_path, "tracked_worked_example"
            reason = (
                "A local result exists at '{}' but is not newer than the tracked "
                "worked-example snapshot - using the tracked snapshot at '{}'.".format(
                    local_path, tracked_path
                )
            )
    elif local_exists:
        resolved_path, source = local_path, "local_session_result"
        reason = "Only a local finalized result exists in this workspace ('{}').".format(local_path)
    elif tracked_exists:
        resolved_path, source = tracked_path, "tracked_worked_example"
        reason = (
            "No local finalized result in this workspace; using the tracked "
            "worked-example snapshot at '{}'.".format(tracked_path)
        )
    else:
        reason = (
            "Neither a local finalized result ('{}') nor a tracked worked-example "
            "snapshot ('{}') exists for this country/purpose.".format(local_path, tracked_path)
        )

    return {
        "country": country,
        "country_slug": slug,
        "purpose": purpose,
        "local_path": local_path,
        "local_exists": local_exists,
        "tracked_path": tracked_path,
        "tracked_exists": tracked_exists,
        "resolved_path": resolved_path,
        "source": source,
        "reason": reason,
        "resolved": resolved_path is not None,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--country", required=True, help="e.g. Canada")
    parser.add_argument("--purpose", required=True, choices=PURPOSES,
                         help="'approved' for validated-data/graph questions, 'review' for REVIEW-awareness questions.")
    parser.add_argument("--local-path", default=None, help="Override the local result path (testing only).")
    parser.add_argument("--tracked-path", default=None, help="Override the tracked snapshot path (testing only).")
    args = parser.parse_args(argv)

    result = resolve(args.country, args.purpose, local_path=args.local_path, tracked_path=args.tracked_path)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["resolved"] else 1


if __name__ == "__main__":
    sys.exit(main())
