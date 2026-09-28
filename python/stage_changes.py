#!/usr/bin/env python3
"""Stage a candidate Pollitik observation (Skill sections 29-30, 35).

Always re-runs deterministic validation before staging (a record cannot
be staged without going through validate_record.validate() first, even
if the caller already ran it) and appends the result as one JSON line to
data/staging/candidates.jsonl.

This script never touches the production workbook - it only ever writes
under data/staging/, which .claude/hooks/pollitik_guard.py always
permits. Records of every validation_status (APPROVED, REVIEW, REJECTED,
NOT_FOUND) are staged; only apply_changes.py filters for APPROVED before
touching production, so REVIEW/REJECTED/NOT_FOUND candidates remain
available for human review and for the final audit report (Skill
section 41).
"""

import argparse
import json
import os
import sys
import uuid

import pollitik_common as pc
import validate_record


def _finalize_and_persist(validated):
    """Shared tail end of staging: assign record_id/staged_at/job_id and
    append to the staging file. Used by both stage() and stage_batch() so
    the persistence semantics are identical either way."""
    validated["record_id"] = validated.get("record_id") or str(uuid.uuid4())
    validated["staged_at"] = pc.utc_now_iso()
    job_id = os.environ.get("POLLITIK_JOB_ID")
    if job_id and not validated.get("job_id"):
        validated["job_id"] = job_id
    pc.append_jsonl(pc.STAGING_FILE, validated)
    return validated


def stage(record):
    validated = validate_record.validate(record)
    return _finalize_and_persist(validated)


class StagingUpdateError(Exception):
    """Raised when an update-by-record_id request cannot be safely
    applied. Update mode must never silently append a duplicate line and
    must never silently pick a winner among ambiguous existing state -
    both of those failure modes are exactly what this class exists to
    turn into a hard, reported error instead."""


def _require_record_id(record):
    record_id = record.get("record_id") if isinstance(record, dict) else None
    if not record_id:
        raise StagingUpdateError(
            "Update mode requires an existing 'record_id' on every input "
            "record (revalidating an already-staged candidate must "
            "reference which staged line it replaces); none was provided "
            "on record: {}".format(record)
        )
    return record_id


def update(record):
    """Safely replace exactly one existing staged record, identified by
    record_id, with a freshly re-validated version - in place, with no
    duplicate line ever appended.

    Fails safely (raises StagingUpdateError, writes nothing) unless the
    record_id resolves to exactly one existing line in the staging file.
    """
    return update_batch([record])[0]


def update_batch(records):
    """Atomically replace multiple existing staged records by record_id
    in one pass over data/staging/candidates.jsonl.

    All-or-nothing across the whole batch: every requested record_id
    must resolve to exactly one existing staged line, or nothing is
    written at all. A partial update (some replaced, some not) would
    leave the staging file in exactly the ambiguous state this feature
    is meant to prevent, so validation of every target happens before
    any write. This intentionally differs from stage_batch(), whose
    per-record isolation is safe only because appending a new fact can
    never corrupt an existing one - replacing existing state is not the
    same kind of operation.
    """
    if not records:
        return []

    requested_ids = [_require_record_id(record) for record in records]

    dupe_requests = sorted({rid for rid in requested_ids if requested_ids.count(rid) > 1})
    if dupe_requests:
        raise StagingUpdateError(
            "Refusing update: the same record_id was targeted more than "
            "once in a single batch request: {}.".format(dupe_requests)
        )

    existing = pc.read_jsonl(pc.STAGING_FILE)

    positions = {}
    counts = {}
    for idx, existing_record in enumerate(existing):
        rid = existing_record.get("record_id")
        if rid in requested_ids:
            counts[rid] = counts.get(rid, 0) + 1
            positions[rid] = idx

    problems = []
    for rid in requested_ids:
        n = counts.get(rid, 0)
        if n == 0:
            problems.append(
                "record_id {!r} has no existing staged record to update".format(rid))
        elif n > 1:
            problems.append(
                "record_id {!r} is duplicated {} times in {}; staging state "
                "is ambiguous/corrupt and will not be guessed at - resolve "
                "manually before updating".format(rid, n, pc.STAGING_FILE))
    if problems:
        raise StagingUpdateError(
            "Refusing to update staged record(s): {}".format("; ".join(problems))
        )

    job_id = os.environ.get("POLLITIK_JOB_ID")
    updated_at = pc.utc_now_iso()

    results_by_id = {}
    for record, rid in zip(records, requested_ids):
        validated = validate_record.validate(record)
        original = existing[positions[rid]]
        validated["record_id"] = rid
        # Preserve the original first-staged timestamp (audit trail of
        # when the candidate was first staged) and record this
        # revalidation separately, rather than overwriting history.
        validated["staged_at"] = original.get("staged_at") or validated.get("staged_at") or updated_at
        validated["updated_at"] = updated_at
        if job_id and not validated.get("job_id"):
            validated["job_id"] = job_id
        results_by_id[rid] = validated

    new_lines = list(existing)
    for rid, idx in positions.items():
        new_lines[idx] = results_by_id[rid]

    pc.write_jsonl_atomic(pc.STAGING_FILE, new_lines)

    return [results_by_id[rid] for rid in requested_ids]


