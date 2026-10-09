---
name: australia-pm-approval
description: Collect and validate survey-based general public-support data for Australian Prime Ministers in the Pollitik Database. A country-specific extension of the pollitik-executive-support Skill — narrows and directs that Skill's canonical rules to Australia PM research; does not restate or override them. Use for any task researching, matching, validating, or staging Australian PM job approval, satisfaction, favorability, or image polling data.
---

# Australia PM Approval — Assignment 1

## Scope and relationship to the canonical Skill

This Skill extends `pollitik-executive-support`. It adds nothing that
contradicts the canonical Skill and duplicates none of its rules —
every rule in `.claude/skills/pollitik-executive-support/SKILL.md`
(sections 1-48) applies here in full and unmodified.

Before doing any Australia PM work:

1. Load and follow the canonical Skill:
   `.claude/skills/pollitik-executive-support/SKILL.md` (invoke via
   `/pollitik-executive-support` or the Skill tool).
2. Read the Australia reference profile:
   `.claude/skills/pollitik-executive-support/references/australia.md`.
   It documents the 16 existing raw Australia series (plus one EAD-only
   series, `NEWSPOLL/PYXIS`), their scope classification (in scope /
   out of scope / requires verification), and the Prime Minister
   officeholder timeline — **the Morrison -> Albanese transition
   (2022-05-23) is government-source VERIFIED; every other date is
   still UNVERIFIED** (see its own status note for the full attempt
   log), and explicit confidence
   cautions.
3. Read `config/country_rules.yaml` for any Australia-specific
   exception entries (`trust_allowed`, `confidence_allowed`,
   `country_suffix_mappings`, `special_series_exceptions`). As of this
   writing every list in that file is empty for Australia — no
   exceptions are granted, so the canonical Skill's default rules apply
   unmodified: trust/confidence remain excluded, vote-intention remains
   excluded, and the workbook's Country field is the plain string
   `Australia` (per australia.md, modulo EAD's own trailing-space
   variant, which is a whitespace artifact, not a different country),
   not a `Country_PM`/`Country_GOV` split. If this file is later
   updated with a real Australia entry, that entry governs over the
   defaults described here.

## What this Skill covers

General survey-based public support for the Australian **Prime
Minister** as an individual office-holder — series that target the PM
specifically, not the Government as a whole and not a generic "country
leadership" measure.

Eligible (canonical Skill section 2, applied to the PM):

- job approval / disapproval
- job satisfaction / dissatisfaction
- overall performance
- favorable / unfavorable opinion
- positive / negative image or "impression"
- general approval / general satisfaction / sympathy

Not eligible unless `config/country_rules.yaml` grants an Australia
exception (none currently exists):

- trust in the PM
- confidence in the PM

## Explicit exclusions for this task

Per canonical Skill sections 3, 25, 43, 44, and australia.md's own
classification:

- **Government-as-a-whole approval is excluded** when the research
  target is the individual PM. `CSES` is the one series in
  australia.md's table classified out of scope for this reason — its
  EAD question wording explicitly branches to "the government in
  [CAPITAL]" or "the president," not the Prime Minister. Do not record
  new Australia CSES observations against this PM assignment, and do
  not treat it as continuity for a PM series.
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
- **Generic "leadership of this country" / "leader of this country"
  wording is not automatically treated as PM-eligible.**
  `GALLUPWORLD_LSHP` and `GALLUPWORLD_LDR` are flagged
  "requires verification" in australia.md for exactly this reason —
  route new observations in these series to REVIEW, never automatic
  APPROVED, until the specific wording or source context confirms the
  Australian Prime Minister is the target.

## Series-matching guidance specific to Australia

- Prefer matching to an existing series in australia.md's table over
  proposing a new one, whenever pollster, wording, and PM-target are
  consistent with that series's established pattern.
