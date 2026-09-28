# Canada output (placeholder folder)

This folder is organizational/student-facing only — it does not hold
any real output files, and nothing should be copied into it. Its job is
to point at where generated outputs actually land.

## Real output locations

- **Finalized/audit assignment output**:
  `data/processed/canada_assignment1/canada_pm_approved_final.csv`
  (with its sibling `canada_pm_review.csv` and that folder's copy of the
  master workbook) — the full staging-schema audit trail (`record_id`,
  `validation_status`, `validation_reason`, `source_url`, etc.) for this
  assignment run. Despite the name, this is **not** the file
  `python/generate_visualization.py` reads — its column names don't
  match what the generator expects. Local/gitignored only.
- **Visualization-ready APPROVED dataset (local run)**:
  `data/processed/canada_pm_approval_main.csv` — Date, Approval, Prime
  Minister, Party, Series, Source, Status. APPROVED rows only. Written
  only if this workspace has actually run the research/staging pipeline
  this session. Local/gitignored — absent in a fresh clone.
- **Visualization-ready APPROVED dataset (tracked worked example)**:
  `countries/canada/data/canada_assignment1_approved.csv` — same exact
  schema as the local file above, a frozen copy of the finalized 29
  APPROVED records. This is what a fresh clone has instead of the local
  file, and what makes the six-prompt student workflow work with zero
  research run required.
- **REVIEW datasets**: `data/processed/canada_pm_approval_review.csv`
  (local run) and `countries/canada/data/canada_assignment1_review.csv`
  (tracked, with an added `Validation Reason` column) — kept separate on
  purpose; never merged into an APPROVED file, never plotted.
- **Generated charts**: `data/processed/visualizations/` — e.g.
  `canada_pm_approval.html`, produced by
  `python/generate_visualization.py` after a student picks a graph type
  from the recommendations.
- **Recommendation state (local, gitignored)**:
  `data/processed/recommendation_state/canada.json` — the ranked list a
  `--recommend`-mode run saved via `generate_visualization.py
  --state-file`, so a follow-up "generate graph option N" resolves
  deterministically instead of relying on conversation memory. Nothing
  should ever read this file as if it were assignment data — it only
  ever holds `{option, graph_type, reason}` entries.

Three files legitimately have "approved" in their name or contents —
they are not interchangeable, and never picked by guesswork.
`python/resolve_assignment_dataset.py --country Canada --purpose
approved` is the single deterministic answer for "which APPROVED file":
the local run's output if it exists and is newer, otherwise the tracked
worked-example file. Both `countries/canada/prompts/recommend_graphs.txt`
and `generate_graph.txt` go through that resolver; a student never
names, chooses, or types a CSV path for graphing.

Do not copy the master workbook or the staging file's contents here —
these are derived, regenerable outputs, not a second copy of the source
data. Re-running the pipeline/generator is how you refresh the local
ones; re-running `python/build_country_assignment_snapshot.py` (by the
project owner, only when the finalized results materially change) is how
you refresh the tracked ones.
