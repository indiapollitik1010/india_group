#!/usr/bin/env python3
"""Deterministic validation of a candidate Pollitik observation.

Implements the deterministic half of Skill sections 18 (arithmetic), 22
(sample size), 19-21 (fieldwork dates), 31-34 (source/evidence validation
and statuses), 45 (sample-size inference), 47 (net/app_app_dis), 48
(canonical wording inheritance), 55 (series matching with the EAD
reference workbook). The LLM/agents decide *which* response labels are
positive/negative/neutral
and *what* the series/country/wording are; this script only checks
arithmetic, required fields, and provenance, and assigns the final
validation_status. It never invents or corrects a value - it only
approves, flags for review, or rejects.

Required-field classification (config/schema_mapping.yaml is the
documented reference for this): only country and series are hard
REJECTED-required (check_required_identity). Negative, Neutral,
Sample_Size, and Pollster are optional/supporting - missing any of them
never rejects an otherwise valid record by itself. A missing Pollster
specifically routes to REVIEW via SERIES_REVIEW_REQUIRED
(check_pollster) rather than REJECTED, since Pollster's role is series
identification/matching, not a substantive measure of support.

check_ead_wording_match reads (never computes) `ead_wording_match_status`
- one of SERIES_MATCH_EXACT / SERIES_MATCH_NORMALIZED /
SERIES_MATCH_SUPPORTED / SERIES_REVIEW_REQUIRED - set by the matcher
after consulting python/ead_series_lookup.py against the authoritative
EAD Series/Question-Wording reference workbook
(docs/ead/reference/EAD Series and Question Wording.xlsx). That
workbook is reference material only, never itself evidence for a new
external observation; only SERIES_REVIEW_REQUIRED here affects
validation_status (REVIEW), and its absence is never penalized.

check_wording handles a separate, distinct mechanism: when the matcher
proposes `question_wording_status: INHERITED_FROM_SERIES_REFERENCE`
(Skill section 48), this script never accepts that assertion alone - it
independently re-derives eligibility via `verify_wording.py` against the
EAD reference workbook. Only a confirmed-eligible re-derivation sets the
informational `WORDING_INHERITED_FROM_SERIES_REFERENCE` flag; otherwise
it falls back to QUESTION_WORDING_UNKNOWN.

Expected input record shape (see Skill section 30 / README):

    {
      "country": "...", "series": "...", "pollster": "...",
      "question_wording_status": "EXACT_WORDING",
      "positive": 58, "negative": 36, "neutral": null,
      "response_categories": {"Very poorly": 14, "Poorly": 22,
                               "Well": 40, "Very well": 18},
      "category_classification": {"Very poorly": "negative",
                                   "Poorly": "negative",
                                   "Well": "positive",
                                   "Very well": "positive"},
      "sample_size": 1204,
      "sample_size_status": "INFERRED_FROM_FIRM_PATTERN",  # optional,
          # matcher-only, see Skill section 45 - omit when the sample
          # size was directly confirmed
      "fieldwork_date_normalized": "1/8/2026",
      "fieldwork_date_status": "OBSERVED",
      "requested_url": "...", "final_url": "...", "http_status": 200,
      "retrieved_at": "...", "evidence_text": "...",
      "not_found": false
    }

Output: the input record with "source_verified", "validation_status",
"validation_reason", "validation_flags", and the computed "net"/
"app_app_dis" summary fields (Skill section 47) filled in.
"""

import argparse
import json
import sys

import pollitik_common as pc
import verify_source
import verify_wording

ARITHMETIC_TOLERANCE = 1.0
WORDING_STATUSES = {
    "EXACT_WORDING", "PARTIAL_WORDING", "IMPLIED_WORDING", "UNKNOWN_WORDING",
    "INHERITED_FROM_SERIES_REFERENCE",
}
INHERITED_WORDING_STATUS = "INHERITED_FROM_SERIES_REFERENCE"