- Route the following to REVIEW rather than automatic approval, per
  australia.md's own classification and confidence cautions:
  `FOX&HEDGEHOG` (its EAD Description is an unresolved internal
  placeholder, not real metadata); `FreshwaterStrategy` and
  `Freshwater Strategy` (a generic multi-figure favorability battery,
  not wording that names the PM); `GALLUPWORLD_LSHP` and
  `GALLUPWORLD_LDR` (international "leadership of this country"
  programs, PM-target not independently confirmed); and single-record
  series generally (`GALLUPWORLD_LDR`, `FOX&HEDGEHOG`).
- **Do not merge `Freshwater Strategy` with `FreshwaterStrategy`, or
  `NEWSPOLL/YouGov` with `NEWSPOLL/YOUGOV` (EAD's spelling).** Both
  pairs are alias/casing candidates surfaced by
  `python/report_country_ead_coverage.py`, but this task explicitly
  requires they stay separate, raw values preserved, flagged for human
  review rather than auto-merged.
- **`NEWSPOLL/PYXIS` is real EAD metadata with zero matching Master
  rows today.** If a new source is clearly a Newspoll/Pyxis-branded
  wave, match it to `NEWSPOLL/PYXIS`, not to plain `NEWSPOLL` — do not
  fold it into `NEWSPOLL` merely because both start with "Newspoll."
- A genuinely new series (no plausible match anywhere in australia.md)
  requires `SERIES_REVIEW_REQUIRED` per canonical Skill section 11 —
  never auto-approve a new Australia series.

## Leader assignment — partly verified officeholder timeline

australia.md includes a Prime Minister officeholder timeline (Harold
Holt through Anthony Albanese). As of 2026-08-25:

- **The Morrison -> Albanese transition (2022-05-23) is VERIFIED** —
  directly retrieved and quoted from `https://www.pm.gov.au/about-prime-minister`,
  the official Prime Minister of Australia government website: "The
  Hon Anthony Albanese MP was sworn in as Australia's 31st Prime
  Minister on 23 May 2022."
- **Every other date remains UNVERIFIED** — Wikipedia was used only as
  a discovery aid for these candidate dates; repeated attempts to
  confirm them from `aph.gov.au`, `gg.gov.au`, and `naa.gov.au` failed
  for environmental/access reasons documented in australia.md's own
  attempt log (this Skill does not treat those failures as evidence the
  dates are wrong, only as evidence they are not yet independently
  confirmed).

Assign every observation's `executive_name` from that table by
comparing the observation's own Date against the officeholder date
ranges — **never** by assuming a recent-looking series or a recent Date
belongs to the current PM. In particular:

- The Morrison -> Albanese transition is **2022-05-23** exactly (the day
  Albanese was sworn in, immediately after Morrison's term ended) — use
  this precise date; it may now be described as government-source
  verified in reports.
- Do not describe any *other* row (Morrison's own start date, or any
  earlier PM) as verified — only the Morrison -> Albanese boundary has
  actually-retrieved authoritative provenance behind it.
- If `config/country_rules.yaml` or a future update to australia.md
  extends or corrects this timeline (e.g. a new PM, or a further
  government-source verification pass), that update governs; this
  Skill does not hardcode an assumption that Albanese remains PM
  indefinitely.

## Required fields

Use the same structured candidate observation as canonical Skill
section 30, with `country = "Australia"` and `executive_type` = Prime
Minister. Do not invent a `Country_PM`/`Country_GOV` split for
Australia — australia.md confirms the snapshot uses a single plain
`Australia` country value; PM vs. Government is distinguished by series
classification (see australia.md's scope table), not by a Country
suffix.

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

- any new or ambiguous series not clearly matched in australia.md
- any series in australia.md's "requires verification" table
- any conflict with an existing non-empty workbook value
- any observation whose Date falls outside every range in the
  officeholder timeline (do not guess a PM for it — and remember only
  the Morrison -> Albanese boundary is government-source verified; every
  other date is still UNVERIFIED, see above)

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
full australia.md table or full workbook contents into agent context.
Summarize findings in the final report per canonical Skill section 41.
