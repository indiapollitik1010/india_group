# Pollitik Visualization Rules

Project-resident specification for the student graph-generation workflow.
Replaces Flourish as the visualization target: Codex **ranks** a short
list of suitable charts from the approved list below, the student picks
one, and Codex builds it with full Pollitik styling applied automatically.
Codex never forces a single chart on the student, and the student never
hand-configures axes, colors, legends, or other chart detail.

**Provenance:** the underlying Pollitik graph/style conventions were
shared by the project owner directly in conversation (not retrieved from
the web, and not present anywhere else in this repository). This document
and `config/visualization_rules.yaml` are the first place they are
recorded in-project. Treat both files as the authoritative source going
forward — do not re-derive or re-guess these rules from web research or
general design conventions.

## 1. Approved graph types

### `approval_over_time`
- **Use when:** exactly one executive; at least 8 APPROVED observations;
  at least 2 distinct dates.
- **Do not use when:** more than one executive is present, or there are
  too few observations/dates to support a time-series read.
- **Design:** individual polling observations shown as points, grouped
  (colored) by polling `Series`. An optional pooled trend line may be
  added, but only when the trend method (e.g. rolling average, LOESS,
  window size) is explicitly defined — never an unspecified/default
  smoother.
- **Never** connect points within a single sparse pollster series merely
  to imply continuity — a 1–2 point series stays as unconnected points.
- **Applies to:** time series, single leader.

### `leader_comparison_grid`
- **Use when:** at least 2 executives exist with comparable
  approval time-series data.
- **Design:** small multiples — one executive per panel.
- **Applies to:** time series, multiple leaders, comparison.

### `snapshot_comparison`
- **Use when:** comparing leaders, countries, or pollsters at one
  selected or latest date; or when a time series has too few
  observations to justify a trend read.
- **Design:** each Series' bar shows its own latest reading *and* the
  date of that observation (different Series can have different "latest"
  dates, so the date must travel with the value — never just the bare
  percentage).
- **Reader-facing wording:** explains what the chart shows; never calls
  itself a "fallback chart" — once the student has deliberately picked
  it (by type or by recommendation option), it's not a fallback from
  their point of view.
- **Applies to:** comparison, magnitude, single point in time.

### `series_spread`
- **Use only** as a secondary/diagnostic graph for comparing pollster
  dispersion or house effects.
- **Do not use** as the primary visualization when the assignment asks
  for change over time.
- **Reader-facing wording:** state plainly that it compares the observed
  values reported by each polling Series, that it is diagnostic/
  secondary, and that it does not by itself prove a stable pollster
  house effect. Per-Series observation counts can be highly uneven (a
  1-poll firm next to a 16-poll firm); when any Series has very few
  observations, add a visible caution that it should be interpreted
  carefully and that a 1-2 point series does not show a real
  distribution or a stable pattern.
- **Applies to:** distribution, pollster comparison.

## 2. Recommend, then the student chooses

REVIEW and REJECTED records are filtered out **before** anything below
runs — recommendations are computed from APPROVED records only, so a
REVIEW/REJECTED row can never change what gets ranked or recommended.

The student workflow is:

0. **Before anything else, Codex routes the student's exact request text
   through the deterministic resolver** —
   `python/generate_visualization.py --resolve-request "<text>"` — rather
   than judging "vague vs specific" itself. This is a pure text
   classifier (no `--input`/`--config`, nothing generated) that prints
   one of `recommend` / `approval_over_time` / `series_spread` /
   `snapshot_comparison` / `all`. A request that doesn't name a specific
   graph type always resolves to `recommend`, even though
   `approval_over_time` is priority-ranked first below — Codex must not
   skip step 3 just because the top-ranked type happens to match what a
   vague request would probably want. Only a `recommend` result runs
   steps 1–3 below; a specific-type or `all` result skips straight to
   step 5 for that type (still subject to the same eligibility check).
1. Codex reads the assignment and the APPROVED data.
2. Codex checks each approved graph type's eligibility (the `requires`
   thresholds in `config/visualization_rules.yaml`) against the data's
   shape (executive count, observation count, distinct dates, distinct
   Series) and ranks the eligible types, highest priority first, capped
   at `recommendation.max_recommendations` (currently 3).