def check_arithmetic(record, flags):
    categories = record.get("response_categories")
    classification = record.get("category_classification")

    if not categories:
        flags.append("ARITHMETIC_REVIEW_REQUIRED")
        return ("ARITHMETIC_REVIEW_REQUIRED",
                "No response_categories components were preserved, so "
                "reported positive/negative/neutral cannot be "
                "deterministically re-derived.")

    if not classification:
        flags.append("RESPONSE_MAPPING_REVIEW_REQUIRED")
        return ("ARITHMETIC_REVIEW_REQUIRED",
                "response_categories were preserved but no "
                "category_classification mapping was provided.")

    sums = {"positive": 0.0, "negative": 0.0, "neutral": 0.0}
    unmapped = []
    for label, value in categories.items():
        bucket = classification.get(label)
        if bucket not in ("positive", "negative", "neutral"):
            if bucket not in (None, "nonresponse"):
                unmapped.append(label)
            continue
        if not pc.is_number(value):
            unmapped.append(label)
            continue
        sums[bucket] += pc.to_number(value)

    if unmapped:
        flags.append("RESPONSE_MAPPING_REVIEW_REQUIRED")
        return ("ARITHMETIC_REVIEW_REQUIRED",
                "Could not classify/sum categories: {}.".format(unmapped))

    diffs = {}
    for bucket in ("positive", "negative", "neutral"):
        reported = record.get(bucket)
        if reported is None:
            if sums[bucket] != 0:
                diffs[bucket] = (reported, sums[bucket])
            continue
        if not pc.is_number(reported):
            diffs[bucket] = (reported, sums[bucket])
            continue
        diffs[bucket] = (pc.to_number(reported), sums[bucket])

    max_abs_diff = 0.0
    mismatches = {}
    for bucket, (reported, computed) in diffs.items():
        if reported is None:
            continue
        d = abs(reported - computed)
        max_abs_diff = max(max_abs_diff, d)
        if d > 0:
            mismatches[bucket] = {"reported": reported, "computed": computed}

    if max_abs_diff == 0:
        return ("ARITHMETIC_OK", "Computed totals match reported values exactly.")
    if max_abs_diff <= ARITHMETIC_TOLERANCE:
        return ("ROUNDING_DIFFERENCE",
                "Computed totals differ from reported values by <= {} "
                "(normal survey rounding): {}".format(ARITHMETIC_TOLERANCE, mismatches))

    flags.append("ARITHMETIC_REVIEW_REQUIRED")
    return ("ARITHMETIC_REVIEW_REQUIRED",
            "Computed totals differ from reported values by more than "
            "the rounding tolerance: {}".format(mismatches))


def check_sample_size(record, flags):
    sample_size = record.get("sample_size")
    if record.get("sample_size_status") == "INFERRED_FROM_FIRM_PATTERN":
        # Skill section 45: a narrow, always-reviewed exception - only
        # the matcher may set this, and only after confirming the
        # pattern actually recurs via python/reference_lookup.py. Never
        # silently APPROVED regardless of how plausible the value looks.
        flags.append("SAMPLE_SIZE_INFERRED_FROM_PATTERN")
    if sample_size is None:
        return
    if not pc.is_number(sample_size) or pc.to_number(sample_size) <= 0:
        flags.append("SAMPLE_SIZE_REVIEW_REQUIRED")


def compute_summary_fields(record):
    """Skill section 47: net and app_app_dis, deterministic, never
    LLM-estimated. Blank (None) if either input is missing - never
    force a value."""
    positive = record.get("positive")
    negative = record.get("negative")
    if not pc.is_number(positive) or not pc.is_number(negative):
        return None, None
    positive = pc.to_number(positive)
    negative = pc.to_number(negative)
    net = positive - negative
    denom = positive + negative
    app_app_dis = (positive / denom * 100) if denom else None
    return net, app_app_dis


def check_fieldwork_date(record, flags):
    status = record.get("fieldwork_date_status")
    normalized = record.get("fieldwork_date_normalized")
    if status == "FIELDWORK_DATE_UNKNOWN" or (not normalized and not status):
        flags.append("FIELDWORK_DATE_UNKNOWN")
    elif status == "IMPUTED_MONTH_MIDPOINT":
        flags.append("FIELDWORK_DATE_IMPUTED")  # informational, not a hard review trigger


def check_wording(record, flags):
    status = record.get("question_wording_status")

    if status == INHERITED_WORDING_STATUS:
        # Skill section 48: the matcher may PROPOSE inheritance, but a
        # record is never treated as having known wording on that
        # assertion alone - re-derive eligibility from the local EAD
        # reference file, the same "never approved on an LLM assertion
        # alone" principle verify_source.py applies to provenance (Skill
        # section 33).
        result = verify_wording.verify(record)
        record["wording_inheritance_check"] = result
        if result["eligible"]:
            flags.append("WORDING_INHERITED_FROM_SERIES_REFERENCE")
            record["question_wording_source"] = "EAD_SERIES_REFERENCE"
            if not record.get("question_wording_english"):
                record["question_wording_english"] = result["canonical_wording"]
        else:
            flags.append("QUESTION_WORDING_UNKNOWN")
        return

    if status not in WORDING_STATUSES or status == "UNKNOWN_WORDING":
        flags.append("QUESTION_WORDING_UNKNOWN")


