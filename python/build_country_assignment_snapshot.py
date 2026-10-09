#!/usr/bin/env python3
"""Build a country's tracked, student-facing Assignment-1 snapshot files
(countries/<country>/data/<country>_assignment1_approved.csv and
..._review.csv) from that country's real local pipeline outputs.

This is a maintainer/build-time tool, analogous to
python/build_reference_index.py and the way
countries/canada/data/canada_reference_snapshot.csv was first produced:
run once (by hand, by the project owner) when a country's finalized
assignment results materially change, never by a student workspace, and
never as part of the student-facing runtime pipeline
(python/resolve_assignment_dataset.py, python/generate_visualization.py).

It never invents a value. Every row in the APPROVED output is copied
verbatim from the local visualization-ready APPROVED CSV. Every row in
the REVIEW output is copied verbatim from the local visualization-ready
REVIEW CSV, with exactly one field added - Validation Reason - joined
from the local audit-schema REVIEW CSV (the one with `validation_reason`)
by matching Source URL. If any REVIEW row's source cannot be matched to
an audit row, this script fails loudly (a clear reported list, not an
unhandled traceback) rather than leaving a blank or guessed reason.

Default input/output paths follow the existing per-country conventions:

  local approved (viz-ready):  data/processed/<slug>_pm_approval_main.csv
  local review (viz-ready):    data/processed/<slug>_pm_approval_review.csv
  local review (audit, has
    validation_reason):        data/processed/<slug>_assignment1/<slug>_pm_review.csv

  tracked approved (output):   countries/<slug>/data/<slug>_assignment1_approved.csv
  tracked review (output):     countries/<slug>/data/<slug>_assignment1_review.csv

Usage:
    python python/build_country_assignment_snapshot.py --country Canada
"""

import argparse
import csv
import json
import os
import sys

import pollitik_common as pc

APPROVED_FIELDS = ["Date", "Approval", "Prime Minister", "Party", "Series", "Source", "Status"]
REVIEW_FIELDS = APPROVED_FIELDS + ["Validation Reason"]


class SnapshotBuildError(Exception):
    """A clearly-reportable data problem. Always caught in main() and
    printed as a single clean error line - never an unhandled traceback,
    and never a guessed/invented value."""


def default_paths(project_dir, slug):
    return {
        "approved_input": os.path.join(project_dir, "data", "processed", "{}_pm_approval_main.csv".format(slug)),
        "review_input": os.path.join(project_dir, "data", "processed", "{}_pm_approval_review.csv".format(slug)),
        "review_audit_input": os.path.join(
            project_dir, "data", "processed", "{}_assignment1".format(slug), "{}_pm_review.csv".format(slug)
        ),
        "approved_output": os.path.join(project_dir, "countries", slug, "data", "{}_assignment1_approved.csv".format(slug)),
        "review_output": os.path.join(project_dir, "countries", slug, "data", "{}_assignment1_review.csv".format(slug)),
    }


def read_csv_rows(path):
    if not os.path.isfile(path):
        raise SnapshotBuildError("Required input file does not exist: '{}'.".format(path))
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []
    return rows, fieldnames


def build_approved(approved_input):
    rows, fieldnames = read_csv_rows(approved_input)
    missing = [c for c in APPROVED_FIELDS if c not in fieldnames]
    if missing:
        raise SnapshotBuildError(
            "'{}' is missing required column(s): {}.".format(approved_input, ", ".join(missing))
        )
    non_approved = [r for r in rows if (r.get("Status") or "").strip() != "APPROVED"]
    if non_approved:
        raise SnapshotBuildError(
            "'{}' contains {} row(s) with Status != APPROVED; this input must be "
            "APPROVED-only.".format(approved_input, len(non_approved))
        )
    if not rows:
        raise SnapshotBuildError("'{}' has no data rows.".format(approved_input))
    return [{k: r.get(k, "") for k in APPROVED_FIELDS} for r in rows]


def _audit_reason_index(review_audit_input):
    """Keyed by every URL an audit row could plausibly be found under
    (source_url and final_url, whichever are non-blank) - the local
    audit REVIEW file sometimes has source_url blank with only final_url
    populated (see canada_pm_review.csv's SparkInsights row)."""
    rows, fieldnames = read_csv_rows(review_audit_input)
    required = ["series", "source_url", "final_url", "validation_reason"]
    missing = [c for c in required if c not in fieldnames]
    if missing:
        raise SnapshotBuildError(
            "'{}' is missing required column(s): {}.".format(review_audit_input, ", ".join(missing))
        )
    index = {}
    for r in rows:
        reason = (r.get("validation_reason") or "").strip()
        for url_field in ("source_url", "final_url"):
            url = (r.get(url_field) or "").strip()
            if url:
                index[(("series", (r.get("series") or "").strip()), url)] = reason
                index[("any_series", url)] = reason
    return index


