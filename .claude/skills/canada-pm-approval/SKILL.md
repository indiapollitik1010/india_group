---
name: canada-pm-approval
description: Collect and validate survey-based general public-support data for Canadian Prime Ministers in the Pollitik Database. A country-specific extension of the pollitik-executive-support Skill — narrows and directs that Skill's canonical rules to Canada PM research; does not restate or override them. Use for any task researching, matching, validating, or staging Canadian PM job approval, satisfaction, favorability, or image polling data.
---

# Canada PM Approval — Assignment 1

## Scope and relationship to the canonical Skill

This Skill extends `pollitik-executive-support`. It adds nothing that
contradicts the canonical Skill and duplicates none of its rules —
every rule in `.claude/skills/pollitik-executive-support/SKILL.md`
(sections 1-47) applies here in full and unmodified.

Before doing any Canada PM work:

1. Load and follow the canonical Skill:
   `.claude/skills/pollitik-executive-support/SKILL.md` (invoke via
   `/pollitik-executive-support` or the Skill tool).
2. Read the Canada reference profile:
   `.claude/skills/pollitik-executive-support/references/canada.md`.
   It documents the 30 existing Canada series, their inferred targets
   (PM vs. GOV vs. FAV vs. IMPRESSION), and explicit cautions about how
   confident each inference is.
3. Read `config/country_rules.yaml` for any Canada-specific exception
   entries (`trust_allowed`, `confidence_allowed`,
   `country_suffix_mappings`, `special_series_exceptions`). As of this
   writing every list in that file is empty for Canada — no exceptions
   are granted, so the canonical Skill's default rules apply
   unmodified: trust/confidence remain excluded, vote-intention remains
   excluded, and the workbook's Country field is the plain string
   `Canada` (per canada.md), not a `Country_PM`/`Country_GOV` split. If
   this file is later updated with a real Canada entry, that entry
   governs over the defaults described here.

## What this Skill covers

General survey-based public support for the Canadian Prime Minister as
an individual office-holder — series that target the PM specifically,
not the Government as a whole.

Eligible (canonical Skill section 2, applied to the PM):

- job approval / disapproval
- job satisfaction / dissatisfaction
- overall performance
- favorable / unfavorable opinion
- positive / negative image or "impression"
- general approval / general satisfaction / sympathy

Not eligible unless `config/country_rules.yaml` grants a Canada
exception (none currently exists):

- trust in the PM
- confidence in the PM

## Explicit exclusions for this task

Per canonical Skill sections 3, 25, 43, 44:

- **Government approval is excluded** when the research target is the
  individual PM. `GOV`-suffixed series in canada.md (e.g. `DecimaGOV`,
  `EnvironicsGOV`, `ANGUSREIDGOV`) measure the Government, not the PM —
  do not record new observations against them for a PM-approval task,
  and do not treat them as continuity for a PM series.
- **Issue-specific approval is excluded** (economy, immigration,
  healthcare, etc.) even when the question is about the PM
  specifically.
- **Vote-intention / preferred-PM / "if an election were held" /
  head-to-head preferred-leader questions are excluded**, unless the
  canonical Skill's SUN-prefix exception (section 43) is explicitly
  authorized by the user for this specific task. This Skill does not
  grant that authorization itself.
- **Continuous 1-10 / 1-100 grading scales are excluded** unless the
  canonical Skill's narrow exception (section 44) is explicitly
  authorized by the user.

## Workflow

Use the existing seven Pollitik subagents. Do not create Canada-specific
copies of any subagent — the Canada context comes from this Skill and
from canada.md, not from a specialized agent.

1. **reference-analyst** — always first. Query existing Canada series
   (via the DuckDB index) for the specific PM, date range, and/or
   pollster in scope, and cross-check against canada.md's series table
   before any web research begins. This determines which existing
   series a new observation is likely to extend.
2. **researcher** — discover and retrieve (via WebFetch or another
   approved deterministic mechanism) candidate sources for verified
   survey-based general PM support in Canada. Only approved-domain,
   actually-retrieved sources count as provenance (canonical Skill
   sections 5-8).
3. **multilingual-extractor** — if the retrieved source is in French or
   any non-English language, extract structured values while
   preserving original wording (canonical Skill section 9). Skip for
   English-only sources.
4. **matcher** — match the extracted candidate to an existing Canada
   series from canada.md using question wording, pollster, and target
   (PM vs. GOV) as primary evidence (canonical Skill sections 10-11).
   canada.md itself notes that plain-name series (`ANGUSREID`, `IPSOS`,
   `LEGER`, `NANOS`, etc.) do not encode PM-vs-GOV target from the name
   alone — the matcher must rely on question wording and source
   context in those cases, not the series name.
5. **validator** — run deterministic validation (provenance, arithmetic,
   required fields) and stage the candidate. Staging is required before
   any write is even considered; do not skip it.

## Series-matching guidance specific to Canada

- Prefer matching to an existing series in canada.md's table over
  proposing a new one, whenever pollster, wording, and PM-target are
  consistent with that series's established pattern.
- Route the following to REVIEW rather than automatic approval, per
  canada.md's own confidence cautions: single-record series (`CultMTL`,
  `GALLUPWORLD_LDR`, `INSIGHTSWESTPM`); any plain-name series where
  PM-vs-GOV target cannot be confirmed from the new source's own
  wording; and the multi-country program series (`GALLUPWORLD_LDR`,
  `GALLUPWORLD_LSHP`, `LAPOP`) where Canada-specific question wording
  isn't independently verifiable from the program alone.
- A genuinely new series (no plausible match anywhere in canada.md)
  requires `SERIES_REVIEW_REQUIRED` per canonical Skill section 11 —
  never auto-approve a new Canada series.

## Required fields

Use the same structured candidate observation as canonical Skill
section 30, with `country = "Canada"` and `executive_type` = Prime
Minister. Do not invent a `Country_PM`/`Country_GOV` split for Canada —
canada.md confirms the workbook uses a single plain `Canada` country
value; PM vs. Government is distinguished only by series name.

Preserve exactly as found, never invented (canonical Skill sections 34,
37, 42):

- exact question wording
- source URL (only from actual retrieval, never model-generated)
- fieldwork dates
- sample size
- positive / neutral / negative values and their component categories
- full provenance (retrieval metadata, domain, language, evidence text)

## Ambiguity always routes to REVIEW

Never automatic approval for (canonical Skill sections 11, 34, 36):

- any new or ambiguous series not clearly matched in canada.md
- any plain-name series where PM-vs-Government target is uncertain
- any conflict with an existing non-empty workbook value

## Write policy

Unchanged from canonical Skill section 35: research agents (including
reference-analyst, researcher, multilingual-extractor, matcher,
validator) never write to the production workbook. Only `excel-writer`,
invoked explicitly by the user after the validator has staged an
APPROVED record via `python/apply_changes.py`, may write. This Skill
does not request or perform that write on its own — it only produces
staged, validated candidates.

## Token efficiency

Keep reference-analyst and matcher outputs scoped to the specific
series/date range/pollster in question — do not repeatedly dump the
full canada.md table or full workbook contents into agent context.
Summarize findings in the final report per canonical Skill section 41.
