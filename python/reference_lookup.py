#!/usr/bin/env python3
"""Low-token reference lookup against the DuckDB index built by
build_reference_index.py (Skill section 13, token-efficiency
requirement #2: deterministic queries instead of loading the whole
workbook into an LLM context).

Returns a SMALL number of relevant existing rows (default limit 10) for
comparison - never the whole table. Excel remains canonical; this reads
only the derived index, never the workbook itself, and is never treated
as evidence for a new external observation.

Column names are matched to whatever the indexed workbook actually
calls them (case/spacing-insensitive), never assumed - if a requested
filter has no matching column, it is reported as unmapped rather than
silently ignored or applied to the wrong column.

Usage:
    python3 python/reference_lookup.py \\
        [--index PATH] [--table NAME] \\
        [--country X] [--pollster X] [--executive-type X] [--series X] \\
        [--wording-contains X] [--date-from m/d/yyyy] [--date-to m/d/yyyy] \\
        [--limit 10]
"""

import argparse
import json
import os
import re
import sys

import pollitik_common as pc


def normalize_header(name):
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


FILTER_COLUMN_CANDIDATES = {
    "country": ["country", "country_base"],
    "pollster": ["pollster"],
    "executive_type": ["executive_type", "executivetype", "executive"],
    "series": ["series"],
}


def find_column(column_map, candidates):
    for candidate in candidates:
        if candidate in column_map:
            return column_map[candidate]
    return None


def find_wording_column(column_map):
    for norm, actual in column_map.items():
        if "wording" in norm or "question" in norm:
            return actual
    return None


def find_date_column(column_map):
    fieldwork_end = [actual for norm, actual in column_map.items() if "fieldwork" in norm and "end" in norm]
    if fieldwork_end:
        return fieldwork_end[0]
    any_date = [actual for norm, actual in column_map.items() if "date" in norm]
    return any_date[0] if any_date else None


