# AGENTS.md — repository map

This file is a map, not a manual. It exists so a student working with
Codex (or any other agent) in this repo does not need to re-explain the
project's rules in every prompt — the rules already live here, in
`CLAUDE.md`, and in `.claude/skills/`. Read those, don't restate them.

## Ground rules

- **Classroom setup (create workspace / generate reference snapshot /
  generate EAD snapshot) needs no `pip install` at all - never gate it
  on the dependency check.** For a prompt that clearly means one or more
  of: "create my country workspace," "generate the country reference
  snapshot," "generate the country EAD series/question-wording file" —
  run `python python/student_workspace_setup.py --country <Country>`
  (add `--steps workspace`, `--steps reference`, or `--steps ead`, or
  any comma-separated subset, to do just one). This script imports only
  the Python standard library plus the two tracked shared CSVs
  (`data/reference/pollitik_reference.csv`,
  `data/reference/ead_series_question_wording.csv`) - a fresh clone
  always has both, since neither is git-ignored. It never touches
  `duckdb`, `pandas`, `PyYAML`, or `openpyxl`, and it is safe to re-run
  (an already-existing workspace or snapshot is reported as skipped, not
  an error). **Do not run `python/check_python_dependencies.py` first
  for this - these three tasks don't need anything it checks for.** See
  `docs/student_workflow.md` and `docs/country_blueprint.md`.
- **Check Python dependencies before preflight, before any research.**
  This applies to the RESEARCH pipeline only (preflight, reference-index
  build, web fetch, matching, validation/staging) - never to the
  classroom-setup tasks above. Run `python
  python/check_python_dependencies.py` first. It never installs
  anything - it only reports whether the third-party packages the
  research pipeline needs (`duckdb`, `pandas`, `openpyxl`, `PyYAML` -
  all already declared in `requirements.txt`) are importable in the
  current interpreter. If it reports `dependencies_ready=false`,
  **STOP** before preflight and before any research or staging - this is
  an environment/setup problem, never a data problem, so it must never
  produce a NOT_FOUND/REVIEW/REJECTED record. Tell the student to run
  `pip install -r requirements.txt` once, from the repo root, then
  retry; never install packages automatically or one-by-one. This
  exists because a fresh Codex sandbox can have the repo code, AGENTS.md,
  and a country's tracked snapshot all correctly discovered while the
  Python environment running them has never had `requirements.txt`
  installed - the prior symptom was a raw `ModuleNotFoundError` surfacing
  deep inside the reference-index build instead of one clear setup step
  up front.
- **Run the preflight check before any research.** Before starting or
  resuming a country assignment, run
  `python python/check_assignment_preflight.py --country <Country>`.
  If it reports `SAFE_TO_RESEARCH=false`, **STOP** — explain why (its
  `reason`/`unsafe_reasons` field says exactly what's missing) and do
  not fetch the web or stage anything until it's resolved. This exists
  because a fresh workspace (e.g. a new Codex sandbox) can contain the
  repo code and a country's `AGENTS.md` without containing
  `data/reference_index.duckdb`, `data/master/pollitik_master.xlsx`, or
  any local staging history — and without this check, research could
  start with no real duplicate/reference check behind it. Each country
  ships a small tracked reference-snapshot CSV
  (`countries/<country>/data/<country>_reference_snapshot.csv`) so a
  fresh workspace can build a real local index without the production
  workbook — see "New required workflow" below. An empty or missing
  `data/staging/candidates.jsonl` is never itself evidence that the
  workspace is safe, or that an observation is new.
- **This repository is the source of truth.** If a prompt, a memory, or
  a prior answer conflicts with what's actually in this repo (Skills,
  config, code), the repo wins.
- **Read the country-specific `AGENTS.md` before doing country work**
  (e.g. `countries/canada/AGENTS.md`). It narrows these repo-wide rules
  to one country's assignment; it does not replace them.
- **Use the existing Pollitik Skills/agents/scripts — do not recreate
  their rules from memory or general knowledge.** Canonical policy:
  `.claude/skills/pollitik-executive-support/SKILL.md`. Country
  extensions: `.claude/skills/<country>-pm-approval/SKILL.md`. Pipeline
  roles: `.claude/agents/*.md` (researcher, multilingual-extractor,
  reference-analyst, matcher, validator, excel-writer, r-analyst).
  Deterministic logic: `python/*.py`.
- **Approved domains only.** Every web fetch must resolve to a domain
  listed in `config/allowed_domains.txt`. No exceptions, no mirrors, no
  proxies.
- **Use the existing researcher/agent web-fetch mechanism ("WebFetcher")
  for all web research.** Do not introduce a new scraping tool, library,
  or framework. See "Web fetch" in `docs/student_workflow.md`.
- **Batch source research where possible.** One researcher pass per
  source/domain batch, not one agent invocation per observation. See
  `docs/prompt_guide.md` for the token-efficiency rules this implies.
- **Never guess a missing value.** No invented PM name, party, date,
  approval number, or source. If it isn't in the retrieved evidence, it
  stays blank or the record goes to REVIEW.
- **Route ambiguity to REVIEW, not to a guess.** Uncertain series match,
  uncertain wording, uncertain sample size — REVIEW, never silently
  APPROVED.
