# Student workflow

What actually happens, in plain language, from typing a short prompt to
getting a chart. This describes the pipeline that already exists in
this repo (Skills, agents, `python/*.py`) — it does not add new
behavior, it explains the behavior that's already there so you don't
have to read the Skill files cover-to-cover before your first prompt.

## Classroom setup comes first, and needs no `pip install`

Before any of the research pipeline below runs, three one-time setup
steps happen: create the country workspace, generate its reference
snapshot, generate its EAD series/question-wording CSV. All three are
handled by one dependency-free command —

    python python/student_workspace_setup.py --country <Country>

— which imports only the Python standard library and reads only the two
tracked shared CSVs (`data/reference/pollitik_reference.csv`,
`data/reference/ead_series_question_wording.csv`). It never needs
`requirements.txt` installed and never needs the hidden
`data/master/` Excel workbooks. Codex runs this automatically for a
setup-shaped prompt ("create my country workspace," "generate the
reference snapshot") — see the root `AGENTS.md` "Classroom setup"
section — and does **not** run `python/check_python_dependencies.py`
first for it. The dependency check below applies only once real
research starts.

## The pipeline

```
Assignment prompt (you)
  -> dependency check              (python/check_python_dependencies.py -
                                    read-only, installs nothing; STOP
                                    here if dependencies_ready=false)
  -> preflight check              (python/check_assignment_preflight.py
                                    --country <Country>)
  -> build local index if needed   (only when preflight reports
                                    COUNTRY_SNAPSHOT_BUILDABLE - built
                                    automatically from the country's
                                    tracked reference-snapshot CSV, then
                                    preflight runs again)
  -> STOP here if still SAFE_TO_RESEARCH=false
  -> repo instructions            (AGENTS.md, CLAUDE.md)
  -> country rules                (countries/<country>/AGENTS.md,
                                    .claude/skills/<country>-pm-approval/SKILL.md)
  -> existing reference data       (canada.md reference profile,
                                    python/reference_lookup.py against
                                    the derived DuckDB index)
  -> researcher / web fetch        (approved domains only,
                                    config/allowed_domains.txt)
  -> candidate extraction          (multilingual-extractor agent,
                                    exact wording/values preserved)
  -> deduplication                 (same poll wave found twice -> one record)
  -> matcher                       (which existing Series does this
                                    belong to? or REVIEW if unclear)
  -> validator                     (python/validate_record.py +
                                    python/stage_changes.py -
                                    provenance, arithmetic, required
                                    fields, all deterministic)
  -> APPROVED / REVIEW / REJECTED  (data/staging/candidates.jsonl)
  -> clean outputs                 (data/processed/*_main.csv,
                                    *_review.csv)
  -> result-precedence resolver    (python/resolve_assignment_dataset.py
                                    --country <Country> --purpose
                                    {approved,review} - deterministically
                                    picks this run's local output if it's
                                    newer, otherwise the country's tracked
                                    worked-example snapshot; see below)
  -> answer validated/REVIEW questions directly from the resolved CSV
  -> graph recommendations         (config/visualization_rules.yaml,
                                    against the same resolved CSV;
                                    ranked list saved to a local state
                                    file via --state-file)
  -> you choose a graph (by type or by ranked option number)
  -> graph generation              (python/generate_visualization.py
                                    --graph <type> or --select-option N
                                    --state-file <same path>)
```

## Why there's a result-precedence resolver before answering any question

A fresh clone ships a small, tracked, frozen worked-example result per
country - `countries/<country>/data/<country>_assignment1_approved.csv`
and `..._review.csv` - precisely so the six-prompt student workflow
(summarize the trend, find the min/max, explain REVIEW cases, recommend
graphs, generate one, explain it) works with zero research run required.
But a workspace that *has* done real research this session also has a
local, gitignored `data/processed/<country>_pm_approval_main.csv` /
`..._review.csv`, and both can legitimately exist at once. Which one is
"the" validated dataset for a given question is never left to inference:

- **If a finalized local result exists and is newer** than the tracked
  snapshot, use it - this session's own work takes precedence.
- **Otherwise**, fall back to the tracked worked-example snapshot - this
  is what makes a fresh clone answer correctly on the first prompt.
- **The historical reference snapshot
  (`<country>_reference_snapshot.csv`) is never a substitute** for
  either - it's for duplicate-checking only, and
  `python/resolve_assignment_dataset.py` has no code path that can
  return it.

`python/resolve_assignment_dataset.py --country <Country> --purpose
{approved,review}` is the single deterministic decider (mtime
comparison of the two candidate files, read-only, no side effects).
Reference/duplicate lookup stays a completely separate tool
(`python/reference_lookup.py` against the index built from the
reference snapshot) and never goes through this resolver.

## Why "generate graph option N" doesn't rely on conversation memory

`python/generate_visualization.py`'s recommend mode can persist its
ranked list to a small local JSON file (`--state-file <path>`, kept
gitignored under `data/processed/`). A follow-up "generate graph option
N" resolves N against that saved file (`--select-option N --state-file
<same path>`) instead of the model re-deriving it from its own earlier
printed text - deterministic even if the session's context has been
summarized or compacted in between.

Every arrow above is a real, already-built step — nothing here is
aspirational. Your prompt just tells Codex where in this pipeline to
start or resume; see `docs/prompt_guide.md`.

## Why there's a dependency check before preflight

A fresh workspace's Python *environment* is separate from the repo code
itself: you can have the correct branch, `AGENTS.md`, a country's
tracked reference snapshot, and the preflight script all present, while
`pip install -r requirements.txt` has never actually been run in that
environment. `duckdb` (used inside `python/build_reference_index.py`
and `python/reference_lookup.py`) is already declared in
`requirements.txt` - this was never a missing declaration - but a
missing install previously surfaced as a raw `ModuleNotFoundError`
partway through the index-build step, which isn't a clear instruction
for a student.

`python/check_python_dependencies.py` runs first and catches this. It
never installs anything and never touches the network - it only checks
whether the packages already declared in `requirements.txt` are
importable in the current interpreter, and reports one canonical fix:
run `pip install -r requirements.txt` once, from the repo root. If it
reports `dependencies_ready=false`, stop before preflight and before any
research or staging - this is always an environment/setup problem, never
a NOT_FOUND/REVIEW/REJECTED data outcome.

## Why there's a preflight check before research

A brand-new workspace (e.g. a fresh Codex sandbox, or any clone that
hasn't had the data files added yet) can have the repo code and a
country's `AGENTS.md` without having `data/reference_index.duckdb`,
`data/master/pollitik_master.xlsx`, or any local staging history — all
three are git-ignored, not part of the repo's tracked code. Without a
check, nothing stops research from starting anyway: the low-token
lookup tool (`python/reference_lookup.py`) just quietly reports "index
not found, zero rows" when the index is missing, which looks the same
as "checked, no duplicates" if you're not watching for it.

`python/check_assignment_preflight.py --country <Country>` is a
read-only gate that runs first and catches this. It never fetches the
web, never stages anything, and never builds or creates a missing file
itself (including the reference index) — it only reports what's
actually present and computes `SAFE_TO_RESEARCH`, via
`reference_data_status`:

- **`REFERENCE_INDEX_PRESENT`** — `SAFE_TO_RESEARCH: true`. A local
  index already exists; sufficient even without the master workbook.
- **`COUNTRY_SNAPSHOT_BUILDABLE`** — `SAFE_TO_RESEARCH: false` *until
  the index is actually built*. The country's small tracked reference
  snapshot (`countries/<country>/data/<country>_reference_snapshot.csv`)
  is present but no local index has been built from it yet. The
  snapshot's mere presence is never treated as sufficient — the
  assignment prompt builds the index automatically (the exact command
  is in the report's `suggested_index_build_command` field) and
  re-checks before continuing. You never need to type that command
  yourself, and it never touches the production workbook or the web.
- **`MASTER_ONLY_INDEX_BUILDABLE`** — `SAFE_TO_RESEARCH: true` (an
  instructor/production workspace case). The master workbook is present
  but no index yet; build one via `python/build_reference_index.py`
  before trusting `reference_lookup.py`, which otherwise silently
  returns zero rows.
- **`NO_REFERENCE_DATA`** — `SAFE_TO_RESEARCH: false`. None of the
  index, the country snapshot, or the master workbook is present; there
  is no way to check a new candidate against existing data. STOP.

`SAFE_TO_RESEARCH` is also `false` if the approved-domain list is
missing or has no usable domains, or if the root or country `AGENTS.md`
is missing — explain the reported `reason` and don't research or stage
until it's resolved. An empty or missing `data/staging/candidates.jsonl`
is **never** evidence either way — it doesn't make an otherwise-unsafe
workspace safe, and its absence doesn't count against an
otherwise-safe one.

## What the three statuses mean

- **APPROVED** — the record passed every deterministic check: the
  source was actually retrieved (never a model-guessed URL), the
  reported numbers add up, every required field is present, and the
  series match was confident. This is what feeds the main
  visualization.
- **REVIEW** — something about the record needs a human judgment call:
  an ambiguous series match, a sample size that had to be inferred
  rather than read directly, an unresolved question wording, a
  duplicate that needs a human tie-breaker. REVIEW records are **never**
  silently promoted to APPROVED and **never** plotted on the main graph
  — they're kept in a separate file so a human can look at exactly the
  unresolved cases.
- **REJECTED** — the record failed a hard check (e.g. the source
  couldn't be verified, the numbers don't add up, it's out of scope for
  this assignment). Kept in the staging file for the audit trail, never
  used anywhere downstream.

## Student data-access policy

The tracked/reference/finalized datasets behind this workflow
(`countries/<country>/data/<country>_assignment1_approved.csv`,
`..._review.csv`, `..._reference_snapshot.csv`, and their local
gitignored counterparts under `data/processed/`) are **a student's own
assignment data** — learning/research artifacts, not secret data. A
student may:

- Ask for a summary, an aggregate answer, or a graph of their own
  results, exactly as before.
- Ask to see their own APPROVED results, including the underlying rows
  and columns.
- Ask to see their own REVIEW records and each record's real
  validation reason.
- Explicitly request their assignment CSV, or the internal file path it
  lives at, and be given it — there is no reason to withhold a
  student's own data from the student it belongs to.

Plain-language description ("validated Canada Assignment 1 data",
"Canada Assignment 1 REVIEW records") is still a perfectly good default
answer when the student hasn't asked for the file itself — it's simply
no longer the *only* allowed answer. Naming the file, handing over its
path, or providing the raw rows on request is equally correct.

**What stays protected — unchanged by this policy:**

- The production/master Pollitik workbook
  (`data/master/pollitik_master.xlsx`). Students must not read it as a
  substitute for their own assignment data, and must never write to it
  directly — the only approved writer remains
  `python/apply_changes.py`, enforced deterministically by
  `.claude/hooks/pollitik_guard.py` (see "What you should never do by
  hand" below). This policy governs a student's own assignment output,
  never the production workbook.
- Another student's or another country's assignment data — this policy
  is scoped to a student's own country assignment.
- The full staging audit trail (`data/staging/candidates.jsonl`) and
  research/validation logs — answer from the resolved APPROVED/REVIEW
  dataset (see "Deterministic result routing" in the country
  `AGENTS.md`), not by dumping the staging file's internal pipeline
  detail.

## History: prior response-only restriction (reversed 2026-08-25)

An earlier version of this policy instructed Codex to refuse a
student's own row-level data, file path, or CSV export "with no
explicit-ask exception," even for their own assignment. That
restriction has been reversed: it protected data that was never
actually secret in the first place, while never functioning as a real
access boundary either — the tracked assignment CSVs are plaintext
files already sitting in the student's own working tree, directly
readable with an ordinary editor, `cat`, or the `Read` tool regardless
of what Codex says (see `tests/test_student_data_access_boundary.py`,
which documents this as expected, intended behavior now, not a gap to
close). The production-workbook and web-fetch-domain protections
described above were never part of that restriction and remain exactly
as strict as before.

## What you should never do by hand

- **Never edit `data/master/pollitik_master.xlsx` directly**, and never
  ask Codex to edit it directly. The only path into it is
  `python/apply_changes.py`, run against a record that is already
  staged and re-validated as APPROVED. A hook
  (`.claude/hooks/pollitik_guard.py`) blocks every other route to that
  file — this isn't just a request, it's enforced.
- **Never hand-edit `data/staging/candidates.jsonl`** to change a
  status. If a REVIEW record should become APPROVED, that's a human
  decision made explicitly (and logged), not a find-and-replace.
- **Never manually configure a chart's axes, colors, legend, or
  formatting.** `python/generate_visualization.py` applies Pollitik
  styling automatically once you pick a graph type from its
  recommendations.
- **Never guess which APPROVED/REVIEW file to read for a country.**
  `python/resolve_assignment_dataset.py` decides deterministically
  (local run vs. tracked worked-example snapshot); the reference
  snapshot is never an acceptable substitute either way.

## Where this pipeline is documented in full

This page is the short version. The full rules live in
`.claude/skills/pollitik-executive-support/SKILL.md` (canonical) and the
country-specific Skill under `.claude/skills/<country>-pm-approval/`.
You generally don't need to read those yourself — Codex reads them as
part of following `AGENTS.md` — but they're the ground truth if
something here seems to disagree with what actually happens.
