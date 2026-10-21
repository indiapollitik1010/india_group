# Australia data

This folder is organizational/student-facing only, with one deliberate
exception, tracked in git. Nothing else should be copied in here — this
README points at the real locations so a student doesn't go looking for
data in the wrong place.

## `australia_reference_snapshot.csv`

A small, tracked, read-only export of Australia's *existing* reference
observations from the master workbook's Master sheet — exactly these 8
columns: `Series, Date, Total Count, Positive, Neutral, Negative,
Source, Country`. 16 raw Series values, 1,836 records, 1968-08-15 to
2026-02-15. It exists so a fresh workspace (no production workbook, no
pre-built index) can still build a real local reference index and
perform duplicate/reference checks before researching. It is a
point-in-time snapshot, not a live view: it is regenerated (by the
project owner, from the master workbook, the same way it was first
created) only when Australia's approved reference data materially
changes — a student workspace never regenerates or edits it. It is
never treated as evidence for a *new* external observation, the same
rule that governs the index/workbook it's derived from (Skill section
13).

**This is not Assignment-1 output.** It answers "does this look like a
duplicate of something already known," never "what did the finalized
assignment find." `python/resolve_assignment_dataset.py` has no code
path that can return this file for a validated-data or REVIEW question.

## `australia_assignment1_approved.csv` / `australia_assignment1_review.csv`

**Do not exist yet.** No Assignment-1 research/staging run has happened
for Australia in this repository — this workspace currently prepares
the existing-data/reference layer only (the scope, the reference
profile, the country Skill, and the tracked snapshot above), per this
task's explicit instruction not to perform the missing polling research
itself. Once a real research run happens, these would be built by
`python/build_country_assignment_snapshot.py` from that run's real
local pipeline output — never hand-transcribed, never copied from the
Canada blueprint's results. Until then,
`python/resolve_assignment_dataset.py --country Australia --purpose
{approved,review}` correctly has nothing tracked to fall back to; a
validated-data or REVIEW question should be answered by saying so
plainly, not by fabricating a summary.

## Real data locations

- **Local reference index**: `data/reference_index.duckdb` — queried
  via `python/reference_lookup.py --country Australia`, never edited
  directly. Built automatically (by the assignment prompt) from
  `australia_reference_snapshot.csv` in a workspace that has no
  production workbook, or from the workbook itself
  (`python/build_reference_index.py`) in one that does. Either way,
  once built it does not need the workbook to be queried.
- **Production workbook**: `data/master/pollitik_master.xlsx` — the
  canonical source of already-approved-and-written Australia records.
  Read-only except via `python/apply_changes.py`. Not required for
  research or duplicate-checking in a student workspace.
- **EAD Series/Question Wording reference**:
  `data/master/EAD Series and Question Wording.xlsx` — the authority
  for Series description, Question Type, and Question Wording where
  populated (see the reference profile for what's populated for each
  Australia series). Read-only, never a source of new external
  evidence.
- **Staging file**: `data/staging/candidates.jsonl` — every Australia
  candidate that has gone through validation, every status
  (APPROVED/REVIEW/REJECTED/NOT_FOUND), full audit trail.
- **Source cache**: `data/cache/sources.jsonl` — already-verified
  retrievals, keyed by URL, so a source is never re-fetched needlessly.

Do not create an Australia-specific copy of `data/master/` or
`data/staging/` here. One production workbook, one staging file, shared
by the whole pipeline — see `docs/country_blueprint.md` for why that
stays shared rather than being forked per country. The reference
snapshot above is the one narrow, intentional exception to "don't copy
data into a country folder," scoped to exactly the columns needed for
duplicate checks.
