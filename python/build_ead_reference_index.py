#!/usr/bin/env python3
"""Build (or refresh) the `ead_series_reference` table inside the shared
derived DuckDB index (data/reference_index.duckdb), from the read-only
authoritative EAD Series/Question-Wording reference workbook:

    docs/ead/reference/EAD Series and Question Wording.xlsx

This is NOT the production master workbook (see python/build_reference_index.py
for that). The two scripts share the same index file - each only ever
drops/rebuilds the table(s) it owns (this script: `ead_series_reference` /
`_ead_reference_metadata`; the other: everything else, see its
PROTECTED_TABLES) - so rebuilding one never wipes the other's table.

The reference workbook itself is NEVER opened for writing and this
script performs no write of any kind against it. It is reference
material for determining which EXISTING Series a candidate observation
might continue - never itself evidence that a new external polling
observation occurred (same principle as Skill section 13/40, extended
to this second reference source).

Adds two deterministic, match-only derived columns not present in the
source file - `series_normalized` and `question_wording_normalized`
(python/pollitik_common.normalize_question_wording) - purely for
comparison. The original `Series`/`Question Wording` text is preserved
unchanged in their own columns alongside them; nothing here overwrites
or discards the original wording.

Usage:
    python3 python/build_ead_reference_index.py [--workbook PATH] [--index PATH]
"""

import argparse
import os
import sys

import pollitik_common as pc

TABLE_NAME = "ead_series_reference"
METADATA_TABLE_NAME = "_ead_reference_metadata"

# The source workbook carries several trailing columns with no header
# (verified by direct inspection - Skill: never invent/assume schema).
# pandas names these "Unnamed: N"; they carry no data and are dropped
# here, not from the source file.
_UNNAMED_PREFIX = "Unnamed:"


def build(workbook_path, index_path):
    if not os.path.exists(workbook_path):
        return {
            "built": False,
            "workbook_path": workbook_path,
            "message": "No EAD reference workbook at this path yet - "
                       "nothing to index. This script never fabricates "
                       "one or invents a schema.",
        }

    import duckdb
    import pandas as pd

    df = pd.read_excel(workbook_path, sheet_name="Sheet1")
    df = df.loc[:, [c for c in df.columns if not str(c).startswith(_UNNAMED_PREFIX)]]
    df = df.dropna(how="all")  # drop fully-blank rows (found during inspection)

    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].astype("string")

    df["series_normalized"] = df.get("Series", pd.Series(dtype="string")).map(
        pc.normalize_question_wording
    )
    df["question_wording_normalized"] = df.get(
        "Question Wording", pd.Series(dtype="string")
    ).map(pc.normalize_question_wording)

    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    con = duckdb.connect(index_path)
    try:
        con.execute(f'DROP TABLE IF EXISTS "{TABLE_NAME}"')
        con.execute(f'DROP TABLE IF EXISTS "{METADATA_TABLE_NAME}"')
        con.register("_df", df)
        con.execute(f'CREATE TABLE "{TABLE_NAME}" AS SELECT * FROM _df')
        con.unregister("_df")
        con.execute(
            f'CREATE TABLE "{METADATA_TABLE_NAME}" AS SELECT ? AS workbook_path, '
            "? AS built_at, ? AS workbook_mtime",
            [workbook_path, pc.utc_now_iso(), os.path.getmtime(workbook_path)],
        )
    finally:
        con.close()

    return {
        "built": True,
        "workbook_path": workbook_path,
        "index_path": index_path,
        "table": TABLE_NAME,
        "rows": len(df),
        "columns": list(df.columns),
        "built_at": pc.utc_now_iso(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", default=pc.EAD_REFERENCE_WORKBOOK)
    parser.add_argument("--index", default=pc.REFERENCE_INDEX_PATH)
    args = parser.parse_args()

    import json

    result = build(args.workbook, args.index)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    sys.exit(0 if result["built"] else 1)


if __name__ == "__main__":
    main()