def check_series(record, flags):
    if record.get("series_match_status") == "SERIES_REVIEW_REQUIRED":
        flags.append("SERIES_REVIEW_REQUIRED")


EAD_WORDING_MATCH_STATUSES = {
    "SERIES_MATCH_EXACT", "SERIES_MATCH_NORMALIZED", "SERIES_MATCH_SUPPORTED",
    "SERIES_REVIEW_REQUIRED",
}


def check_ead_wording_match(record, flags):
    """Reads the matcher-computed comparison of the proposed question
    wording against the authoritative EAD Series/Question-Wording
    reference workbook (python/ead_series_lookup.py). This script never
    performs that lookup itself - the matcher already ran it and
    attached the result, the same pattern as
    sample_size_status: INFERRED_FROM_FIRM_PATTERN (section 45).

    SERIES_MATCH_EXACT / _NORMALIZED / _SUPPORTED are informational
    positive signals only - they never themselves cause APPROVED
    (confidence/agreement with a reference is not evidence, Skill
    section 33) and are preserved on the record as-is. Only
    SERIES_REVIEW_REQUIRED contributes the shared review flag, and only
    once - check_series may have already added it."""
    status = record.get("ead_wording_match_status")
    if status == "SERIES_REVIEW_REQUIRED" and "SERIES_REVIEW_REQUIRED" not in flags:
        flags.append("SERIES_REVIEW_REQUIRED")


def check_pollster(record, flags):
    """Pollster is important for identifying/matching Series (Skill
    sections 10-11, 23) but is not itself a substantive measure of
    executive support. Its absence must never REJECT an otherwise valid,
    sourced observation - it routes to REVIEW via SERIES_REVIEW_REQUIRED
    instead (config/schema_mapping.yaml: Pollster is optional_supporting,
    not core_required). Never fabricate a pollster to avoid this flag."""
    if not record.get("pollster") and "SERIES_REVIEW_REQUIRED" not in flags:
        flags.append("SERIES_REVIEW_REQUIRED")


def check_required_identity(record):
    """Country and Series identify the observation itself - without
    either there is nothing to validate, so both stay hard-required
    (REJECTED). Pollster is handled separately by check_pollster (REVIEW,
    not REJECTED). Negative, Neutral, and Sample_Size are optional
    throughout this module: nothing here ever requires them to be
    present (config/schema_mapping.yaml: optional_supporting_fields)."""
    missing = [f for f in ("country", "series") if not record.get(f)]
    return missing


def validate(record):
    record = dict(record)
    flags = []

    if record.get("not_found"):
        record["source_verified"] = False
        record["validation_status"] = "NOT_FOUND"
        record["validation_reason"] = "NOT_FOUND_ON_APPROVED_SOURCES"
        record["validation_flags"] = ["NOT_FOUND_ON_APPROVED_SOURCES"]
        return record

    source_result = verify_source.verify(record)
    record["source_verified"] = source_result["source_verified"]
    record["source_domain"] = source_result["source_domain"]

    if not source_result["source_verified"]:
        record["validation_status"] = "REJECTED"
        record["validation_reason"] = "{}: {}".format(
            source_result["status"], source_result["reason"])
        record["validation_flags"] = [source_result["status"]]
        return record

    missing = check_required_identity(record)
    if missing:
        record["validation_status"] = "REJECTED"
        record["validation_reason"] = "Missing required identification field(s): {}".format(missing)
        record["validation_flags"] = ["MISSING_REQUIRED_FIELDS"]
        return record

    arithmetic_status, arithmetic_reason = check_arithmetic(record, flags)
    record["arithmetic_status"] = arithmetic_status
    record["arithmetic_reason"] = arithmetic_reason

    record["net"], record["app_app_dis"] = compute_summary_fields(record)

    check_sample_size(record, flags)
    check_fieldwork_date(record, flags)
    check_wording(record, flags)
    check_series(record, flags)
    check_ead_wording_match(record, flags)
    check_pollster(record, flags)

    informational_flags = ("FIELDWORK_DATE_IMPUTED", "WORDING_INHERITED_FROM_SERIES_REFERENCE")
    hard_review_flags = [f for f in flags if f not in informational_flags]

    if hard_review_flags:
        record["validation_status"] = "REVIEW"
        record["validation_reason"] = "Flagged for human review: {}".format(hard_review_flags)
    else:
        record["validation_status"] = "APPROVED"
        record["validation_reason"] = "Source verified, required fields present, " \
            "arithmetic status={}.".format(arithmetic_status)

    record["validation_flags"] = flags
    return record


