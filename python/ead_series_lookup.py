#!/usr/bin/env python3
"""Low-token lookup against the `ead_series_reference` table (built by
python/build_ead_reference_index.py) - the authoritative EAD Series/
Question-Wording reference (docs/ead/reference/EAD Series and Question
Wording.xlsx), NOT the production master workbook.

This is reference material for determining which EXISTING Series a
candidate observation might continue - it is NEVER evidence that a new
external polling observation occurred. External observations still
require verified original source evidence (WebFetch/approved retrieval),
exactly as this project already requires for the production workbook
(Skill section 13/40 principle, extended to this second reference
source).

Schema note (from direct inspection - never assumed): this reference
workbook has no dedicated Pollster or Executive_Type column. Pollster/
survey-program identity is embedded in free-text `Description`;
Executive_Type is only implicit via Country/Series suffix conventions
(Skill section 12) already established by the actual production
workbook. `--description-contains` is the practical way to search by
pollster/program here; there is no `--executive-type` filter, so a
caller asking for one gets it reported back as unmapped rather than
silently ignored or guessed at.

`--pollster` and `--executive-type` are accepted (the task's requested
lookup dimensions) but never map to a real column in this workbook -
they are reported in `unmapped_filters` rather than silently ignored or
misapplied, same convention as python/reference_lookup.py. Use
`--description-contains` as the practical pollster/program search
instead.

Usage:
    python3 python/ead_series_lookup.py \\
        [--index PATH] \\
        [--country X] [--series X] [--question-type X] \\
        [--description-contains X] \\
        [--wording-exact X] [--wording-contains X] \\
        [--limit 10]

--wording-exact / --wording-contains match against the NORMALIZED
wording (case/whitespace/quote-insensitive -
pollitik_common.normalize_question_wording), not literal byte-for-byte
text, so routine formatting differences still hit. The reference
workbook preserves original-language wording per country (verified by
inspection - e.g. Mexico rows are in Spanish, not translated) - match
question_wording_original against this reference first; only fall back
to an English-mediated comparison when the reference entry's own
language differs from the candidate's original-language wording, and
never fabricate a translation just to force a match.
"""

import argparse
import json
import os
import sys

import pollitik_common as pc

TABLE_NAME = "ead_series_reference"
METADATA_TABLE_NAME = "_ead_reference_metadata"

MAPPED_FILTERS = {
    "country", "series", "question_type", "description_contains",
    "wording_exact", "wording_contains",
}
# Requested-but-not-a-real-column filters (no dedicated Pollster or
# Executive_Type column exists in this reference workbook - see the
# module docstring). Accepted so a caller's request is never silently
# dropped, always surfaced via unmapped_filters instead.
UNMAPPABLE_FILTERS = {"pollster", "executive_type"}


def lookup(index_path, filters, limit):
    if not os.path.exists(index_path):
        return {
            "found_index": False,
            "message": "No reference index at {}. Run "
                       "python/build_ead_reference_index.py first (it "
                       "will itself report cleanly if the source "
                       "workbook is missing).".format(index_path),
            "rows": [],
        }

    import duckdb

    con = duckdb.connect(index_path, read_only=True)
    try:
        tables = [r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()]
        if TABLE_NAME not in tables:
            return {
                "found_index": True,
                "message": "'{}' table not found in the index yet. Run "
                           "python/build_ead_reference_index.py first.".format(TABLE_NAME),
                "rows": [],
            }

        metadata = None
        if METADATA_TABLE_NAME in tables:
            metadata = con.execute(
                f'SELECT workbook_path, built_at FROM "{METADATA_TABLE_NAME}"'
            ).fetchone()

        where_clauses = []
        params = []
        unmapped_filters = [k for k in filters if filters.get(k) and k in UNMAPPABLE_FILTERS]

        if filters.get("country"):
            where_clauses.append('"Country" ILIKE ?')
            params.append(f"%{filters['country']}%")
        if filters.get("series"):
            where_clauses.append('"Series" ILIKE ?')
            params.append(f"%{filters['series']}%")
        if filters.get("question_type"):
            where_clauses.append('"Question Type" ILIKE ?')
            params.append(f"%{filters['question_type']}%")
        if filters.get("description_contains"):
            where_clauses.append('"Description" ILIKE ?')
            params.append(f"%{filters['description_contains']}%")
        if filters.get("wording_exact"):
            where_clauses.append("question_wording_normalized = ?")
            params.append(pc.normalize_question_wording(filters["wording_exact"]))
        if filters.get("wording_contains"):
            where_clauses.append("question_wording_normalized ILIKE ?")
            params.append(f"%{pc.normalize_question_wording(filters['wording_contains'])}%")

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        query = f'SELECT * FROM "{TABLE_NAME}"{where_sql} LIMIT ?'
        params.append(limit)

        rows = con.execute(query, params).fetchdf().to_dict(orient="records")

        return {
            "found_index": True,
            "workbook_path": metadata[0] if metadata else None,
            "index_built_at": metadata[1] if metadata else None,
            "table": TABLE_NAME,
            "unmapped_filters": unmapped_filters,
            "row_count_returned": len(rows),
            "limit": limit,
            "rows": rows,
        }
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", default=pc.REFERENCE_INDEX_PATH)
    parser.add_argument("--country", default=None)
    parser.add_argument("--series", default=None)
    parser.add_argument("--question-type", dest="question_type", default=None)
    parser.add_argument("--description-contains", dest="description_contains", default=None)
    parser.add_argument("--wording-exact", dest="wording_exact", default=None)
    parser.add_argument("--wording-contains", dest="wording_contains", default=None)
    parser.add_argument("--pollster", default=None, help="Not a real column here - reported in unmapped_filters. Use --description-contains instead.")
    parser.add_argument("--executive-type", dest="executive_type", default=None, help="Not a real column here - reported in unmapped_filters.")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    filters = {
        "country": args.country,
        "series": args.series,
        "question_type": args.question_type,
        "description_contains": args.description_contains,
        "wording_exact": args.wording_exact,
        "wording_contains": args.wording_contains,
        "pollster": args.pollster,
        "executive_type": args.executive_type,
    }

    result = lookup(args.index, filters, args.limit)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    sys.exit(0 if result["found_index"] else 1)


if __name__ == "__main__":
    main()
