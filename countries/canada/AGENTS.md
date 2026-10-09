# AGENTS.md — Canada PM approval assignment

Narrows the root `AGENTS.md` and `CLAUDE.md` to this one assignment. It
adds nothing that contradicts them and duplicates none of their rules —
if something isn't covered here, the repo-wide rules apply unmodified.

## Scope

Canadian **Prime Minister** individual approval/support only — job
approval, job satisfaction, overall performance, favorable/unfavorable
opinion, positive/negative image, general approval/sympathy, as the
office-holder personally. Not the Government as a whole.

**Excluded** (route anything that looks like these to REVIEW or skip it,
never coerce it into a PM series):
- Government approval (`*GOV`-suffixed series, e.g. `DecimaGOV`,
  `EnvironicsGOV`, `ANGUSREIDGOV`)
- Issue-specific approval (economy, immigration, healthcare, etc.)
- Vote-intention / preferred-PM / head-to-head leader-preference
  questions
- Continuous 1-10 / 1-100 grading scales
- Trust/confidence in the PM (no Canada exception currently exists in
  `config/country_rules.yaml`)

## Which Skills govern this work

1. `.claude/skills/pollitik-executive-support/SKILL.md` — canonical,
   applies in full.
2. `.claude/skills/canada-pm-approval/SKILL.md` — Canada-specific
   narrowing of the canonical Skill. Read this before any Canada task.

Do not create a Canada-specific copy of any subagent — Canada context
comes from these two Skills plus the reference profile below, not from a
specialized agent.

## Preflight — run before any research

Before starting or resuming this assignment, run:

```
python python/check_assignment_preflight.py --country Canada
```

If it reports `reference_data_status=COUNTRY_SNAPSHOT_BUILDABLE`, build
the local index automatically from the tracked snapshot — never ask the
student to run this by hand:

```
python python/build_reference_index.py --workbook countries/canada/data/canada_reference_snapshot.csv --index data/reference_index.duckdb
```

then re-run preflight and continue only once it reports
`SAFE_TO_RESEARCH=true`. This never requires the real master workbook.
`countries/canada/prompts/run_assignment.txt` already encodes this loop
for the short prompt.

If it reports `SAFE_TO_RESEARCH=false` for any other reason, **STOP** —
do not fetch the web or stage anything. Explain the reported `reason`
and wait for it to be resolved. This check (and the index build above)
are both read-only/local-only: neither touches the master workbook or
fetches anything from the web. See the root `AGENTS.md` and
`docs/student_workflow.md` for the full required order (preflight ->
build index from snapshot if needed -> preflight again -> inspect
existing state -> research). An empty or missing
`data/staging/candidates.jsonl` does not make a workspace safe on its
own — the workflow needs an actually-built reference index, not
staging-file presence, to check for duplicates.

## Reference data — reuse, don't rebuild

- `countries/canada/data/canada_reference_snapshot.csv` — a small,
  tracked, Canada-only export of the master's existing reference
  observations (Series/Date/Total Count/Positive/Neutral/Negative/
  Source/Country). This is what a fresh student workspace builds its
  local index from — see `countries/canada/data/README.md`. It is a
  point-in-time export, not live-synced; it does not need or use the
  production master workbook to be queried once built.
- `.claude/skills/pollitik-executive-support/references/canada.md` — the
  30 known Canada series, their inferred PM-vs-GOV target, and explicit
  confidence cautions. Read before matching any new candidate.
- `python/reference_lookup.py --country Canada [--series ... --pollster ... --date-from ... --date-to ...]`
  — low-token DuckDB index query against the local reference index
  (built from either the snapshot or the master workbook). Use this,
  not the raw workbook, for "does this series/date already exist"
  checks.
- **Do not rerun the reference-analyst agent or rebuild the index
  (`python/build_reference_index.py`) unless the master workbook (or,
  in a student workspace, the tracked snapshot) has actually changed.**
  A fresh lookup against the existing index is enough for routine
  matching. If preflight reports `COUNTRY_SNAPSHOT_BUILDABLE` or
  `MASTER_ONLY_INDEX_BUILDABLE`, that's a first-time build, not a
  disallowed rebuild — build it once before relying on
  `reference_lookup.py`, since it silently returns zero rows with no
  index at all.

## Research rules for this assignment

- Approved domains only: `config/allowed_domains.txt`. Never fetch
  outside this list, never route around it.
- Prefer the original polling firm's own site over an aggregator or
  secondary write-up when both are approved domains.
- **One researcher pass per source batch when possible** — hand the
  researcher agent a batch of candidate URLs/date-ranges for one
  pollster/domain at a time, not one agent call per individual poll.
- Preserve exactly what's retrieved, never paraphrase or invent:
  source URL, question wording, fieldwork dates, sample size, and the
  reported positive/neutral/negative values.