def lookup(index_path, table_name, filters, limit):
    if not os.path.exists(index_path):
        return {
            "found_index": False,
            "message": "No reference index at {}. Run "
                       "python/build_reference_index.py first (it will "
                       "itself report cleanly if there is no workbook to "
                       "index yet).".format(index_path),
            "rows": [],
        }

    import duckdb

    con = duckdb.connect(index_path, read_only=True)
    try:
        tables = [r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name != '_index_metadata'"
        ).fetchall()]
        if not tables:
            return {"found_index": True, "message": "Index exists but has no tables.", "rows": []}

        # Deterministic default-table selection (never "pick tables[0]" -
        # that silently queried an unrelated sheet, e.g. 'arg2023', when a
        # full-master-workbook-built index has many tables). Table names
        # here are already canonically lowercased by
        # build_reference_index.py's normalize_table_name(), so a plain
        # 'master' in tables check is correct and sufficient - no need to
        # route this through pollitik_common.normalize_identifier(), which
        # exists for Country/Series VALUE matching, not table-name
        # comparison. Precedence:
        #   1. --table, if given, always wins (explicit override).
        #   2. a table literally named 'master' (the canonical Master
        #      sheet from a full-workbook-built index).
        #   3. if there is exactly one table, use it - this is what keeps
        #      a country-snapshot-built index (one table, e.g.
        #      'australia_reference_snapshot') working automatically.
        #   4. multiple tables and no 'master' - ambiguous; fail clearly
        #      with the available table list rather than arbitrarily
        #      choosing one.
        if table_name:
            table = table_name
            table_source = "explicit"
            if table not in tables:
                return {
                    "found_index": True,
                    "message": "Table '{}' not found. Available tables: {}".format(table, tables),
                    "available_tables": tables,
                    "rows": [],
                }
        elif "master" in tables:
            table = "master"
            table_source = "master_default"
        elif len(tables) == 1:
            table = tables[0]
            table_source = "single_table_default"
        else:
            return {
                "found_index": True,
                "ambiguous_tables": True,
                "message": (
                    "Multiple tables exist in this index and none is named "
                    "'master' - refusing to arbitrarily pick one (e.g. an "
                    "unrelated sheet like 'arg2023'). Pass --table "
                    "explicitly. Available tables: {}".format(tables)
                ),
                "available_tables": tables,
                "rows": [],
            }

        metadata = con.execute("SELECT workbook_path, built_at FROM _index_metadata").fetchone()

        columns = [r[0] for r in con.execute(f'DESCRIBE "{table}"').fetchall()]
        column_map = {normalize_header(c): c for c in columns}

        where_clauses = []
        params = []
        unmapped_filters = []

        for key in ("country", "pollster", "executive_type", "series"):
            value = filters.get(key)
            if not value:
                continue
            col = find_column(column_map, FILTER_COLUMN_CANDIDATES[key])
            if not col:
                unmapped_filters.append(key)
                continue
            where_clauses.append(f'"{col}" ILIKE ?')
            params.append(f"%{value}%")

        if filters.get("wording_contains"):
            col = find_wording_column(column_map)
            if not col:
                unmapped_filters.append("wording_contains")
            else:
                where_clauses.append(f'"{col}" ILIKE ?')
                params.append(f"%{filters['wording_contains']}%")

        if filters.get("date_from") or filters.get("date_to"):
            col = find_date_column(column_map)
            if not col:
                unmapped_filters.append("date_from/date_to")
            else:
                # Handles both a native DATE/TIMESTAMP column (pandas/
                # openpyxl often produce one) and the project's own
                # m/d/yyyy string convention (Skill section 19) - whichever
                # TRY_CAST/TRY_STRPTIME actually parses wins, the other
                # side just yields NULL and is ignored by COALESCE.
                col_expr = (
                    f'COALESCE(TRY_CAST("{col}" AS DATE), '
                    f'TRY_STRPTIME(CAST("{col}" AS VARCHAR), \'%m/%d/%Y\')::DATE)'
                )
                param_expr = "COALESCE(TRY_CAST(? AS DATE), TRY_STRPTIME(?, '%m/%d/%Y')::DATE)"
                if filters.get("date_from"):
                    where_clauses.append(f"{col_expr} >= {param_expr}")
                    params.extend([filters["date_from"], filters["date_from"]])
                if filters.get("date_to"):
                    where_clauses.append(f"{col_expr} <= {param_expr}")
                    params.extend([filters["date_to"], filters["date_to"]])

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        query = f'SELECT * FROM "{table}"{where_sql} LIMIT ?'
        params.append(limit)

        rows = con.execute(query, params).fetchdf().to_dict(orient="records")

        return {
            "found_index": True,
            "workbook_path": metadata[0] if metadata else None,
            "index_built_at": metadata[1] if metadata else None,
            "table": table,
            "table_source": table_source,
            "available_tables": tables,
            "columns": columns,
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
    parser.add_argument("--table", default=None)
    parser.add_argument("--country", default=None)
    parser.add_argument("--pollster", default=None)
    parser.add_argument("--executive-type", dest="executive_type", default=None)
    parser.add_argument("--series", default=None)
    parser.add_argument("--wording-contains", dest="wording_contains", default=None)
    parser.add_argument("--date-from", dest="date_from", default=None)
    parser.add_argument("--date-to", dest="date_to", default=None)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    filters = {
        "country": args.country,
        "pollster": args.pollster,
        "executive_type": args.executive_type,
        "series": args.series,
        "wording_contains": args.wording_contains,
        "date_from": args.date_from,
        "date_to": args.date_to,
    }

    result = lookup(args.index, args.table, filters, args.limit)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    # Ambiguous table selection is a clear failure (student must pass
    # --table explicitly), even though the index itself genuinely exists
    # (found_index stays True - that fact isn't in question here).
    ok = result["found_index"] and not result.get("ambiguous_tables")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
