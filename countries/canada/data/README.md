# Canada data

This folder is organizational/student-facing only, with three deliberate
exceptions, all tracked in git. Nothing else should be copied in here —
this README points at the real locations so a student doesn't go
looking for data in the wrong place.

## `canada_reference_snapshot.csv`

A small, tracked, read-only export of Canada's *existing* reference
observations from the master workbook's Master sheet — exactly these 8
columns: `Series, Date, Total Count, Positive, Neutral, Negative,
Source, Country`. It exists so a fresh workspace (no production
workbook, no pre-built index) can still build a real local reference
index and perform duplicate/reference checks before researching. It is
a point-in-time snapshot, not a live view: it is regenerated (by the
project owner, from the master workbook, the same way it was first
created) only when Canada's approved reference data materially changes
— a student workspace never regenerates or edits it. It is never
treated as evidence for a *new* external observation, the same rule
that governs the index/workbook it's derived from (Skill section 13).

**This is not Assignment-1 output.** It answers "does this look like a
duplicate of something already known," never "what did the finalized
assignment find." `python/resolve_assignment_dataset.py` has no code
path that can return this file for a validated-data or REVIEW question.

## `canada_assignment1_approved.csv`

A small, tracked, frozen copy of the finalized **29 APPROVED**
Assignment-1 records, in exactly the schema
`python/generate_visualization.py` already requires: `Date, Approval,
Prime Minister, Party, Series, Source, Status`. This is what lets a
fresh clone answer validated-data questions ("summarize the trend,"
"what was the highest/lowest rating") and generate a graph without a
research run happening first — the worked-example blueprint actually
works end to end in a brand-new workspace.

It was built with `python/build_country_assignment_snapshot.py` (a
maintainer/build-time tool, run once against this workspace's real
`data/processed/canada_pm_approval_main.csv`) — never hand-transcribed.
Re-run that script and re-commit the result only when Canada's finalized
Assignment-1 approved records materially change; a student workspace
never regenerates or edits it.

A fresher local result (`data/processed/canada_pm_approval_main.csv`,
if this workspace has actually done research this session) always takes
precedence over this frozen file — see
`python/resolve_assignment_dataset.py` and "Deterministic result
routing" in `countries/canada/AGENTS.md`. Never read this file directly
by path; always go through the resolver.

## `canada_assignment1_review.csv`

The finalized **10 REVIEW** records' counterpart, same columns as above
plus one: `Validation Reason` — each record's real, human-readable
validation issue (e.g. `"Flagged for human review: ['SAMPLE_SIZE_INFERRED_FROM_PATTERN']"`),
joined deterministically by `python/build_country_assignment_snapshot.py`
from the local audit-schema REVIEW file, never invented. `Status` is
always `REVIEW` on every row — this file is for explaining what's
unresolved, never for plotting or trend analysis, and
`python/generate_visualization.py` never reads it.

## Real data locations

- **Local reference index**: `data/reference_index.duckdb` — queried
  via `python/reference_lookup.py --country Canada`, never edited
  directly. Built automatically (by the assignment prompt) from
  `canada_reference_snapshot.csv` in a workspace that has no production
  workbook, or from the workbook itself
  (`python/build_reference_index.py`) in one that does. Either way,
  once built it does not need the workbook to be queried.
- **Production workbook**: `data/master/pollitik_master.xlsx` — the
  canonical source of already-approved-and-written Canada records.
  Read-only except via `python/apply_changes.py`. Not required for
  research or duplicate-checking in a student workspace.
- **Staging file**: `data/staging/candidates.jsonl` — every Canada
  candidate that has gone through validation, every status
  (APPROVED/REVIEW/REJECTED/NOT_FOUND), full audit trail. This is where
  new research results land before anything reaches the workbook.
- **Source cache**: `data/cache/sources.jsonl` — already-verified
  retrievals, keyed by URL, so a source is never re-fetched needlessly.

Do not create a Canada-specific copy of `data/master/` or
`data/staging/` here. One production workbook, one staging file, shared
by the whole pipeline — see `docs/country_blueprint.md` for why that
stays shared rather than being forked per country. The reference
snapshot above is the one narrow, intentional exception to "don't copy
data into a country folder," scoped to exactly the columns needed for
duplicate checks.
