#!/usr/bin/env python3
"""The one and only approved production writer for the Pollitik master
workbook (Skill sections 30-35, 42).

This script is intentionally the single choke point for production
writes. .claude/hooks/pollitik_guard.py blocks every other route to the
production workbook (direct Write/Edit tool calls, ad-hoc Bash writes,
one-off pandas/openpyxl snippets) and only allows a Bash invocation that
mentions a script listed in its APPROVED_WRITER_SCRIPTS constant. Keep
that list and this file's actual behavior in sync - if you rename this
script, update the hook too.

Hard safety rules enforced here, not just documented:

  1. Refuses to run against a workbook path that does not already exist.
     It never fabricates a workbook or invents column names - Skill
     section 30 requires real workbook column names, not invented ones.
  2. Re-validates the target staged record with validate_record.validate()
     itself. It does not trust a stale "validation_status": "APPROVED"
     sitting in the staging file - re-derives it from the record's own
     data every time.
  3. Refuses to write anything but a freshly re-validated APPROVED record.
  4. Always makes a timestamped backup of the workbook before touching it,
     and aborts if the backup cannot be made.
  5. Only maps record fields onto columns that already exist in the
     workbook's header row (case/spacing-insensitive match, plus a small
     set of historical-name aliases declared in config/schema_mapping.yaml
     - e.g. a workbook column literally named "Total Count" is recognized
     as the same field as the record's sample_size, never as a separate
     column). It never creates new columns. Any record fields that do not
     match an existing column (directly or via alias) are reported, not
     silently written elsewhere - they remain fully preserved in the
     staging JSONL and validation logs regardless.
  6. Logs old/new state to logs/writes/ and re-opens the workbook after
     saving to verify the row is actually there before declaring success.
  7. Marks the staged record as applied (applied=true, applied_at=...) in
     the staging file so it is not re-applied by --apply-all-approved.
"""

import argparse
import collections
import datetime
import json
import os
import re
import shutil
import sys

import pollitik_common as pc
import validate_record

DEFAULT_WORKBOOK = os.path.join(pc.MASTER_DIR, "pollitik_master.xlsx")

# Explicit overrides for candidate-record fields whose name does not match
# the Master workbook's own column header after normalize_header() (e.g.
# the workbook's "Date" column vs. the record's "fieldwork_date_normalized"
# field). Only covers fields with a real, unambiguous column counterpart -
# PM name, pollster, and question wording have no Master column and are
# deliberately left unmapped (reported in unmapped_fields_not_written_to_excel)
# rather than invented. Values here must already be normalize_header() output.
FIELD_TO_COLUMN_ALIASES = {
    "fieldwork_date_normalized": "date",
    "sample_size": "total_count",
    "source_url": "source",
}

# Skill section 19: fieldwork_date_normalized is always staged as an
# m/d/yyyy or mm/dd/yyyy string. Every existing Master "Date" cell holds a
# native datetime value, not a string, so the column-mapped value must be
# converted to match before it is written.
FIELDWORK_DATE_INPUT_FORMAT = "%m/%d/%Y"


def normalize_fieldwork_date_for_excel(value):
    """Convert a staged fieldwork_date_normalized string to the native
    datetime.datetime type existing Master rows use for their Date cell.

    Never invents or corrects a date: anything that is not a non-empty
    string, or does not parse as m/d/yyyy or mm/dd/yyyy, is returned
    unchanged (including None) so it writes through exactly as staged
    rather than being coerced into a fabricated value."""
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return value
    try:
        return datetime.datetime.strptime(stripped, FIELDWORK_DATE_INPUT_FORMAT)
    except ValueError:
        return value


def find_duplicate_record_ids(staged):
    """Deterministic duplicate-detection over the staging file's current
    contents, never an LLM self-report. A duplicate record_id means the
    staging file is in an ambiguous state (e.g. an append happened where
    an update should have) - this script must refuse to guess which line
    is authoritative rather than silently pick the first/last/APPROVED
    one, since a wrong guess here writes straight to production."""
    counts = collections.Counter(
        r.get("record_id") for r in staged if r.get("record_id")
    )
    return {record_id for record_id, n in counts.items() if n > 1}


def normalize_header(name):
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def backup_workbook(workbook_path, archive_dir):
    os.makedirs(archive_dir, exist_ok=True)
    stamp = pc.utc_now_iso().replace(":", "").replace("-", "")
    base = os.path.splitext(os.path.basename(workbook_path))[0]
    backup_path = os.path.join(archive_dir, "{}_backup_{}.xlsx".format(base, stamp))
    shutil.copy2(workbook_path, backup_path)
    if not os.path.exists(backup_path):
        raise RuntimeError("Backup copy did not appear on disk; refusing to write.")
    return backup_path


