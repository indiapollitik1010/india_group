# Canada — Prime Minister approval assignment

Worked example for `docs/country_blueprint.md`. Read
`countries/canada/AGENTS.md` before doing any work here — this file is
the overview, that one is the operating rules.

## What this assignment is

Collecting and validating survey-based public support data for the
Canadian **Prime Minister** as an individual office-holder, then
producing a clean, visualization-ready dataset and letting a student
generate an approved-style chart from it.

## What qualifies

- Job approval / disapproval of the PM specifically
- Job satisfaction / dissatisfaction
- Overall performance
- Favorable / unfavorable opinion, positive/negative image or
  "impression"
- General approval / general satisfaction / sympathy

## What does not qualify

- Government approval as a whole (`*GOV`-suffixed series)
- Issue-specific approval (economy, immigration, healthcare, etc.)
- Vote-intention, preferred-PM, or head-to-head leader-preference
  questions
- Continuous 1-10 / 1-100 grading scales
- Trust/confidence in the PM (no Canada exception currently exists)

Full detail and reasoning: `countries/canada/AGENTS.md` and
`.claude/skills/canada-pm-approval/SKILL.md`.

## Where the data actually lives

This folder is instructions and prompts only, plus three small tracked
exceptions under `countries/canada/data/`:

- `canada_reference_snapshot.csv` — a Canada-only export of existing
  *historical* reference observations. Exists so a fresh workspace can
  build a real local reference index (`data/reference_index.duckdb`)
  without needing the production master workbook — see
  `countries/canada/data/README.md`. **Not** Assignment-1 output; never
  used to answer a validated-data or REVIEW question.
  `python/resolve_assignment_dataset.py` has no code path that can
  return this file.
- `canada_assignment1_approved.csv` — a frozen, tracked copy of the
  finalized **29 APPROVED** Assignment-1 records, in the same
  visualization-ready schema `python/generate_visualization.py` already
  expects. This is what lets a fresh clone answer validated-data
  questions and generate graphs without a research run first.
- `canada_assignment1_review.csv` — a frozen, tracked copy of the
  finalized **10 REVIEW** records, plus each record's real validation
  reason, for REVIEW-awareness questions. Never plotted, never treated
  as validated.

Everything else stays at the real, shared, gitignored locations a real
research run in this workspace would produce:

- `data/staging/candidates.jsonl` — every staged Canada candidate, all
  statuses (APPROVED/REVIEW/REJECTED), full audit trail.
- `data/master/pollitik_master.xlsx` — the production workbook. Written
  to only via `python/apply_changes.py`. Not needed for research or
  duplicate-checking — the local reference index is.
- `data/processed/canada_pm_approval_main.csv` /
  `canada_pm_approval_review.csv` — the current run's visualization-ready
  APPROVED/REVIEW outputs, if this workspace has actually done research.
- `data/processed/canada_assignment1/canada_pm_approved_final.csv` —
  the finalized/audit output of an assignment run (a different schema
  from the visualization-ready file above — see
  `countries/canada/output/README.md` for the distinction).
- `data/processed/visualizations/` — generated charts.

**Which one answers a given question is never guessed** —
`python/resolve_assignment_dataset.py --country Canada --purpose
{approved,review}` deterministically picks the newer of the local run's
output vs. the tracked snapshot above (falling back to the tracked
snapshot in a fresh clone, where no local output exists yet). See
"Deterministic result routing" in `countries/canada/AGENTS.md` for the
full routing table.

See `countries/canada/data/README.md` and
`countries/canada/output/README.md` for more on this split.

## How a student runs the workflow

A fresh clone needs none of `data/master/pollitik_master.xlsx`, a
pre-built `data/reference_index.duckdb`, or any manual DuckDB command —
`run_assignment.txt` runs the preflight check, builds the local index
from `canada_reference_snapshot.csv` automatically if needed, and only
then proceeds. See `docs/student_workflow.md` for the full order.

Use the short prompts in `countries/canada/prompts/`, or type the
equivalent yourself — see `docs/prompt_guide.md` for why short prompts
are enough:

1. `countries/canada/prompts/run_assignment.txt` — start/resume the
   full pipeline.
2. `countries/canada/prompts/continue_research.txt` — resume at the
   next unresolved source batch.
3. `countries/canada/prompts/review_results.txt` — see current
   APPROVED/REVIEW/REJECTED counts and what the REVIEW cases need.

## How a student gets graph recommendations

0. Whatever the student actually types for a graph request, Codex first
   runs `python python/generate_visualization.py --resolve-request
   "<student's text>"` — a deterministic text classifier, not a judgment
   call — to decide whether to recommend or generate directly. A vague
   request ("generate a graph of the results", "make a graph for this
   assignment") always resolves to `recommend`, so Codex shows the
   numbered options below and stops rather than silently picking
   Approval Over Time because it's ranked first.
1. `countries/canada/prompts/recommend_graphs.txt` — Codex resolves the
   current APPROVED dataset via `python/resolve_assignment_dataset.py`
   (the tracked `canada_assignment1_approved.csv` in a fresh clone, or a
   fresher local result if this workspace has actually done research),
   ranks the top eligible graph types (from `config/visualization_rules.yaml`)
   against it, and saves the ranked list to a local, gitignored state
   file. Nothing is generated yet.
2. Pick one of the ranked options — by number ("1"), by name ("Approval
   Over Time"), with a natural description ("make the trend graph",
   "latest pollster comparison"), or say "all three" for every eligible
   graph. You never need an internal graph type id.
3. `countries/canada/prompts/generate_graph.txt` (or just say which
   option/name/description you picked) — Codex resolves your reply
   deterministically from the saved state (never by re-reading its own
   earlier reply from memory, and never guessing an ambiguous reply) and
   `python/generate_visualization.py` generates that chart automatically,
   fully styled, against the same resolved dataset. If your reply is
   ambiguous, Codex asks a short clarification with the same numbered
   options instead of guessing. You never set axes, colors, legends, or
   a CSV path by hand.

Full mechanics: `docs/visualization_rules.md`,
`config/visualization_rules.yaml`, `python/generate_visualization.py`.