3. Codex prints the ranked options as a numbered, human-readable list
   (e.g. "1. Approval Over Time — ...") with a one-line reason each — it
   does **not** generate a chart yet, and it never asks the student to
   reply with an internal graph type id
   (`approval_over_time`/`series_spread`/`snapshot_comparison`/
   `leader_comparison_grid`). Those ids exist in code/config only.
4. The student answers with an option number ("1"), the graph's display
   name ("Approval Over Time"), an unambiguous natural description
   ("make the trend graph", "latest pollster comparison"), or "all
   three" for every eligible type. `python/generate_visualization.py
   --reply <text> --state-file <path>` resolves this deterministically
   via `resolve_student_choice()` — never guessed from conversation
   memory — against the saved ranked list; an ambiguous reply gets a
   short clarification (the same numbered list) instead of a guess.
5. Codex generates the resolved chart(s) automatically, with full
   Pollitik styling (colors, legend, axes, title, provenance note)
   already applied. The student never sets any of that by hand, and
   never needs to know or type the internal `--graph <type>` value
   themselves.

Eligibility (unchanged in meaning from the old single-selection rule,
now used as a per-type filter instead of a first-match branch):

```
leader_comparison_grid  eligible when distinct(executives) >= 2
approval_over_time      eligible when executives == 1
                                  and rows >= 8
                                  and distinct(dates) >= 2
series_spread           eligible when distinct(Series) >= 2
snapshot_comparison     eligible when distinct(Series) >= 2
```

Ranking priority when more than one type is eligible: `leader_comparison_grid`
› `approval_over_time` › `series_spread` › `snapshot_comparison` (see
`recommendation.priority_order` in the YAML). If the student requests a
type that is not eligible for their data (e.g. `leader_comparison_grid`
with only one executive present), Codex refuses with a clear reason
instead of generating a misleading chart.

**Resolving the student's choice deterministically:** the recommend
step can save its ranked list to a small local, gitignored JSON file
(`generate_visualization.py ... --state-file <path>`). A later, separate
invocation resolves the student's reply against that saved file instead
of the model re-deriving it from its own earlier printed text —
`--select-option N --state-file <same path>` for a bare option number,
or `--reply "<text>" --state-file <same path>` for a display name, a
natural description, or "all three" (see `resolve_student_choice()` in
`python/generate_visualization.py`). See `docs/student_workflow.md` for
why this matters across a summarized/compacted session. `--input` for
every call is always the same country dataset resolved by
`python/resolve_assignment_dataset.py`, never a path the student
supplies.

## 3. Pollitik style rules

Confirmed brand colors (use these before introducing any other color):

| Color | Hex |
|---|---|
| Amber | `#FFB400` |
| Blue | `#00A6ED` |
| Orange-red | `#F6511D` |
| Off-white | `#FBFBF2` |

General rules:
- Clear, descriptive title.
- Readable dates (native date format, not raw serials/strings).
- Approval values displayed as percentages.
- Clean/light plot area, based on `#FBFBF2` where appropriate.
- Legend placed below the chart when a legend is needed.
- Include source/provenance information on or alongside the chart.
- Maintain consistent styling across countries.

## 4. Data-quality rules

- REVIEW and REJECTED records must never appear in the main
  visualization.
- Do not invent PM, party, dates, values, or source information —
  every plotted field must trace back to an APPROVED staged/production
  record.
- If a required field is genuinely unavailable on an APPROVED record
  (e.g. missing sample size), leave it blank; never substitute an
  inferred or default value.

## 5. Current Canada assignment — recommended ranking

Given the current `data/processed/canada_pm_approval_main.csv` (APPROVED
only):

- 29 APPROVED observations
- 1 executive: Mark Carney
- 5 polling Series
- Dates 2025-09-12 through 2026-08-08
- Irregular polling frequency

`leader_comparison_grid` is not eligible (only 1 executive present) and
is excluded from ranking entirely. The three remaining types are all
eligible and ranked:

1. **`approval_over_time` — recommended.** Best for showing how Mark
   Carney approval changes over time.
2. **`series_spread`.** Useful for showing differences across polling
   firms.
3. **`snapshot_comparison`.** Useful for comparing pollsters at a
   selected/latest point, when the data supports a fair comparison.

Codex presents these three to the student as a numbered, human-readable
list ("1. Approval Over Time", "2. Series Spread", "3. Snapshot
Comparison") and accepts a reply by number, display name, natural
description, or "all three" — never requiring the `--graph <type>`
values shown above, which are for Codex's own script invocation, not
for the student to type. Codex does not generate any of them until that
choice is made.

## 6. Natural-language routing refinements (2026-08-25)

Small, targeted fix to `resolve_request()` — the initial-request
classifier only (never `resolve_student_choice()`, which resolves a
reply to an already-shown, already-eligible list and was already
correct). Before this change, a bare `"compare"`/`"comparison"` keyword
routed every comparison-shaped request to `snapshot_comparison`, which
conflated two structurally different things this project can compare:
executives (`leader_comparison_grid`) and polling Series
(`series_spread`/`snapshot_comparison`). "Compare these leaders." could
resolve to a pollster chart.

`resolve_request()` now checks the comparison *subject* first:

- Leader-subject wording ("leader(s)", "candidate(s)") — with or
  without "over time" also present — resolves to
  `leader_comparison_grid`. Eligibility (≥2 executives) is still decided
  entirely by `graph_eligibility()`, exactly as before; a single-leader
  dataset gets the same clear refusal-plus-alternatives message any
  other ineligible `--graph` choice gets.
- Pollster-subject wording ("pollster(s)", "polling firm(s)", "firm(s)")
  combined with "latest"/"snapshot" resolves to `snapshot_comparison`;
  combined with "compare"/"comparison"/"spread"/"dispersion"/"house
  effect" (and no "latest"/"snapshot") resolves to `series_spread`.
- No subject at all falls back to the original, narrower keyword table
  (`trend`/`over time`, `spread`/`dispersion`/`house effect`,
  `snapshot`/`latest`) — a bare `"compare"` with no named subject and no
  other keyword is genuinely ambiguous and still resolves to
  `recommend`, never a guess.

**Unsupported chart forms** (pie chart, donut chart, word cloud) are
checked before anything else and resolve to `unsupported:<key>` instead
of `recommend`/a type/`all`. `--resolve-request` prints the token plus a
second line with a short, student-facing, data-grounded reason (e.g. "a
pie chart is not appropriate for these approval observations because
these are repeated approval observations over time, not parts of one
total"). Codex relays that line, then runs ordinary recommend mode in a
separate invocation — the same two-call pattern every other
`resolve_request()` outcome already uses — so the student still sees
their real eligible options. `pie_chart`/`donut_chart`/`word_cloud` are
not, and will never be, entries in `RENDERERS`; passing one to
`--graph` directly fails the same way any unapproved type does.

**Standalone SVG output:** every successful render now writes a
`.svg` file next to the `.html` output (same basename), extracted
directly from the chart's own already-built `<svg>` markup — no new
dependency. The JSON summary's `output_formats` (e.g. `["HTML",
"SVG"]`) and `student_summary` (e.g. "Your graph was generated as HTML
and SVG.") fields exist so Codex can tell the student what was produced
without reciting internal file paths or the generator's own script
name. PNG export is unchanged and remains best-effort only (`cairosvg`,
if importable — still not a project dependency).

## 7. Follow-up work (explicitly deferred, not implemented in this pass)

The following were evaluated but intentionally left for a later,
separately-reviewed change, not built partially:

- `net_approval_over_time` and the `Positive`/`Negative`/`Net` schema
  expansion to the visualization-ready CSV.
- `change_over_period` ("which leader improved the most").
- A dedicated latest-approval-by-leader renderer (distinct from
  `snapshot_comparison`, which compares Series, not executives).
- Cross-country small multiples (the CSV schema has no `Country`
  column today).
- R/R-CAL integration of any kind.
- Adding `cairosvg` (or any other PNG-rasterization dependency) to
  `requirements.txt`.