def stage_batch(records):
    """Validate and stage multiple candidate records in one call, reusing
    validate_record.validate_batch() (which itself reuses validate()) so
    no validation or staging rule is duplicated for the batch path.

    Every input record gets its own staged result, in order, using the
    exact same staging semantics as stage() (same record_id/staged_at/
    job_id assignment, same append-every-status-to-candidates.jsonl
    behavior). A failure persisting one record (e.g. a disk error) is
    captured on that record's result rather than raised, so it cannot
    lose or corrupt the rest of the batch.
    """
    results = []
    for validated in validate_record.validate_batch(records):
        try:
            results.append(_finalize_and_persist(validated))
        except Exception as exc:  # noqa: BLE001 - isolate one bad record, never abort the batch
            validated = dict(validated)
            validated["staging_error"] = str(exc)
            results.append(validated)
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
             "records. Batch mode: validates and stages every record in "
             "one invocation via stage_batch() and prints a JSON array of "
             "staged results, one per input record, in the same order.",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Treat stdin as a batch (JSON array or JSONL) instead of a "
             "single JSON object. Ignored if --record or --records is given.",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update-in-place mode instead of append: every input record "
             "must carry an existing 'record_id'. Atomically replaces that "
             "staged line with a freshly re-validated version - no "
             "duplicate line is ever appended. Fails safely (writes "
             "nothing, exits 1, prints {\"error\": ...}) unless every "
             "record_id resolves to exactly one existing staged line. "
             "Combine with --record/--records/--batch/stdin exactly like "
             "the append path; --records/--batch update multiple existing "
             "records atomically in one invocation.",
    )
    args = parser.parse_args()

    if args.update:
        try:
            if args.record:
                with open(args.record, "r", encoding="utf-8") as f:
                    record = json.load(f)
                updated = update(record)
                print(json.dumps(updated, indent=2, ensure_ascii=False))
                print(
                    "Updated record_id={} status={} -> {}".format(
                        updated["record_id"], updated["validation_status"], pc.STAGING_FILE
                    ),
                    file=sys.stderr,
                )
                return

            if args.records or args.batch:
                if args.records:
                    with open(args.records, "r", encoding="utf-8") as f:
                        text = f.read()
                else:
                    text = sys.stdin.read()
                records = pc.parse_batch_input(text)
                updated_list = update_batch(records)
                print(json.dumps(updated_list, indent=2, ensure_ascii=False))
                for updated in updated_list:
                    print(
                        "Updated record_id={} status={} -> {}".format(
                            updated.get("record_id"), updated.get("validation_status"), pc.STAGING_FILE
                        ),
                        file=sys.stderr,
                    )
                return

            record = json.load(sys.stdin)
            updated = update(record)
            print(json.dumps(updated, indent=2, ensure_ascii=False))
            print(
                "Updated record_id={} status={} -> {}".format(
                    updated["record_id"], updated["validation_status"], pc.STAGING_FILE
                ),
                file=sys.stderr,
            )
            return
        except StagingUpdateError as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
            sys.exit(1)

    if args.record:
        # Unchanged single-record path.
        with open(args.record, "r", encoding="utf-8") as f:
            record = json.load(f)

        staged = stage(record)
        print(json.dumps(staged, indent=2, ensure_ascii=False))
        print(
            "Staged record_id={} status={} -> {}".format(
                staged["record_id"], staged["validation_status"], pc.STAGING_FILE
            ),
            file=sys.stderr,
        )
        return

    if args.records or args.batch:
        if args.records:
            with open(args.records, "r", encoding="utf-8") as f:
                text = f.read()
        else:
            text = sys.stdin.read()

        records = pc.parse_batch_input(text)
        staged_list = stage_batch(records)

        print(json.dumps(staged_list, indent=2, ensure_ascii=False))
        for staged in staged_list:
            print(
                "Staged record_id={} status={} -> {}".format(
                    staged.get("record_id"), staged.get("validation_status"), pc.STAGING_FILE
                ),
                file=sys.stderr,
            )
        return

    # Unchanged single-record path (stdin).
    record = json.load(sys.stdin)

    staged = stage(record)
    print(json.dumps(staged, indent=2, ensure_ascii=False))
    print(
        "Staged record_id={} status={} -> {}".format(
            staged["record_id"], staged["validation_status"], pc.STAGING_FILE
        ),
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
