# AGENTS.md — India PM approval assignment

Narrows the root `AGENTS.md` and `CLAUDE.md` to this one country
assignment, the same way every other country's `AGENTS.md` narrows
them.

This structure follows the Canada blueprint (see
`docs/country_blueprint.md`) - the completed, worked-example country
assignment used as the template for every new country. No data, series,
pollsters, sources, executive name, reference profile, or results from
the Canada blueprint are copied into this file or anywhere else in this
workspace. Everything below must come from real India research.

## Scope

India's **Prime Minister** as an individual office-holder. Include
general job/performance approval only. Exclude government-as-a-whole
approval, favorability, vote intention, preferred-leader measures,
issue-specific questions, trust, and confidence.

Once resolved, state the scope here in the same shape the Canada
blueprint's own country `AGENTS.md` uses (a short "Scope" section) -
see `docs/country_blueprint.md` for the pattern.

## Reference and source rules

Read `.claude/skills/pollitik-executive-support/references/india.md`
and `.claude/skills/india-pm-approval/SKILL.md` before research. Use
the India snapshot through `python/reference_lookup.py --country India`
for duplicate checks, and only fetch domains in `config/allowed_domains.txt`.

## Assignment-1 outputs

No tracked worked-example results exist yet for India
(`india_assignment1_approved.csv` / `..._review.csv`). These files
are only ever produced by `python/build_country_assignment_snapshot.py`
from a real, completed local research/staging run for India -
never hand-written, never copied from the Canada blueprint's results.

## Student data-access policy

Same policy as every other country (see `docs/student_workflow.md`,
"Student data-access policy"): a student's own India assignment
data - their APPROVED results, REVIEW results and validation reasons,
and the underlying rows - is learning material, not secret data. It may
be shown, explained, or provided to the student on request once real
data exists. Only the production/master Pollitik workbook, and other
students'/countries' data, stay protected.

## Where to go next

- `docs/country_blueprint.md` - the full structure this workspace
  follows and what's shared vs. country-specific.
- `docs/student_workflow.md` - the pipeline this assignment will run
  once the SETUP REQUIRED items above are resolved.
- `countries/india/prompts/run_assignment.txt` - the same
  short-prompt pattern every country uses, already updated for
  India.
