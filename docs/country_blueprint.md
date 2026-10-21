# Country blueprint

Canada (`countries/canada/`) is the worked example. This page is what to
copy — and, just as importantly, what *not* to copy — when adding
another country.

## Structure to copy per country

```
countries/<country>/
  AGENTS.md            # narrows the root AGENTS.md to this country
  README.md             # worked-example overview: scope, in/out of
                         # scope data, where outputs live, how to run it
  prompts/
    run_assignment.txt
    continue_research.txt
    review_results.txt
    recommend_graphs.txt
    generate_graph.txt
  data/
    README.md                          # placeholder - points at the real data/ paths
    <country>_reference_snapshot.csv   # tracked - see below
    <country>_assignment1_approved.csv # tracked - see below
    <country>_assignment1_review.csv   # tracked - see below
  output/
    README.md           # placeholder - points at the real data/processed/ paths
```

Generate this skeleton automatically with
`python python/init_country_workspace.py --country <Name>` (see the
"Creating a new country workspace" rule in the root `AGENTS.md`) — it
creates exactly the file list above with generic, templated content and
refuses to overwrite an existing `countries/<country>/` folder. It never
copies the Canada blueprint's actual data, series, pollsters, sources,
executive name, reference profile, Skill, or results — only the
country-specific content described below (reference snapshot, tracked
Assignment-1 results, the Skill, the reference profile, and the scope in
`AGENTS.md`) still needs to be filled in by hand, from real research,
after the skeleton exists.

## What is country-specific

- **`countries/<country>/data/<country>_reference_snapshot.csv`** — a
  small, tracked, read-only export of that country's *existing*
  reference observations from the master workbook, containing only
  these 8 columns: `Series, Date, Total Count, Positive, Neutral,
  Negative, Source, Country`, filtered to that one country. This is
  what lets a fresh student workspace build a real local reference
  index (`python/build_reference_index.py --workbook
  countries/<country>/data/<country>_reference_snapshot.csv --index
  data/reference_index.duckdb`) and pass the preflight check
  (`python/check_assignment_preflight.py`) without ever needing the
  production master workbook, a committed `reference_index.duckdb`, or
  manual DuckDB knowledge. Generate it the same read-only way
  `countries/canada/data/canada_reference_snapshot.csv` was generated
  — export straight from the master workbook's Master sheet, never from
  a processed/working copy, and never including REVIEW/REJECTED staging
  records. Re-export only when that country's approved reference data
  materially changes; a student workspace never regenerates it itself.
  **Not** Assignment-1 output — never a substitute for the two files
  below when answering a validated-data or REVIEW question.
- **`countries/<country>/data/<country>_assignment1_approved.csv`** and
  **`<country>_assignment1_review.csv`** — small, tracked, frozen copies
  of that country's *finalized* assignment results, so a fresh clone can
  demonstrate the full student workflow (validated questions, REVIEW
  awareness, graph recommendation/generation) without a research run
  happening first. `<country>_assignment1_approved.csv` uses exactly the
  schema `python/generate_visualization.py` requires (`Date, Approval,
  <executive title>, Party, Series, Source, Status`); `..._review.csv`
  is the same shape plus one column, `Validation Reason`, carrying each
  record's real validation issue. Build both with
  `python/build_country_assignment_snapshot.py --country <Country>`
  against that country's real local pipeline outputs — never
  hand-transcribed — and re-run it (by the project owner) only when the
  finalized results materially change. A fresher local result in
  `data/processed/<country>_pm_approval_main.csv` / `..._review.csv`
  always takes precedence over these tracked files at runtime — see
  `python/resolve_assignment_dataset.py` below, the single deterministic
  decider that must never be second-guessed by model inference.
- **`countries/<country>/AGENTS.md`** — assignment scope (which office,
  which series are eligible/excluded), any country-specific research
  guidance (preferred pollsters, known data gaps).
- **A reference profile**, analogous to
  `.claude/skills/pollitik-executive-support/references/canada.md` —
  the known series for that country, their inferred target
  (PM/GOV/etc.), and confidence cautions. Build this from the existing
  workbook/index (`python/reference_lookup.py --country <Country>`),
  never from general knowledge.
- **A country Skill**, analogous to
  `.claude/skills/canada-pm-approval/SKILL.md` — narrows the canonical
  Skill to this country's office and exclusions. Add it under
  `.claude/skills/<country>-<office>-approval/`.
- **Approved/relevant sources** — which entries in
  `config/allowed_domains.txt` are this country's pollsters. The
  allow-list itself is shared (one file, all countries), but which
  domains matter for a given assignment is country-specific — say so in
  that country's `AGENTS.md`.
- **Assignment scope** — which office, which support-measure types
  (approval/favorability/etc.) are in scope for this specific
  assignment, stated in `countries/<country>/AGENTS.md`.
- **Country output files** — `data/processed/<country>_<office>_main.csv`
  and `..._review.csv`, following the naming pattern
  `canada_pm_approval_main.csv` / `canada_pm_approval_review.csv`
  already established.

## What stays shared — never duplicate into a country folder

- The preflight gate (`python/check_assignment_preflight.py`) and the
  reference-index tooling (`python/build_reference_index.py`,
  `python/reference_lookup.py`) — country-agnostic; a country's
  reference-snapshot CSV is just one of the inputs `build_reference_index.py`
  accepts, the same way a country's CSV is just an input to the
  visualization generator below.
- The deterministic result-precedence resolver
  (`python/resolve_assignment_dataset.py`) — takes `--country` and
  `--purpose` as parameters; it computes both candidate paths (local run
  vs. tracked snapshot) from the country slug, so it never hardcodes
  Canada or any other country.
- The tracked-snapshot builder (`python/build_country_assignment_snapshot.py`)
  — a maintainer/build-time tool, also parameterized by `--country`;
  never a per-country script.
- The canonical Skill (`.claude/skills/pollitik-executive-support/SKILL.md`)
- The seven pipeline agents (`.claude/agents/*.md`)
- The validator (`python/validate_record.py`, `python/stage_changes.py`)
- The matcher (agent logic — country context comes from that country's
  Skill/reference profile, not a per-country matcher copy)
- The production writer (`python/apply_changes.py` — the only approved
  writer, for every country)
- Visualization rules and generator
  (`config/visualization_rules.yaml`, `python/generate_visualization.py`)
  — country-agnostic by design; a country's CSV is just its input
- The test suite (`tests/`) — add country-specific fixtures/tests
  there, not a parallel test setup per country

If you find yourself about to copy a `.py` file, a Skill, or an agent
definition into a country folder, stop — that logic belongs in the
shared location above, parameterized by country/series/domain, not
forked per country. A country folder should contain only what genuinely
differs: scope, reference data, and prompts.
