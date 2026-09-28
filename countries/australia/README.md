# Australia — Prime Minister approval assignment

Built following `docs/country_blueprint.md` (the Canada blueprint's
structure), with Australia's own data and metadata throughout. Read
`countries/australia/AGENTS.md` before doing any work here — this file
is the overview, that one is the operating rules.

## What this assignment is

Collecting and validating survey-based public support data for the
Australian **Prime Minister** as an individual office-holder, then
producing a clean, visualization-ready dataset and letting a student
generate an approved-style chart from it. No Assignment-1 research run
has happened yet in this repository — this workspace currently prepares
the existing-data/reference layer so a student can understand what is
already known before conducting the missing research themselves.

## What qualifies

- Job approval / disapproval of the PM specifically
- Job satisfaction / dissatisfaction
- Overall performance
- Favorable / unfavorable opinion, positive/negative image or
  "impression"
- General approval / general satisfaction / sympathy

## What does not qualify

- Government-as-a-whole approval (`CSES` — its EAD wording explicitly
  targets "the government"/"the president," not the PM)
- Issue-specific approval (economy, immigration, healthcare, etc.)
- Vote-intention, preferred-PM, or head-to-head leader-preference
  questions
- Continuous 1-10 / 1-100 grading scales
- Trust/confidence in the PM (no Australia exception currently exists)

## Requires verification before use

`FOX&HEDGEHOG`, `FreshwaterStrategy` / `Freshwater Strategy`,
`GALLUPWORLD_LSHP`, `GALLUPWORLD_LDR` — see the reference profile for
exactly why each is flagged rather than classified in or out of scope.

Full detail and reasoning: `countries/australia/AGENTS.md` and
`.claude/skills/australia-pm-approval/SKILL.md`.

## Where the data actually lives

This folder is instructions and prompts only, plus one small tracked
exception under `countries/australia/data/`:

- `australia_reference_snapshot.csv` — an Australia-only export of
  existing *historical* reference observations (16 raw Series, 1,836
  records, 1968–2026). Exists so a fresh workspace can build a real
  local reference index (`data/reference_index.duckdb`) without needing
  the production master workbook — see
  `countries/australia/data/README.md`. **Not** Assignment-1 output;
  never used to answer a validated-data or REVIEW question.
  `python/resolve_assignment_dataset.py` has no code path that can
  return this file.

No tracked Assignment-1 results
(`australia_assignment1_approved.csv` / `..._review.csv`) exist yet —
those are only ever produced by
`python/build_country_assignment_snapshot.py` from a real, completed
local research/staging run for Australia, which has not happened in
this repository.

Everything else stays at the real, shared, gitignored locations a real
research run in this workspace would produce:

- `data/staging/candidates.jsonl` — every staged Australia candidate,
  all statuses (APPROVED/REVIEW/REJECTED), full audit trail.
- `data/master/pollitik_master.xlsx` — the production workbook. Written
  to only via `python/apply_changes.py`. Not needed for research or
  duplicate-checking — the local reference index is.
- `data/processed/australia_pm_approval_main.csv` /
  `australia_pm_approval_review.csv` — the current run's
  visualization-ready APPROVED/REVIEW outputs, if this workspace has
  actually done research.
- `data/processed/australia_assignment1/` — the finalized/audit output
  of an assignment run, once one has happened.
- `data/processed/visualizations/` — generated charts.

See `countries/australia/data/README.md` and
`countries/australia/output/README.md` for more on this split.

## How a student runs the workflow

A fresh clone needs none of `data/master/pollitik_master.xlsx`, a
pre-built `data/reference_index.duckdb`, or any manual DuckDB command —
`run_assignment.txt` runs the preflight check, builds the local index
from `australia_reference_snapshot.csv` automatically if needed, and
only then proceeds. See `docs/student_workflow.md` for the full order.

Use the short prompts in `countries/australia/prompts/`, or type the
equivalent yourself — see `docs/prompt_guide.md` for why short prompts
are enough:

1. `countries/australia/prompts/run_assignment.txt` — start/resume the
   full pipeline.
2. `countries/australia/prompts/continue_research.txt` — resume at the
   next unresolved source batch.
3. `countries/australia/prompts/review_results.txt` — see current
   APPROVED/REVIEW/REJECTED counts and what the REVIEW cases need (says
   so plainly if no results exist yet).

## How a student gets graph recommendations

Same mechanics as every other country (see `countries/canada/README.md`'s
"How a student gets graph recommendations" section) —
`countries/australia/prompts/recommend_graphs.txt` and
`generate_graph.txt` resolve the current APPROVED dataset via
`python/resolve_assignment_dataset.py --country Australia`. Until a
research run produces one, there is nothing to recommend or graph, and
Codex says so rather than fabricating a chart.

Full mechanics: `docs/visualization_rules.md`,
`config/visualization_rules.yaml`, `python/generate_visualization.py`.
