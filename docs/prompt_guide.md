# Prompt guide

Short prompts, on purpose. Codex already reads `AGENTS.md`, the Skills
under `.claude/skills/`, the country folder, and `config/` — repeating
those rules in your prompt wastes tokens and adds nothing Codex doesn't
already have. Tell it *what to do next*, not *how the pipeline works*.

## Recommended prompts

These are intentionally minimal. Copy one, or use the matching file
under `countries/<country>/prompts/`.

- **"Run the Canada Prime Minister approval assignment."**
  Starts (or resumes) the full pipeline for Canada from wherever it
  left off. This always runs the dependency check
  (`python/check_python_dependencies.py`) first — see
  `countries/canada/prompts/run_assignment.txt`. On an environment that
  has never had `requirements.txt` installed, it reports
  `dependencies_ready=false`; Codex stops before preflight and tells you
  to run `pip install -r requirements.txt` once (never installs packages
  itself). Once dependencies are ready, it runs the preflight check
  (`python/check_assignment_preflight.py --country Canada`) next. On a
  fresh clone with no local reference index yet, preflight reports
  `COUNTRY_SNAPSHOT_BUILDABLE`; Codex builds the local index
  automatically from the tracked `canada_reference_snapshot.csv` (no
  master workbook, no manual DuckDB command, nothing for you to type)
  and re-checks before continuing. If it still reports
  `SAFE_TO_RESEARCH=false` for any other reason, Codex stops and
  reports why instead of starting research; it never fetches the web or
  stages anything in that state.
- **"Continue the next Canada source batch."**
  Resumes research at the next unresolved batch instead of restarting
  from scratch.
- **"Give me a summary of Mark Carney's approval trend, and tell me
  which polling firms are included."** / **"What was the highest and
  lowest validated approval rating, and which pollster/date reported
  each?"**
  Answered directly from the resolved APPROVED dataset
  (`python/resolve_assignment_dataset.py --purpose approved` — the
  tracked worked-example snapshot in a fresh clone, or a fresher local
  result if this workspace has actually done research). A plain-language
  description ("validated Canada Assignment 1 data") is fine by
  default, and so is naming the actual file/path or handing over the
  underlying rows if the student asks for either — it's their own
  assignment data; see `docs/student_workflow.md` "Student data-access
  policy" for what's protected instead (the production workbook, and
  other students'/countries' data).
- **"Show me the remaining REVIEW cases."** / **"Are there any results I
  should be careful about?"**
  Summarizes the current REVIEW-status records (resolved dataset,
  `--purpose review`) as "Canada Assignment 1 REVIEW records" in plain
  language, preserving each record's real validation reason — same
  no-internal-path rule as above. Never treats REVIEW as validated,
  never mixes in REJECTED unless you explicitly ask for it.
- **"Recommend graphs for my approved results."** / **"I'm not sure
  which graph I should use for the Canada Prime Minister approval
  results. What are my best options and why?"**
  The "student unsure" workflow: runs the graph-recommendation step
  against the resolved APPROVED dataset, ranks up to 3 eligible chart
  types, and presents them as a numbered, human-readable list (display
  name + one-line reason each — never an internal graph type id), saving
  the ranked list locally so a follow-up reply resolves deterministically.
  You can then reply with a number, the graph's name, a natural
  description ("make the trend graph"), or "all three".
  **Generates nothing yet** — recommend and stop.
- **"Generate a graph showing Mark Carney's validated approval over
  time."**
  The "student knows what they want" workflow: an unambiguous request
  names (or clearly implies) one eligible graph type, so Codex maps it
  straight to `--graph approval_over_time` and generates it directly —
  it does **not** force the recommend-first step when the choice is
  already clear from the request.
- **"Generate a graph option 1."** / **"Approval Over Time."** /
  **"Make the trend graph."** / **"Latest pollster comparison."**
  Resolves your reply (option number, display name, or an unambiguous
  natural description) from the saved recommendation state — never by
  re-reading the earlier reply from memory, and never by guessing a
  reply that could mean more than one type — and generates that graph,
  fully styled, against the same resolved dataset. No internal graph
  type id required.
