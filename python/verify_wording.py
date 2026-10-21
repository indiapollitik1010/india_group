#!/usr/bin/env python3
"""Deterministic canonical-wording inheritance check (Skill section 48).

IMPORTANT: this script does not decide whether a candidate's series match
is confident, and it does not classify question types semantically - that
judgment stays with the matcher (Skill sections 10-11). This script only
answers one narrow, deterministic question: does the EAD
Series/Question-Wording reference workbook
(`docs/ead/reference/EAD Series and Question Wording.xlsx`, Skill section
54; pollitik_common.EAD_WORDING_REFERENCE_PATH) contain exactly one row
for this exact (Country, Series), with non-blank wording and question
type? A record can only be treated as eligible for
INHERITED_FROM_SERIES_REFERENCE once this script (or validate_record.py,
which calls it) says so - matching the same "never approved on an LLM
assertion alone" principle verify_source.py applies to source provenance
(Skill section 33).

Input (stdin or --record a JSON file): a JSON object with at least
`country` and `series`.

Output: a JSON object:

    {
      "eligible": true | false,
      "reason": "...",
      "row_count": 0 | 1 | N,
      "canonical_wording": "..." | null,
      "question_type": "..." | null
    }
"""

import argparse
import json
import os
import re
import sys

import pollitik_common as pc

_ROW_CACHE = {}


def _normalize_header(name):
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def _normalize_value(value):
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _load_rows(path):
    """Read the EAD reference workbook's first sheet into a list of dicts,
    keyed by normalized header name. Cached per path+mtime for the life of
    the process, since a single batch-validation run may check many
    records against the same, unchanging reference file."""
    if not os.path.exists(path):
        return None

    mtime = os.path.getmtime(path)
    cached = _ROW_CACHE.get(path)
    if cached and cached[0] == mtime:
        return cached[1]

    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    rows_iter = ws.iter_rows(values_only=True)
    header = next(rows_iter, None)
    if not header:
        _ROW_CACHE[path] = (mtime, [])
        return []

    header_map = {i: _normalize_header(h) for i, h in enumerate(header) if h}
    rows = []
    for raw_row in rows_iter:
        row = {}
        for i, norm_name in header_map.items():
            if i < len(raw_row):
                row[norm_name] = raw_row[i]
        if any(v not in (None, "") for v in row.values()):
            rows.append(row)

    _ROW_CACHE[path] = (mtime, rows)
    return rows


def verify(record, path=None):
    path = path or pc.EAD_WORDING_REFERENCE_PATH
    country = (record or {}).get("country")
    series = (record or {}).get("series")

    if not country or not series:
        return {
            "eligible": False,
            "reason": "Record is missing country and/or series; cannot "
                      "look up an EAD reference row.",
            "row_count": 0,
            "canonical_wording": None,
            "question_type": None,
        }

    rows = _load_rows(path)
    if rows is None:
        return {
            "eligible": False,
            "reason": "No EAD reference workbook found at {}.".format(path),
            "row_count": 0,
            "canonical_wording": None,
            "question_type": None,
        }

    norm_country = _normalize_value(country)
    norm_series = _normalize_value(series)
    matches = [
        r for r in rows
        if _normalize_value(r.get("country", "")) == norm_country
        and _normalize_value(r.get("series", "")) == norm_series
    ]

    if not matches:
        return {
            "eligible": False,
            "reason": "No EAD reference row for Country={!r} Series={!r}.".format(
                country, series),
            "row_count": 0,
            "canonical_wording": None,
            "question_type": None,
        }

    if len(matches) > 1:
        return {
            "eligible": False,
            "reason": "{} EAD reference rows exist for Country={!r} "
                      "Series={!r}; not a single unambiguous applicable "
                      "question.".format(len(matches), country, series),
            "row_count": len(matches),
            "canonical_wording": None,
            "question_type": None,
        }

    row = matches[0]
    wording = row.get("question_wording")
    question_type = row.get("question_type")

    if not wording or not str(wording).strip():
        return {
            "eligible": False,
            "reason": "The single EAD reference row for Country={!r} "
                      "Series={!r} has no Question Wording text.".format(
                          country, series),
            "row_count": 1,
            "canonical_wording": None,
            "question_type": str(question_type).strip() if question_type else None,
        }

    if not question_type or not str(question_type).strip():
        return {
            "eligible": False,
            "reason": "The single EAD reference row for Country={!r} "
                      "Series={!r} has no Question Type recorded.".format(
                          country, series),
            "row_count": 1,
            "canonical_wording": str(wording).strip(),
            "question_type": None,
        }

    return {
        "eligible": True,
        "reason": "Exactly one EAD reference row found for Country={!r} "
                  "Series={!r}.".format(country, series),
        "row_count": 1,
        "canonical_wording": str(wording).strip(),
        "question_type": str(question_type).strip(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--record",
        help="Path to a JSON file with at least country/series. Defaults "
             "to reading a single JSON object from stdin.",
    )
    parser.add_argument(
        "--path",
        default=None,
        help="Override the EAD reference workbook path (defaults to "
             "docs/ead/reference/EAD Series and Question Wording.xlsx).",
    )
    args = parser.parse_args()

    if args.record:
        with open(args.record, "r", encoding="utf-8") as f:
            record = json.load(f)
    else:
        record = json.load(sys.stdin)

    result = verify(record, path=args.path)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["eligible"] else 1)


if __name__ == "__main__":
    main()
