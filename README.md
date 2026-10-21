# Pollitik Database

An academic research platform for collecting survey-based public support
data for political executives (presidents, prime ministers, chancellors,
and equivalent offices), built on Claude Code.

Start with `CLAUDE.md` and
`.claude/skills/pollitik-executive-support/SKILL.md` — that Skill is the
policy for every research/extraction/validation/staging/write task in
this project. The core rule it enforces: a source is never valid
provenance merely because a model wrote a plausible-looking URL; it must
actually be retrieved (WebFetch or another approved deterministic
mechanism), and academic validity always wins over filling more cells.

The Skill's conventions are grounded in the real **Executive Approval
Database (EAD) Data Collection Manual** (v.10/8/2020) — the actual
academic project ("Pollitik" is this repo's working name for the same
effort). Several rules (Country_Gov/Pres/PM suffixes, m/d/yyyy dates
with a 15th-of-month fallback, question-wording-determines-series,
trust/confidence excluded by default) match the manual's own
conventions directly; see Skill sections 43-47 for rules added once the
manual was available (vote-intention exclusion, continuous-scale
exclusion, sample-size inference, the `net`/`app_app_dis` computed
fields, multi-wave survey-program naming).

Remote/API access to this pipeline (a FastAPI job service using the
Claude Agent SDK) is documented separately in
`docs/REMOTE_DEPLOYMENT.md` — this README covers the pipeline itself,
which works identically whether driven interactively via Claude Code or
remotely via that service.

## Student Country Workflow

If you're a student working on a country assignment, start here.

The overall workflow:

1. Start from latest `main` and create/use the group branch.
2. Create the country workspace.
3. Generate the country reference snapshot.
4. Generate the country EAD series/question-wording CSV.
5. Inspect the existing country data and continue the assignment/research.
6. Commit and push work to the group branch.

- **Start from the latest `main`** and create/use the group branch
  assigned for your country — don't work directly on `main`.
- **You do not need the hidden `data/master/` Excel workbooks** for the
  classroom country-workspace workflow. Those are the private,
  production-only Master and EAD workbooks — they're git-ignored and not
  part of this repo. The classroom workflow runs entirely from the two
  tracked shared reference CSVs described next.
- **This repo ships two tracked shared reference files** covering every
  country already in the data:
  - `data/reference/pollitik_reference.csv`
  - `data/reference/ead_series_question_wording.csv`
- **Creating a country workspace, generating its reference snapshot, and
  generating its EAD series/question-wording CSV are one dependency-free
  command**, needing no `pip install` at all:
  ```
  python python/student_workspace_setup.py --country Belgium
  ```
  This wraps `python/init_country_workspace.py`,
  `python/build_country_reference_snapshot.py`, and
  `python/build_country_ead_snapshot.py` — it imports nothing beyond the
  Python standard library and reads only the two tracked shared CSVs
  above, so it works on a completely fresh clone with no
  `requirements.txt` install and no hidden Excel workbook. Pass `--steps
  workspace`, `--steps reference`, or `--steps ead` (or any
  comma-separated subset) to run just one of the three; it's safe to
  re-run — an already-existing workspace or snapshot is reported as
  skipped, not an error. For example, asking:
  > "Create the Pollitik workspace for Belgium."
  runs (or is understood as) just the `workspace` step: the standard
  `countries/belgium/` folder and scaffold (`AGENTS.md`, prompts, empty
  `data/`/`output/` folders) — it does not fetch or generate any data by
  itself. Asking to also generate the reference/EAD data runs the
  remaining steps, still without touching the hidden Excel workbooks.
- **This is a separate, earlier tool than the research pipeline.** The
  research pipeline itself (preflight, the DuckDB reference index, web
  fetch, matching, validation/staging) still needs
  `pip install -r requirements.txt` and `python
  python/check_python_dependencies.py` first, same as before — see
  "How the pieces fit together" below. Only the three classroom-setup
  steps above are dependency-free.
- **Country name aliases and canonical folder names are handled
  centrally**, so common spelling/case/hyphen variants (e.g. "UK",
  "USA", "South-Korea") resolve to the correct `countries/<slug>/`
  folder automatically. One exception: plain **"France"** is ambiguous
  and must be specified as **France President** or **France Prime
  Minister**.
- **Changes created by Codex are written to its local Git checkout/
  worktree first.** They do not automatically appear on GitHub —
  students must commit and push them to their group branch.

## How the pieces fit together

```
Internet
  -> researcher agent (source_cache.py lookup -> WebFetch, approved domains only -> source_cache.py store)
  -> multilingual-extractor agent (translation, structured extraction, all-eligible-values-in-one-pass)
  -> reference-analyst agent (reference_lookup.py - low-token DuckDB index query, not the raw workbook)
  -> matcher agent (Country / series / duplicate / conflict resolution)
  -> validator agent (python/validate_record.py + python/stage_changes.py)
  -> data/staging/candidates.jsonl
  -> excel-writer agent (python/apply_changes.py — the only writer)
  -> data/master/pollitik_master.xlsx
  -> r-analyst agent (R, once real approved data exists)
```

### Token efficiency

