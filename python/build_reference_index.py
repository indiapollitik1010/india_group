#!/usr/bin/env python3
"""Build (or rebuild) a read-only DuckDB reference index from either the
master Pollitik workbook OR a country reference-snapshot CSV, for
fast/low-token lookups (Skill section 13; token-efficiency requirement:
never load the full workbook into an LLM context).

Excel (or the tracked CSV snapshot) remains canonical. This index is a
derived, disposable artifact - delete data/reference_index.duckdb and
rerun this script at any time to rebuild it. Nothing ever writes back
from the index to its source, and the index is never treated as
evidence for a NEW external observation (Skill section 13/40) - it only
helps a subagent quickly find existing rows to compare against.

Column names are taken verbatim from whatever the source's header row
actually says - this script never invents or assumes Pollitik schema
column names (Skill section 30).

Two input shapes are supported, chosen by the `--workbook` path's
extension - nothing else about this script's behavior, output shape, or
the existing Excel path changes:

  - `.xlsx`/`.xlsm`/`.xls` (unchanged): every sheet (or just `--sheet`)
    is indexed into its own table, exactly as before.
  - `.csv` (new): a single small reference snapshot - e.g.
    `countries/canada/data/canada_reference_snapshot.csv` - is indexed
    into one table. This is what lets a fresh student workspace build a
    usable local index without ever needing the real master workbook.
    `--sheet` does not apply to a CSV input and is rejected with a clear
    message rather than silently ignored.

Usage:
    python3 python/build_reference_index.py [--workbook PATH] [--index PATH] [--sheet NAME]
    python3 python/build_reference_index.py --workbook countries/canada/data/canada_reference_snapshot.csv --index data/reference_index.duckdb
"""

import argparse
import os
import re
import sys

import pollitik_common as pc

# Tables owned by python/build_ead_reference_index.py, which shares this
# same DuckDB file (data/reference_index.duckdb) for the authoritative
# EAD Series/Question-Wording reference. A rebuild here must never wipe
# them, and build_ead_reference_index.py's own rebuild is likewise
# scoped to only its own tables - see that script.
PROTECTED_TABLES = {"ead_series_reference", "_ead_reference_metadata"}


def normalize_table_name(name):
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip()).strip("_")
    return cleaned.lower() or "sheet"


def is_csv_path(path):
    return os.path.splitext(path)[1].lower() == ".csv"


def build(workbook_path, index_path, sheet_name=None):
    if not os.path.exists(workbook_path):
        return {
            "built": False,
            "workbook_path": workbook_path,
            "message": "No workbook/snapshot at this path yet - nothing to "
                       "index. Add the real Pollitik master workbook under "
                       "data/master/, or point --workbook at a tracked "
                       "country reference-snapshot CSV, first; this script "
                       "never fabricates one or invents a schema.",
        }

    if sheet_name and is_csv_path(workbook_path):
        return {
            "built": False,
            "workbook_path": workbook_path,
            "message": "--sheet is not applicable to a CSV input (a "
                       "reference-snapshot CSV has no sheets) - omit it "
                       "when --workbook points at a .csv file.",
        }

    import duckdb
    import pandas as pd

    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    if os.path.exists(index_path):
        # Scoped rebuild, not a full file wipe: drop only the tables this
        # script owns (anything not in PROTECTED_TABLES), so the shared
        # index file can also hold the EAD reference table without this
        # rebuild wiping it.
        con = duckdb.connect(index_path)
        try:
            existing = [r[0] for r in con.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()]
            for t in existing:
                if t not in PROTECTED_TABLES:
                    con.execute(f'DROP TABLE IF EXISTS "{t}"')
        finally:
            con.close()

    con = duckdb.connect(index_path)
    tables = []
    try:
        if is_csv_path(workbook_path):
            df = pd.read_csv(workbook_path)
            for col in df.columns:
                if df[col].dtype == "object":
                    df[col] = df[col].astype("string")

            table = normalize_table_name(os.path.splitext(os.path.basename(workbook_path))[0])
            con.register("_df", df)
            con.execute(f'CREATE TABLE "{table}" AS SELECT * FROM _df')
            con.unregister("_df")
            tables.append({"sheet": None, "table": table, "rows": len(df), "columns": list(df.columns)})
            source_kind = "csv"
        else:
            xls = pd.ExcelFile(workbook_path)
            sheet_names = [sheet_name] if sheet_name else xls.sheet_names

            for name in sheet_names:
                df = xls.parse(name)

                for col in df.columns:
                    if df[col].dtype == "object":
                        df[col] = df[col].astype("string")

                table = normalize_table_name(name)
                con.register("_df", df)
                con.execute(f'CREATE TABLE "{table}" AS SELECT * FROM _df')
                con.unregister("_df")
                tables.append({"sheet": name, "table": table, "rows": len(df), "columns": list(df.columns)})
            source_kind = "workbook"

        # Same three columns as before (reference_lookup.py only ever
        # selects workbook_path/built_at) - a fourth, source_kind, is
        # additive and purely informational, so existing readers of this
        # table are unaffected. workbook_path/workbook_mtime here are
        # whatever the caller passed/the source file's own mtime, exactly
        # as before - no new machine-specific data (hostname, username,
        # etc.) is introduced for the CSV case.
        con.execute(
            "CREATE TABLE _index_metadata AS SELECT ? AS workbook_path, ? AS built_at, "
            "? AS workbook_mtime, ? AS source_kind",
            [workbook_path, pc.utc_now_iso(), os.path.getmtime(workbook_path), source_kind],
        )
    finally:
        con.close()

    return {
        "built": True,
        "workbook_path": workbook_path,
        "index_path": index_path,
        "built_at": pc.utc_now_iso(),
        "source_kind": source_kind,
        "tables": tables,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", default=pc.DEFAULT_MASTER_WORKBOOK,
                         help="Path to the master .xlsx, or to a tracked "
                              "country reference-snapshot .csv.")
    parser.add_argument("--index", default=pc.REFERENCE_INDEX_PATH)
    parser.add_argument("--sheet", default=None, help="Index only this sheet (Excel input only; default: all sheets)")
    args = parser.parse_args()

    import json

    result = build(args.workbook, args.index, args.sheet)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    sys.exit(0 if result["built"] else 1)


if __name__ == "__main__":
    main()