- **Deduplicate before the matcher** — if a batch retrieval turns up the
  same poll wave twice (same pollster, same fieldwork dates, same
  values), resolve that before candidates reach the matcher agent, not
  after.
- **Batch candidates to the matcher and to the validator** — pass a
  batch of extracted candidates through matcher/validator together
  (`python/validate_record.py`/`python/stage_changes.py` both support
  batch input) rather than one candidate per invocation.
- Any uncertain series match, unresolved wording, or inferred field
  (e.g. sample size inferred from a firm's known pattern rather than
  stated outright) routes to REVIEW. Never guess it into APPROVED.

## Production data

The production workbook stays untouched unless a human explicitly
requests a write. Only `python/apply_changes.py` (invoked by the
`excel-writer` agent) may write it, and only for a record that is
freshly staged and re-validated as APPROVED.
`.claude/hooks/pollitik_guard.py` blocks every other route — this is
enforced, not just documented.

## Outputs stay separated

- `data/processed/canada_pm_approval_main.csv` — APPROVED-only,
  visualization-ready. A real research/staging run in *this* workspace
  writes here. Gitignored — absent in a fresh clone.
- `data/processed/canada_pm_approval_review.csv` — REVIEW-only,
  visualization-ready shape. Same as above: local, gitignored, written by
  a real run in this workspace.
- `data/processed/canada_assignment1/canada_pm_approved_final.csv` —
  the finalized/audit output of an assignment run (staging schema, full
  provenance columns). This is a different file with a different schema
  from `canada_pm_approval_main.csv` above — never pass it to
  `python/generate_visualization.py` directly.
- `countries/canada/data/canada_assignment1_approved.csv` — **tracked**,
  frozen copy of the finalized 29 APPROVED Assignment-1 records, same
  visualization-ready schema as `canada_pm_approval_main.csv`. This is
  what makes Canada work as a worked example in a fresh clone: no local
  research run has to happen first for a student to ask validated
  questions or generate a graph.
- `countries/canada/data/canada_assignment1_review.csv` — **tracked**,
  frozen copy of the finalized 10 REVIEW records, same shape plus one
  extra column (`Validation Reason`) carrying each record's real,
  deterministically-joined validation reason. Never plotted, never
  treated as validated.

See `countries/canada/output/README.md` for how the local files relate
to the staging file they're derived from, and
`countries/canada/data/README.md` for the tracked files.

## Student data-access policy

Same policy as `docs/student_workflow.md` "Student data-access policy"
(read that for the full policy and its 2026-08-25 history) — this
section only restates it in the context of this assignment's specific
files.

The tracked/local datasets this assignment answers questions from
(`canada_assignment1_approved.csv`, `canada_assignment1_review.csv`,
`canada_reference_snapshot.csv`, and their local `data/processed/`
counterparts) are this student's own assignment data — not secret. A
student may ask for a summary, inspect their own APPROVED/REVIEW rows,
ask about REVIEW cases, request graphs, and explicitly request the CSV
itself or its file path — all of that is answered directly, not
refused. What stays protected is unchanged: the production/master
workbook (`data/master/pollitik_master.xlsx`, writable only via
`python/apply_changes.py`) and any other country's/student's data.

## Deterministic result routing — never inferred

Two files can legitimately exist for "the APPROVED Canada dataset" at
once (a fresh local run's output, and the tracked worked-example
snapshot). Which one answers a student's question is decided by
`python/resolve_assignment_dataset.py`, not by Codex's judgment:

```
python python/resolve_assignment_dataset.py --country Canada --purpose approved
python python/resolve_assignment_dataset.py --country Canada --purpose review
```

Precedence (enforced inside the script, not a convention to remember):

1. If a finalized local result exists in this workspace
   (`data/processed/canada_pm_approval_main.csv` /
   `..._review.csv`) and its mtime is **newer** than the tracked file's,
   use the local result.
2. Otherwise, use the tracked worked-example snapshot
   (`countries/canada/data/canada_assignment1_approved.csv` /
   `..._review.csv`).
3. `canada_reference_snapshot.csv` is never a candidate output of this
   script — it has no code path that can return it. Reference/duplicate
   lookup is a completely separate tool
   (`python/reference_lookup.py` against the DuckDB index built from the
   snapshot) and never goes through this resolver.

Route every student question through this table, always resolving
`--purpose` first and passing the script's `resolved_path` on as the
input to whatever comes next — the student never supplies a filename:

| Student question | `--purpose` | Then |
|---|---|---|
| Validated summary / trend / min-max / "which pollsters" | `approved` | Answer directly from the resolved CSV. |
| "What should I be careful about" / REVIEW awareness | `review` | Answer directly from the resolved CSV, using its `Validation Reason` column. |
| Graph recommendation | `approved` | Feed the resolved path to `python/generate_visualization.py` as `--input` (recommend mode). |
| Graph generation ("generate graph option N" or a named type) | `approved` | Same resolved path, `python/generate_visualization.py --graph <type>` or `--select-option N`. |
| Reference/duplicate lookup | *(not this script)* | `python/reference_lookup.py --country Canada` against the index built from `canada_reference_snapshot.csv`. |

## Graph workflow

**Route every incoming graph request through the deterministic resolver
first — never judge "vague vs specific" by reading the request
yourself:**

```
python python/generate_visualization.py --resolve-request "<student's exact text>"
```

This is a pure text classifier (no `--input`/`--config` needed) that
prints exactly one of `recommend` / `approval_over_time` /
`series_spread` / `snapshot_comparison` / `all` and exits — nothing is
generated. Any request that doesn't name a specific graph type (e.g.
"Generate a graph of the Canada results.", "Make a graph for this
assignment.", "Show me a visualization.") deterministically resolves to
`recommend`; Codex must not skip straight to a chart just because
Approval Over Time happens to rank first for this data. Act on the
result:

- `recommend` → run recommend mode below and stop. Do **not** generate
  any graph yet.
- `approval_over_time` / `series_spread` / `snapshot_comparison` → skip
  straight to generating that one chart (still subject to the same
  eligibility check `generate_chosen_graph()` always runs).
- `all` → generate all eligible charts.

Codex resolves the APPROVED input via `resolve_assignment_dataset.py`
above (never the `canada_assignment1/canada_pm_approved_final.csv` audit
file — see "Outputs stay separated"), ranks the top eligible graph types
from `config/visualization_rules.yaml`, and presents them to the student
as a numbered, human-readable list (display name + one-line reason
each) — **never** the internal graph type id
(`approval_over_time`/`series_spread`/`snapshot_comparison`/
`leader_comparison_grid`; those exist in code/config only, and are never
shown to the student even when `--resolve-request` itself is one of
those tokens internally). The student answers with an option number,
the display name, an unambiguous natural description ("make the trend
graph", "latest pollster comparison"), or "all three", and
`python/generate_visualization.py` generates the resolved chart(s)
automatically with full Pollitik styling. Codex resolves every path
itself — the student never provides a CSV path and never hand-configures
axes, colors, legends, or the trend line. See
`docs/visualization_rules.md` and `countries/canada/README.md`.

**Recommend, then resolve the student's reply deterministically:** pass
`--state-file <local gitignored path, e.g.
data/processed/recommendation_state/canada.json>` on the recommend-mode
call so the ranked list is saved; resolve the follow-up reply against
that same file instead of re-deriving it from the model's memory of the
earlier printed list — `--select-option N --state-file <same path>` for
a bare option number, or `--reply "<student's text>" --state-file <same
path>` for a display name, natural description, or "all three" (see
`resolve_student_choice()` in `python/generate_visualization.py`). An
ambiguous reply prints a short clarification (the same numbered,
human-readable list) instead of guessing — ask the student to pick
again rather than inferring which graph they meant. The state file must
stay local/gitignored (`data/processed/*` is already ignored by
`.gitignore` — nothing extra to configure) and is never itself the
source of truth for *which* APPROVED dataset to use; that's still
`resolve_assignment_dataset.py`.

**Grounding a graph explanation:** after generation, explain the graph
using (a) the JSON summary `generate_visualization.py` printed
(`graph_type`, `series_count`, `date_range`, `trend_method`,
`records_excluded_by_status`), (b) the generated HTML's own `<meta>`
tags and visible legend/footer, and (c) the matching `design` block in
`config/visualization_rules.yaml` (e.g. `approval_over_time.design.trend_line.note`
for what the trend line actually is). Never fall back to generic
chart-reading assumptions the data/config don't support.

## Filesystem access note (superseded "known limitation", 2026-08-25)

`countries/canada/data/canada_assignment1_approved.csv` and
`canada_assignment1_review.csv` are tracked, plaintext files, directly
readable through ordinary repository access (the `Read` tool, `cat`, a
text editor) — `.claude/hooks/pollitik_guard.py` has no rule for `Read`
at all, and its `Bash`/`Write`/`Edit` checks only protect the
*production* workbook (`data/master/pollitik_master.xlsx`) and the
WebFetch domain allow-list. Under the 2026-08-25 student-data-access
policy correction, this is no longer a gap: a student directly reading
their own tracked assignment CSV is exactly as acceptable as Codex
handing it to them on request — there is nothing left to close here.
The hook's actual job remains protecting `data/master/pollitik_master.xlsx`
and the WebFetch domain allow-list, and it still does that (see
`tests/test_student_data_access_boundary.py`, which documents both: the
tracked CSVs are freely readable, and the production workbook/allow-list
protections remain enforced).