Token usage is treated as a first-class design constraint, never traded
against source verification or validation rigor:

- **No agent loads the full master workbook.** `reference-analyst` (and
  `matcher`/`r-analyst` when they need a quick lookup) query
  `python/reference_lookup.py`, which returns a handful of matching rows
  from a derived DuckDB index (`data/reference_index.duckdb`, built by
  `python/build_reference_index.py`) — Excel stays canonical, the index
  is just a fast, disposable, rebuildable read layer over it.
- **Sources are fetched once.** `python/source_cache.py` keeps a
  persistent, URL-keyed cache of already-verified retrievals (final URL,
  HTTP status, retrieval time, evidence text). The researcher agent
  checks it before every `WebFetch` call and stores a fresh result after
  — a cache hit is exactly as verifiable as the original fetch, because
  it *is* the original fetch's recorded output, not a shortcut around
  verification.
- **Model tiers match task difficulty.** `reference-analyst`, `validator`,
  and `excel-writer` (mostly "run a deterministic script and report its
  output" roles) run on `haiku`; `researcher`, `multilingual-extractor`,
  `matcher`, and `r-analyst` (genuine judgment calls — issue-specific vs.
  general classification, ambiguous translation, uncertain series
  matching) keep the session's default model. See each agent's `model:`
  frontmatter in `.claude/agents/`.
- **Deterministic code, not the LLM, does**: arithmetic, duplicate
  detection, URL/domain verification, workbook inspection, schema
  lookup, date normalization, staging, backups, Excel writes, and
  source-metadata storage. See `python/*.py` — none of it involves a
  model call.
- **Structured artifacts, not prose, flow between phases.** Every
  script above emits JSON; subagents pass record IDs, URLs, and cache
  hit/miss status to each other rather than re-describing content in
  conversation. The Pollitik Manager (`service/agent.py`) never
  reproduces a subagent's full output in its own context — it retains
  references and returns one concise structured job summary.
- **Cost/token observability**, when running via the remote service: per
  job, `GET /jobs/{id}` reports model, input/output tokens, total cost,
  number of model calls, number of subagent (Task) calls, source-fetch
  count, and cache hits/misses — the last three recomputed
  deterministically from `logs/research/cache_access.jsonl`, not trusted
  from the agent's own summary (same principle as the staging-count
  override described below).

### Key files

- **`.claude/skills/pollitik-executive-support/SKILL.md`** — the research
  policy (what counts as public support, source rules, series matching,
  response aggregation, statuses, etc.). Invoke directly with
  `/pollitik-executive-support`. This is the GLOBAL Skill; a
  country-specific Skill (e.g. `canada-pm-approval` below) extends it by
  reference and must never duplicate it (Skill section 53).
- **`.claude/skills/canada-pm-approval/SKILL.md`** and
  **`.claude/skills/pollitik-executive-support/references/canada.md`** —
  the first country-specific Skill in this project, added 2026-08-13.
  Loads the canonical Skill in full and adds only Canada-specific facts
  (existing series, PM-vs-Government distinctions, workbook conventions)
  — use it as the template for any future country-specific Skill.
- **`.claude/hooks/pollitik_guard.py`** — a `PreToolUse` hook that
  deterministically enforces the parts of the Skill that must never
  depend on the model "being careful": no WebFetch outside
  `config/allowed_domains.txt`, no shell-based networking used to route
  around that, and no write/delete/rename of the production workbook
  outside `python/apply_changes.py`.
- **`.claude/agents/`** — the seven pipeline roles (researcher,
  multilingual-extractor, reference-analyst, matcher, validator,
  excel-writer, r-analyst), each with tool access scoped to its stage so
  role boundaries are enforced by permissions, not just prompts.
- **`python/`** — the deterministic half of the pipeline: source
  verification, arithmetic, staging, read-only workbook inspection, the
  DuckDB reference index/lookup, the source-retrieval cache, and the one
  approved production writer. See each script's docstring.
- **`service/`** — a FastAPI job API exposing this pipeline remotely via
  the Claude Agent SDK. See `docs/REMOTE_DEPLOYMENT.md`.
- **`data/reference_index.duckdb`** — derived, rebuildable index over the
  master workbook (`python/build_reference_index.py`). Never authoritative
  — Excel remains canonical; delete and rerun the build script anytime.
- **`data/cache/sources.jsonl`** — persistent cache of verified source
  retrievals (`python/source_cache.py`), keyed by URL.
- **`python/check_domain.py`** — deterministic, no-network pre-fetch
  check: given a URL, reports `APPROVED` or `DOMAIN_APPROVAL_REQUIRED`.
  The researcher agent runs this before proposing a lead as usable, so
  an unapproved domain is flagged and a request for approval is raised
  (Skill sections 8, 49) instead of attempting a fetch the hook would
  deny anyway.
- **`config/allowed_domains.txt`** — WebFetch domain allow-list, and the
  single file `.claude/hooks/pollitik_guard.py` actually enforces. Only
  a small number of domains are approved so far; add more only after
  you've explicitly approved them, one at a time or as an explicit
  batch. See the domain-approval workflow below.