def build_review(review_input, review_audit_input):
    rows, fieldnames = read_csv_rows(review_input)
    missing = [c for c in APPROVED_FIELDS if c not in fieldnames]
    if missing:
        raise SnapshotBuildError(
            "'{}' is missing required column(s): {}.".format(review_input, ", ".join(missing))
        )
    non_review = [r for r in rows if (r.get("Status") or "").strip() != "REVIEW"]
    if non_review:
        raise SnapshotBuildError(
            "'{}' contains {} row(s) with Status != REVIEW; this input must be "
            "REVIEW-only.".format(review_input, len(non_review))
        )
    if not rows:
        raise SnapshotBuildError("'{}' has no data rows.".format(review_input))

    reason_index = _audit_reason_index(review_audit_input)

    out_rows = []
    unmatched = []
    for i, r in enumerate(rows):
        series = (r.get("Series") or "").strip()
        source = (r.get("Source") or "").strip()
        reason = reason_index.get((("series", series), source))
        if reason is None:
            reason = reason_index.get(("any_series", source))
        if reason is None:
            unmatched.append("row {} (Series={!r}, Source={!r})".format(i + 1, series, source))
            reason = ""
        out_row = {k: r.get(k, "") for k in APPROVED_FIELDS}
        out_row["Validation Reason"] = reason
        out_rows.append(out_row)

    if unmatched:
        raise SnapshotBuildError(
            "Could not find a matching validation reason in '{}' for {} REVIEW row(s) - "
            "refusing to invent a reason:\n  {}".format(
                review_audit_input, len(unmatched), "\n  ".join(unmatched)
            )
        )
    return out_rows


def write_csv(path, rows, fields):
    out_dir = os.path.dirname(os.path.abspath(path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--country", required=True, help="e.g. Canada")
    parser.add_argument("--project-dir", default=os.getcwd(), help="Repo root (default: current directory).")
    parser.add_argument("--approved-input", default=None, help="Override local APPROVED viz-ready CSV path.")
    parser.add_argument("--review-input", default=None, help="Override local REVIEW viz-ready CSV path.")
    parser.add_argument("--review-audit-input", default=None, help="Override local REVIEW audit CSV path (has validation_reason).")
    parser.add_argument("--approved-output", default=None, help="Override tracked APPROVED output path.")
    parser.add_argument("--review-output", default=None, help="Override tracked REVIEW output path.")
    args = parser.parse_args(argv)

    # Resolve aliases (e.g. "UK" -> "United Kingdom") through the one
    # centralized resolver in pollitik_common.py - never reimplemented
    # here - so this lands in the same countries/<slug>/ folder every
    # other pipeline script uses for that country.
    try:
        slug = pc.canonical_country_slug(args.country)
    except pc.AmbiguousCountryError as exc:
        print("build_country_assignment_snapshot.py: ERROR: {}".format(exc), file=sys.stderr)
        return 1
    paths = default_paths(args.project_dir, slug)
    approved_input = args.approved_input or paths["approved_input"]
    review_input = args.review_input or paths["review_input"]
    review_audit_input = args.review_audit_input or paths["review_audit_input"]
    approved_output = args.approved_output or paths["approved_output"]
    review_output = args.review_output or paths["review_output"]

    try:
        approved_rows = build_approved(approved_input)
        review_rows = build_review(review_input, review_audit_input)
    except SnapshotBuildError as exc:
        print("build_country_assignment_snapshot.py: ERROR: {}".format(exc), file=sys.stderr)
        return 1

    write_csv(approved_output, approved_rows, APPROVED_FIELDS)
    write_csv(review_output, review_rows, REVIEW_FIELDS)

    summary = {
        "country": args.country,
        "country_slug": slug,
        "approved_input": approved_input,
        "review_input": review_input,
        "review_audit_input": review_audit_input,
        "approved_output": approved_output,
        "approved_row_count": len(approved_rows),
        "review_output": review_output,
        "review_row_count": len(review_rows),
        "review_reasons_matched": sum(1 for r in review_rows if r["Validation Reason"]),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