- **Never write to the production master workbook without explicit
  instruction.** The only approved writer is `python/apply_changes.py`,
  invoked only after a record is staged and re-validated as APPROVED
  (`.claude/hooks/pollitik_guard.py` enforces this deterministically —
  it is not just a prompt convention).
- **Use the repo-resident visualization recommendation rules** for any
  chart — `config/visualization_rules.yaml` +
  `python/generate_visualization.py`. Recommend top options, let the
  student choose, generate automatically. Never hand-configure axes,
  colors, or legends. See `docs/visualization_rules.md`.

## Creating a new country workspace

A student may ask Codex to set up a brand-new country assignment (e.g.
"Set up my country assignment for Australia," "Create my Australia
country workspace," "I was assigned Australia — set it up using the
Canada blueprint"). When a prompt clearly expresses that CREATE/SETUP
intent, run:

    python python/student_workspace_setup.py --country <Name> --steps workspace

(equivalent to, and a thin wrapper around,
`python python/init_country_workspace.py --country <Name>` — see
"Classroom setup" above; needs no `pip install`) then **stop** and
report the setup state it returns (which files were created, and what's
still `SETUP REQUIRED` — reference profile, Skill, reference data,
approved sources). Do not continue into research, preflight, or
anything else in the same turn — creating a workspace and running the
research assignment are two separate actions. If the prompt also asks
for the reference snapshot and/or EAD snapshot in the same breath (e.g.
"create my Belgium workspace and generate its reference data"), drop
`--steps workspace` and let it run all three steps in one call instead.

**Folder non-existence alone is never sufficient evidence of creation
intent.** A question like "What do we know about polling in Australia?"
or "Does this repo cover Australia yet?" must be answered as a question
— by checking whether `countries/australia/` exists and saying so — and
must never itself trigger file creation. Only run
`python/init_country_workspace.py` when the student's own words ask for
the workspace/assignment to be created or set up.

If `countries/<slug>/` already exists, the script refuses to overwrite
it and reports why — relay that back to the student rather than
retrying or working around it.

See `docs/country_blueprint.md` for what the generated skeleton
contains and what still requires real country-specific research before
any research/staging can begin.

## New required workflow

```
student assignment prompt
  -> dependency check        (python/check_python_dependencies.py)
  -> dependencies_ready == false? -> STOP, tell the student to run
       `pip install -r requirements.txt` once, then retry. Never
       install packages automatically; never treat this as a data
       problem (no NOT_FOUND/REVIEW/REJECTED record from it).
  -> preflight              (python/check_assignment_preflight.py --country <Country>)
  -> reference_data_status == REFERENCE_INDEX_PRESENT?  -> continue
  -> reference_data_status == COUNTRY_SNAPSHOT_BUILDABLE?
       -> build the local index from the tracked country CSV snapshot
          (python/build_reference_index.py --workbook
          countries/<country>/data/<country>_reference_snapshot.csv
          --index data/reference_index.duckdb)
       -> re-run preflight; continue only if it now reports
          SAFE_TO_RESEARCH=true
  -> otherwise (SAFE_TO_RESEARCH=false): STOP and explain why
  -> only once SAFE_TO_RESEARCH=true: inspect existing reference state,
     then research approved domains, then match/validate/stage
```

The preflight step itself is read-only and has no side effects — it
never fetches the web, stages a candidate, or builds/creates any
missing file (including the reference index); it only reports what
exists and computes `SAFE_TO_RESEARCH`. Building the local index from a
tracked snapshot is the one narrow, explicit exception a workflow may
take automatically before re-checking: it never touches
`data/master/pollitik_master.xlsx`, never fetches the web, and the
snapshot's mere presence is never itself treated as
`SAFE_TO_RESEARCH=true` — only a freshly-rebuilt, re-verified index is.
A student should never need to type the build command by hand; the
assignment prompt runs it automatically (see
`countries/canada/prompts/run_assignment.txt`).

## Where to go next

- **`docs/student_workflow.md`** — the full assignment → output pipeline
  in plain language, including what APPROVED/REVIEW/REJECTED mean.
- **`docs/prompt_guide.md`** — the short prompts a student actually
  needs to type, and when more detail is genuinely required.
- **`docs/country_blueprint.md`** — how a new country's folder should be
  structured, and what's shared vs. country-specific.
- **`countries/<country>/`** — one folder per country's assignment
  (e.g. `countries/canada/`), each with its own `AGENTS.md`, `README.md`,
  and short reusable prompt files under `prompts/`.

## What lives where (unchanged by this map)

This map does not move or duplicate any real data. Production/staging
data stays exactly where the pipeline already puts it:

- `data/master/pollitik_master.xlsx` — production workbook (read-only
  except via `python/apply_changes.py`).
- `data/staging/candidates.jsonl` — every staged candidate, all
  statuses, full audit trail.
- `data/processed/` — visualization-ready CSV exports per country
  (e.g. `canada_pm_approval_main.csv`, `canada_pm_approval_review.csv`)
  and `data/processed/visualizations/` for generated charts.
- `config/allowed_domains.txt`, `config/country_rules.yaml`,
  `config/visualization_rules.yaml` — the approved-domain list,
  country-specific coding exceptions, and graph rules.

`countries/<country>/data/README.md` and `.../output/README.md` point
at these real locations rather than copying anything into the country
folder.