- **"All three."**
  Generates every eligible graph from the saved recommendation list
  (for the current Canada assignment: Approval Over Time, Series
  Spread, and Snapshot Comparison), each fully styled against the same
  resolved dataset.
- **"Generate a graph of the Canada results."**
  Too vague to map to one graph type on its own (it doesn't say time
  trend, pollster comparison, or a snapshot) — Codex shows ranked
  recommendations instead of guessing which one was meant, same as the
  "student unsure" case above.
- **"Explain this graph to me in simple words."**
  Grounded in the graph that was actually generated: the generator's own
  summary/report, the chart's `<meta>`/legend/footer, and
  `config/visualization_rules.yaml`'s design rules for that graph type —
  never generic chart-reading assumptions.

## What NOT to do

Don't paste the Skill text, the country rules, the approved-domain list,
or the visualization rules into your prompt. Codex reads
`AGENTS.md` -> Skills -> country docs -> `config/` on its own. A prompt
that re-explains those rules is strictly more tokens for the same
result — worse, a paraphrased rule can drift from the real one in
`config/` or the Skill file and quietly become the wrong rule.

## When you SHOULD give more detail

A short prompt works because the default path is already fully
specified. Give Codex more context when you're doing something the
default path doesn't cover:

- **The assignment scope is changing** (e.g. "also include favorability
  polls, not just job approval" — state the change explicitly, since
  the default scope is job-approval-only per
  `countries/canada/AGENTS.md`).
- **You're starting a new country assignment.** Say so plainly — "Set
  up my country assignment for Australia," "Create my Australia country
  workspace" — and Codex runs `python/student_workspace_setup.py
  --country Australia --steps workspace` (a thin, dependency-free
  wrapper around `python/init_country_workspace.py`) to generate the
  skeleton, then stops so you (or your professor) can fill in the
  country-specific parts. Ask for the reference/EAD data too ("...and
  generate its reference and EAD data") and Codex runs all three steps
  in one call — still no `pip install` needed either way. This is a
  separate step from asking a question about a country that doesn't have
  a workspace yet (e.g. "What do we know about polling in Australia?")
  — a question never creates files on its own. See
  `docs/country_blueprint.md` for what the generated skeleton contains.
- **A source is blocked or inaccessible** — say which domain/URL and
  what happened, so Codex doesn't retry the same blocked fetch
  repeatedly.
- **Your professor gives a rule specific to your section** that isn't
  in the repo yet (e.g. a different cutoff date, an extra exclusion) —
  state it plainly so it can be applied and, ideally, recorded rather
  than re-explained every session.
- **A REVIEW case needs a human decision** — e.g. "treat the LIAISON
  record with the missing sample size as intentionally blank, don't
  infer one." That's exactly the kind of judgment call REVIEW exists
  for; state your decision and the reasoning behind it.

## Token-efficiency rules this repo already follows

Worth knowing so you understand why short prompts are enough, not just
that they are:

- Read existing repo instructions instead of repeating them in prompts.
- Reuse reference-analysis findings (`python/reference_lookup.py`
  against the derived DuckDB index) instead of re-querying the whole
  workbook.
- One researcher pass per source/domain batch, not one call per
  observation.
- Fetch each relevant source once and reuse the cached evidence
  (`python/source_cache.py`) — never re-fetch a URL already retrieved.
- Batch candidates to the matcher, and batch candidates to the
  validator (`python/validate_record.py`/`python/stage_changes.py` both
  take batch input).
- Never launch one agent per individual observation.
- Stop retrying a domain that's clearly blocked or unreachable — report
  it instead of looping.
- Use deterministic scripts (`python/*.py`) for anything that doesn't
  require judgment — arithmetic, duplicate detection, date
  normalization, staging — rather than re-deriving it with the model
  each time.