- **`config/candidate_domains.txt`** — discovery-tier domains, NOT
  enforced and NOT approved (381 entries as of 2026-08-13, preserved
  from a bulk workbook-derived batch that should never have been placed
  directly in the enforcement file — see that file's header for the
  full history). A domain here is a lead worth reviewing, not
  authorization to fetch; promotion to `config/allowed_domains.txt`
  still requires the project owner's explicit approval.
- **`config/domains/`** — documented, optional per-scope domain
  *metadata* (why an *already-approved* domain was approved, which
  country/pollster/program it belongs to) once there are enough
  approved domains for that to matter. Does not replace
  `config/allowed_domains.txt`; see `config/domains/README.md`.
- **`config/country_rules.yaml`** — documented, currently-empty
  structures for trust/confidence exceptions, Country suffix
  conventions, executive-title mappings, and special-series exceptions.
  Populate only from confirmed facts, never inference.
- **`config/schema_mapping.yaml`** — canonical semantic field names
  (Country, Executive, Series, Pollster, Positive, Negative, Sample_Size,
  Source, Notes, etc.), which internal candidate-record field each maps
  to, required/optional classification, and the one historical alias
  this project recognizes: a workbook column named "Total Count" is the
  same field as `Sample_Size`, never a second column
  (`python/apply_changes.py` reads this to resolve it).
- **`config/source_systems.yaml`** — documented, currently-empty
  registry for future approved databases/survey systems (national
  polling archives, academic repositories, etc.) the researcher may
  consult. Registering a system here is not itself a domain approval.
- **`config/source_validation_rules.yaml`** — documented, currently-empty
  placeholder for future source-authenticity/anti-fraud rules (fake or
  copied sites, impersonation domains, methodology transparency, etc.),
  to be populated once the project owner supplies that guidance. Not yet
  enforced.
- **`data/master/`** — the canonical, private location for the real
  Pollitik master workbook (`pollitik_master.xlsx` by default —
  `python/pollitik_common.py`'s `DEFAULT_MASTER_WORKBOOK` and
  `python/apply_changes.py`'s `DEFAULT_WORKBOOK` both point here; no
  other path is hard-coded anywhere in the pipeline). It's git-ignored
  and stays local to the production research pipeline — nothing in this
  repo invents one. **Students do not need it**: the classroom
  country-workspace workflow (see "Student Country Workflow" above)
  runs from the tracked shared reference CSVs in `data/reference/`
  instead.
- **`data/staging/candidates.jsonl`** — every candidate observation that
  has gone through validation, regardless of outcome (APPROVED, REVIEW,
  REJECTED, NOT_FOUND). This is the audit trail.
- **`data/archive/`** — timestamped workbook backups, made automatically
  before every production write.
- **`feedback/corrections.jsonl`** — where human corrections should be
  logged so future tasks can retrieve them as examples (Skill section 38
  — retrieval, not fine-tuning).
- **`logs/`** — validation and write logs.
- **`evals/`** — a place for a gold-standard evaluation set, once one
  exists, to measure Skill/pipeline accuracy objectively.

## What's intentionally not built yet

R scripts (`R/pipeline.R`, `R/visualize.R`, etc.) depend on real approved
data existing first — building them against synthetic placeholders would
just produce hollow code. Add them once `data/master/` holds the real
workbook and the pipeline above has processed at least a handful of real
records end to end.

The DuckDB reference index *tooling* (`python/build_reference_index.py`,
`python/reference_lookup.py`) is built and tested against synthetic
fixtures, unlike the R scripts above — but it has nothing to index until
a real workbook exists at `data/master/pollitik_master.xlsx`. Run
`python3 python/build_reference_index.py` once one is added.

Per-country document storage: the source EAD Data Collection Manual
(`docs/ead/EAD MANUAL.txt`) describes uploading source documents
(PDFs, screenshots, etc.) into a per-country "Country Files" repository
folder, with an accompanying "Institutional Knowledge" notes document
per country (the same concept Skill section 38 already anticipated).
Neither has an equivalent in this repo yet — there is no per-country
storage structure or notes-file convention. This is a documented future
feature, not implemented here; do not invent an ad hoc folder structure
for it before it's explicitly designed and approved.

## Setup

```
pip install -r requirements.txt
```

## Development workflow — definition of done

CI (`.github/workflows/ci.yml`) is the baseline gate. A development
change is not complete until all three of the following are true:

1. Local tests pass: `python3 -m pytest tests/ -v`
2. The secret/production-data scan passes on whatever would be
   committed (see `docs/REMOTE_DEPLOYMENT.md` and this project's
   pre-commit practice — never commit `.env`, credentials, or real
   Pollitik data; `.gitignore` encodes the specifics).
3. GitHub Actions CI passes on the pushed commit — check with
   `gh run list --limit 5` / `gh run view <run-id>`, not just assumed
   from local results. A workflow file can be valid YAML and still be
   rejected by GitHub's own Actions parser (e.g. an expression context
   that's only invalid at that specific location) - `actionlint` catches
   the class of error generic YAML/JSON validation can't; run it on
   `.github/workflows/*.yml` after editing them, in addition to the
   local checks above.