def validate_batch(records):
    """Validate multiple candidate records in one call, reusing validate()
    for every record so no validation rule is duplicated between the
    single-record and batch paths.

    One result dict per input record is returned, in input order, each
    carrying a `batch_index`. A record that is malformed (not a JSON
    object, or a parse-error placeholder from
    pollitik_common.parse_batch_input) or that raises while validating
    becomes its own REJECTED result instead of raising - it never causes
    other records in the batch to be skipped or lost.
    """
    results = []
    for idx, record in enumerate(records):
        if isinstance(record, dict) and "__parse_error__" in record:
            results.append({
                "batch_index": idx,
                "validation_status": "REJECTED",
                "validation_reason": "Could not parse input record: {}".format(
                    record["__parse_error__"]),
                "validation_flags": ["INVALID_INPUT_RECORD"],
                "source_verified": False,
                "raw_input": record.get("__raw_line__"),
            })
            continue

        if not isinstance(record, dict):
            results.append({
                "batch_index": idx,
                "validation_status": "REJECTED",
                "validation_reason": "Input record at batch index {} is not "
                    "a JSON object (got {}).".format(idx, type(record).__name__),
                "validation_flags": ["INVALID_INPUT_RECORD"],
                "source_verified": False,
                "raw_input": record,
            })
            continue

        try:
            result = validate(record)
        except Exception as exc:  # noqa: BLE001 - isolate one bad record, never abort the batch
            results.append({
                "batch_index": idx,
                "validation_status": "REJECTED",
                "validation_reason": "Unhandled error validating record at "
                    "batch index {}: {}".format(idx, exc),
                "validation_flags": ["VALIDATION_ERROR"],
                "source_verified": False,
                "raw_input": record,
            })
            continue

        result["batch_index"] = idx
        results.append(result)

    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--record",
        help="Path to a JSON candidate record file. Defaults to reading "
             "a single JSON object from stdin.",
    )
    parser.add_argument(
        "--records",
        help="Path to a JSON array or JSONL file of multiple candidate "
             "records. Batch mode: validates every record in one "
             "invocation via validate_batch() and prints a JSON array of "
             "results, one per input record, in the same order.",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Treat stdin as a batch (JSON array or JSONL) instead of a "
             "single JSON object. Ignored if --record or --records is given.",
    )
    parser.add_argument(
        "--log",
        action="store_true",
        help="Also append the validated record(s) to logs/validation/ as JSONL.",
    )
    args = parser.parse_args()

    if args.record:
        # Unchanged single-record path.
        with open(args.record, "r", encoding="utf-8") as f:
            record = json.load(f)

        result = validate(record)

        if args.log:
            log_path = pc.VALIDATION_LOG_DIR + "/validated_" + pc.utc_now_iso().replace(":", "") + ".jsonl"
            pc.append_jsonl(log_path, result)

        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0 if result["validation_status"] == "APPROVED" else 1)

    if args.records or args.batch:
        if args.records:
            with open(args.records, "r", encoding="utf-8") as f:
                text = f.read()
        else:
            text = sys.stdin.read()

        records = pc.parse_batch_input(text)
        results = validate_batch(records)

        if args.log:
            log_path = pc.VALIDATION_LOG_DIR + "/validated_" + pc.utc_now_iso().replace(":", "") + ".jsonl"
            for result in results:
                pc.append_jsonl(log_path, result)

        print(json.dumps(results, indent=2, ensure_ascii=False))
        sys.exit(0 if all(r.get("validation_status") == "APPROVED" for r in results) else 1)

    # Unchanged single-record path (stdin).
    record = json.load(sys.stdin)

    result = validate(record)

    if args.log:
        log_path = pc.VALIDATION_LOG_DIR + "/validated_" + pc.utc_now_iso().replace(":", "") + ".jsonl"
        pc.append_jsonl(log_path, result)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["validation_status"] == "APPROVED" else 1)


if __name__ == "__main__":
    main()