def build_column_map(header_row):
    column_map = {}
    for idx, cell in enumerate(header_row):
        if cell is None:
            continue
        column_map[normalize_header(cell)] = idx
    return column_map


def resolve_column(field, column_map, field_aliases):
    """Find the workbook column index for a record field, trying the
    field's own normalized name first, then any historical/alternate
    names declared for it in config/schema_mapping.yaml (e.g.
    sample_size's alias "Total Count"), then any hardcoded
    FIELD_TO_COLUMN_ALIASES entry (fields whose real Master column name
    was confirmed by direct workbook inspection but is not yet declared
    in config/schema_mapping.yaml, e.g. fieldwork_date_normalized ->
    "Date"). Never creates a column - only widens which existing column
    name counts as a match. Returns None if no existing column matches
    any candidate name."""
    candidates = [normalize_header(field)]
    candidates.extend(normalize_header(alias) for alias in field_aliases.get(field, []))
    if field in FIELD_TO_COLUMN_ALIASES:
        candidates.append(FIELD_TO_COLUMN_ALIASES[field])
    for candidate in candidates:
        if candidate in column_map:
            return column_map[candidate]
    return None


def apply_one(record, workbook_path, sheet_name=None, dry_run=False,
              archive_dir=None, writes_log_path=None):
    """`archive_dir`/`writes_log_path` default to the real project's
    data/archive/ and logs/writes/writes.jsonl (pc.ARCHIVE_DIR /
    pc.WRITES_LOG_DIR) so normal production runs are unaffected. Callers
    that want backups/logs isolated from those real locations (e.g. tests
    pointed at a temporary/test workbook) must pass explicit overrides -
    this never infers isolation from the workbook path alone."""
    if archive_dir is None:
        archive_dir = pc.ARCHIVE_DIR
    if writes_log_path is None:
        writes_log_path = os.path.join(pc.WRITES_LOG_DIR, "writes.jsonl")

    if not os.path.exists(workbook_path):
        raise RuntimeError(
            "Workbook not found at {}. Add the real Pollitik master "
            "workbook there first; this script never creates a "
            "production workbook from scratch or invents its "
            "schema.".format(workbook_path)
        )

    revalidated = validate_record.validate(record)
    if revalidated["validation_status"] != "APPROVED":
        raise RuntimeError(
            "Refusing to write: record_id={} re-validated to status={} "
            "(reason: {}). Only a freshly re-validated APPROVED record "
            "may be written.".format(
                record.get("record_id"), revalidated["validation_status"],
                revalidated["validation_reason"],
            )
        )

    import openpyxl

    backup_path = None if dry_run else backup_workbook(workbook_path, archive_dir)

    wb = openpyxl.load_workbook(workbook_path)
    try:
        ws = wb[sheet_name] if sheet_name else wb[wb.sheetnames[0]]
        header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
        column_map = build_column_map(header_row)
        field_aliases = pc.load_schema_field_aliases()

        new_row_values = [None] * len(header_row)
        mapped_fields = {}
        unmapped_fields = {}
        for field, value in revalidated.items():
            col_idx = resolve_column(field, column_map, field_aliases)
            if col_idx is not None:
                cell_value = value
                if field == "fieldwork_date_normalized":
                    # Convert for the actual worksheet cell only - keep the
                    # reported mapped_fields value as the original staged
                    # string so it stays JSON-serializable for the
                    # console/writes-log result (which has no `default=str`
                    # fallback the way the final CLI print does).
                    cell_value = normalize_fieldwork_date_for_excel(value)
                new_row_values[col_idx] = cell_value
                mapped_fields[field] = value
            else:
                unmapped_fields[field] = value

        target_row_number = ws.max_row + 1

        if not dry_run:
            ws.append(new_row_values)
            wb.save(workbook_path)
    finally:
        wb.close()

    verified = False
    if not dry_run:
        verify_wb = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)
        try:
            verify_ws = verify_wb[sheet_name] if sheet_name else verify_wb[verify_wb.sheetnames[0]]
            written_row = None
            for i, row in enumerate(verify_ws.iter_rows(values_only=True), start=1):
                if i == target_row_number:
                    written_row = list(row)
                    break
            verified = written_row == new_row_values
        finally:
            verify_wb.close()

    result = {
        "record_id": record.get("record_id"),
        "workbook_path": workbook_path,
        "backup_path": backup_path,
        "row_number": None if dry_run else target_row_number,
        "mapped_fields": mapped_fields,
        "unmapped_fields_not_written_to_excel": unmapped_fields,
        "verified_after_save": verified,
        "dry_run": dry_run,
        "applied_at": pc.utc_now_iso(),
    }

    if not dry_run:
        pc.append_jsonl(writes_log_path, result)
        if not verified:
            raise RuntimeError(
                "Wrote row {} but post-save verification did not find "
                "matching content. Check {} and the backup at {}.".format(
                    target_row_number, workbook_path, backup_path
                )
            )

    return result


