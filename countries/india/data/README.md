# India data

This folder is organizational/student-facing only, the same as every
other country's `data/README.md` in the Canada blueprint structure.
Nothing should be copied in here except the same two kinds of tracked
exceptions every country has, and only once they are genuinely built
for India:

- `india_reference_snapshot.csv` - **SETUP REQUIRED, does not exist
  yet.** Must be a real, tracked, read-only export of India's
  existing reference observations from the master workbook (see
  `docs/country_blueprint.md`) - never fabricated, never copied from
  the Canada blueprint's snapshot.
- `india_assignment1_approved.csv` / `india_assignment1_review.csv`
  - **SETUP REQUIRED, do not exist yet.** Only ever built by
  `python/build_country_assignment_snapshot.py` from a real, completed
  local research/staging run for India.

## Real data locations

Same shared, country-agnostic locations every country uses:

- `data/reference_index.duckdb` - local reference index, queried via
  `python/reference_lookup.py --country India`.
- `data/master/pollitik_master.xlsx` - the production workbook.
  Read-only except via `python/apply_changes.py`.
- `data/staging/candidates.jsonl` - every India candidate that
  has gone through validation.
- `data/cache/sources.jsonl` - already-verified retrievals.

Do not create a India-specific copy of `data/master/` or
`data/staging/` here - see `docs/country_blueprint.md` for why those
stay shared.