def mark_staged_record_applied(record_id, apply_result, staging_file):
    """Marks the record applied in `staging_file` - always the caller's
    --staging-file (or its default), never the hardcoded pc.STAGING_FILE
    directly. A test/alternate --staging-file must never cause a write to
    the real staging file."""
    if not os.path.exists(staging_file):
        return
    records = pc.read_jsonl(staging_file)
    changed = False
    for rec in records:
        if rec.get("record_id") == record_id:
            rec["applied"] = True
            rec["applied_at"] = apply_result["applied_at"]
            rec["applied_row_number"] = apply_result["row_number"]
            changed = True
    if changed:
        with open(staging_file, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-id", help="Stage record_id to apply.")
    parser.add_argument(
        "--apply-all-approved",
        action="store_true",
        help="Apply every staged record that re-validates to APPROVED "
             "and has not already been applied.",
    )
    parser.add_argument("--staging-file", default=pc.STAGING_FILE)
    parser.add_argument("--workbook", default=DEFAULT_WORKBOOK)
    parser.add_argument("--sheet", default=None)
    parser.add_argument(
        "--archive-dir",
        default=pc.ARCHIVE_DIR,
        help="Directory workbook backups are written to. Defaults to the "
             "real project's data/archive/. Only override this for "
             "isolated test/output runs - never inferred automatically "
             "from --workbook.",
    )
    parser.add_argument(
        "--writes-log",
        default=os.path.join(pc.WRITES_LOG_DIR, "writes.jsonl"),
        help="JSONL file write-log entries are appended to. Defaults to "
             "the real project's logs/writes/writes.jsonl. Only override "
             "this for isolated test/output runs - never inferred "
             "automatically from --workbook.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Re-validate and report what would be written, without "
             "touching the workbook or making a backup.",
    )
    args = parser.parse_args()

    if not args.record_id and not args.apply_all_approved:
        parser.error("Specify --record-id or --apply-all-approved.")

    staged = pc.read_jsonl(args.staging_file)
    duplicate_ids = find_duplicate_record_ids(staged)

    if args.record_id:
        if args.record_id in duplicate_ids:
            print(json.dumps({
                "error": "Refusing to write: record_id={} appears more than "
                         "once in {}. Staging state is ambiguous - resolve "
                         "the duplicate (see stage_changes.py --update) "
                         "before applying.".format(args.record_id, args.staging_file)
            }))
            sys.exit(1)
        targets = [r for r in staged if r.get("record_id") == args.record_id]
        if not targets:
            print(json.dumps({"error": "record_id not found in staging file: {}".format(args.record_id)}))
            sys.exit(1)
    else:
        if duplicate_ids:
            print(json.dumps({
                "error": "Refusing to write: staging file {} has duplicate "
                         "record_id(s): {}. Applying while any record_id is "
                         "ambiguous risks writing the same observation "
                         "twice, or writing the wrong version of it - "
                         "resolve the duplicate(s) (see stage_changes.py "
                         "--update) before running --apply-all-approved."
                         .format(args.staging_file, sorted(duplicate_ids))
            }))
            sys.exit(1)
        targets = [r for r in staged if not r.get("applied")]

    results = []
    had_error = False
    for record in targets:
        try:
            result = apply_one(
                record, args.workbook, args.sheet, dry_run=args.dry_run,
                archive_dir=args.archive_dir, writes_log_path=args.writes_log,
            )
            if not args.dry_run:
                mark_staged_record_applied(record.get("record_id"), result, args.staging_file)
            results.append(result)
        except Exception as exc:  # noqa: BLE001 - surface every failure to the caller
            had_error = True
            results.append({"record_id": record.get("record_id"), "error": str(exc)})

    print(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    sys.exit(1 if had_error else 0)


if __name__ == "__main__":
    main()
