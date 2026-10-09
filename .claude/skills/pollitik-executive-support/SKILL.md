---
name: pollitik-executive-support
description: Research, classify, validate, normalize, and stage survey-based public-support data for presidents, prime ministers, chancellors, governments, and equivalent political executives in the Pollitik Database. Use this skill whenever collecting, interpreting, translating, matching, validating, or preparing executive approval, satisfaction, favorability, image, performance, or approved country-specific trust/confidence polling data.
---

# Pollitik Executive Support Research Skill

## Mission

You are working on an academic political polling database called:

`Pollitik Database`

Your responsibility is to identify, extract, interpret, normalize, validate, and stage survey-based measures of PUBLIC SUPPORT FOR POLITICAL EXECUTIVES.

Accuracy, reproducibility, provenance, and transparency are more important than filling every missing cell.

NEVER invent data.

NEVER invent a source.

NEVER invent a URL.

NEVER infer a polling result simply because it seems plausible.

NEVER fill a value merely because a database cell is empty.

If evidence is insufficient, record the observation as unresolved rather than guessing.

## 1. Political executives

Political executives include heads of government and, where relevant, heads of state.

Examples include:

- President
- Prime Minister
- Chancellor
- Taoiseach
- equivalent locally used executive titles

Do not assume the English title President or Prime Minister.

Determine the office actually being evaluated by the survey.

## 2. Public support

Collect GENERAL evaluations of the executive.

Eligible concepts generally include:

- overall job approval
- overall job disapproval
- job satisfaction
- job dissatisfaction
- overall performance
- favorable opinion
- unfavorable opinion
- positive image
- negative image
- positive evaluation
- negative evaluation
- general approval
- general satisfaction
- sympathy

Potentially eligible for specifically approved countries:

- trust
- confidence

Trust and confidence are NOT generally eligible unless country-specific rules explicitly permit them.

## 3. Exclude issue-specific approval

Do NOT collect evaluations tied to a specific issue.

Examples:

- economy
- inflation
- foreign affairs
- healthcare
- immigration
- crime
- education
- war
- environment
- a particular reform
- a specific crisis

GENERAL EVALUATION OF EXECUTIVE
= eligible

ISSUE-SPECIFIC EVALUATION
= exclude

If uncertain, preserve the wording and mark REVIEW.

Do NOT collect vote intentions for specific incumbents, candidates or parties.

Do NOT collect preferred Prime Minister or preferred President.

## 4. Survey data only

Eligible evidence must derive from a survey of respondents.

Do not treat these as polling observations unless they clearly report an underlying survey:

- journalist commentary
- election results
- betting markets
- social media sentiment
- search trends
- forecasts
- expert ratings
- editorials

Secondary reporting may be used to discover an original poll but should not replace the original pollster source when it is available.

## 5. Source provenance

Source verification is NON-NEGOTIABLE.

Every observation must have a real retrievable source.

The LLM MUST NOT generate the source URL from memory.

A source URL must originate from:

- actual WebFetch retrieval metadata
- an approved HTTP fetcher
- a retrieved document URL
- another explicitly approved deterministic retrieval mechanism

A URL merely written by the model is NOT valid provenance.

For each source preserve when available:

- requested URL
- final resolved URL
- source domain
- title
- pollster
- retrieval timestamp
- retrieval success/status
- source language
- relevant source text
- relevant table/chart context
- page number for documents/PDFs when available

If retrieval fails:

SOURCE_VALIDATION_FAILED

If a URL exists only in model-generated prose and was never successfully fetched:

UNVERIFIED_SOURCE_URL

Do not write that observation to production.

## 6. WebFetch enforcement

Search or model memory may be used only to DISCOVER a possible source.

Before a source can support any Pollitik observation:

1. retrieve the specific source with WebFetch or another approved deterministic retrieval mechanism
2. confirm retrieval succeeded
3. confirm the final domain is allowed
4. inspect retrieved content
5. confirm the content supports the claimed value
6. store the retrieved URL from tool metadata
7. preserve evidence text

Search-engine snippets are discovery aids only.

They are not valid academic evidence.

No observation may receive source_verified=true solely from an LLM assertion.

## 7. Prefer original sources

Preferred order:

1. original polling organization
2. original survey report
3. original pollster press release
4. original pollster table/data page
5. official institutional survey repository
6. archived original pollster material where necessary

Secondary reporting may help locate the source.

Trace results to the original pollster whenever reasonably possible.

## 8. Approved websites

Before external research:

1. read the project approved-domain configuration
2. verify the destination host
3. use only approved domains or explicitly user-approved exceptions
4. reject unauthorized hosts

If information cannot be found on approved sources:

NOT_FOUND_ON_APPROVED_SOURCES

Do not silently broaden the search.

Do not use URL shorteners, mirrors, proxies, alternate domains, or cached copies to evade domain restrictions.

Discovery (search, model knowledge, citation trails) may surface a
promising domain that is not yet approved. A search result or candidate
URL is NOT evidence, and an unapproved domain must never be fetched.
This includes any domain sitting in `config/candidate_domains.txt` -
that file is discovery-tier only and being listed there is not
approval. See section 50 for the full domain-approval-request workflow
when this happens - the short version: identify the domain, explain
what it may contain and why, identify the country/pollster/program it
relates to, and request approval BEFORE any WebFetch, using status
DOMAIN_APPROVAL_REQUIRED. `python/check_domain.py --url <url>` reports
this deterministically without fetching anything.

## 9. Multilingual sources

Pollitik is multilingual.

Valid sources may be in any language.

For each relevant extracted item preserve:

- original source wording
- source language
- English interpretation
- normalized database value

Never discard the original wording.

Translate meaning accurately rather than forcing literal translation.

Preserve local political titles when relevant.

Example:

Original:
Très satisfait

English:
Very satisfied

Classification:
positive

## 10. Question wording determines series

Question wording is the strongest evidence for assigning a series.

Each distinct recurring survey item should generally be a separate SERIES.

Examples:

- job approval
- job satisfaction
- favorability
- image
- performance

Do not merge:

"Do you approve or disapprove of the way X is handling their job?"

with:

"Do you have a favorable or unfavorable opinion of X?"

unless the existing Pollitik schema explicitly establishes that they are the same series.

Question wording may be:

- exact text
- chart label
- questionnaire text
- methodology text
- descriptive prose

Classify wording status as:

EXACT_WORDING
PARTIAL_WORDING
IMPLIED_WORDING
UNKNOWN_WORDING

Never invent exact wording.

## 11. Series matching

Before assigning to an existing series compare:

- executive
- institutional target
- question wording
- response scale
- response labels
- pollster
- survey program
- existing historical series
- prior human corrections

Prefer an existing series when continuity is supported.

Do not create a new series merely because punctuation or capitalization differs.

Do not merge series because their percentages look similar.

Ambiguity:

SERIES_REVIEW_REQUIRED

A genuinely NEW series (no plausible existing match at all, not merely
an ambiguous one) also requires SERIES_REVIEW_REQUIRED. Creating a new
series is not something to do silently.

## 12. Country coding

The Country field may encode geography plus executive type.

Use the existing Pollitik workbook as the canonical reference.

Presidential systems may use a simple country value.

Parliamentary systems may distinguish:

Country_PM
Country_GOV

Dual-executive systems may distinguish:

Country_Pres
Country_PM
Country_Gov

These suffixes are examples only.

Never invent a new naming convention if the existing database establishes one.

## 13. Existing dataset as reference

The Pollitik workbook is the canonical reference for:

- Country naming
- series names
- pollster naming
- date formatting
- executive coding
- response conventions
- source conventions
- known exceptions

Before classifying a new observation:

1. retrieve relevant existing examples
2. compare likely Country
3. compare likely series
4. compare pollster
5. compare question wording
6. compare response labels
7. consult validated human corrections

Use relevant examples rather than loading the entire workbook unnecessarily.

The existing dataset is reference material only.

It is NOT evidence for a new external polling fact.

## 14. Response aggregation

Collect when applicable:

- positive
- negative
- neutral

Collapse underlying component categories into positive, negative and, where available, neutral.

Example:

Very poorly = 14
Poorly = 22
Well = 40
Very well = 18

Should be collapsed as follows:

negative = 14 + 22 = 36
positive = 40 + 18 = 58

Do not invent neutral. 

Do NOT categorize don't know (DK) percentages or non-response (NR) percentages as neutral.

Do NOT include net scores (positive - negative). Do NOT calculate a missing value based on the net score and either a positive or negative rating.

Documentation note: the source EAD manual's own Table 1
(`docs/ead/EAD MANUAL.txt`) appears to contain a copy/paste
inconsistency in its 3- and 4-response-category "Neg" column wording
(e.g. listing "disapprove, good, well" rather than clearly negative
labels). The worked example above is logically correct and authoritative
for this Skill — do not alter it to match Table 1's literal wording.

## 15. Response aggregation of odd-number scales

Example:

Very poorly = 10
Poorly = 18
Neither well nor poorly = 14
Well = 35
Very well = 20

negative = 28
neutral = 14
positive = 55

## 16. Nonresponse is not neutral

These categories are not neutral unless explicitly defined that way:

- don't know
- no opinion
- refused
- no answer
- uncertain
- can't say
- not applicable

Preserve separately when available.

## 17. Multilingual category mapping

Interpret foreign-language categories contextually.

Do not force unfamiliar terms into positive, negative, or neutral if uncertain.

If uncertain:

RESPONSE_MAPPING_REVIEW_REQUIRED

## 18. Arithmetic

The LLM may classify response categories.

Deterministic Python or R code should calculate totals wherever possible.

Calculate:

positive = sum(positive components)
negative = sum(negative components)
neutral = sum(neutral components)

Allow normal survey rounding.

Never alter reported values simply to force 100%.

Possible statuses:

ARITHMETIC_OK
ROUNDING_DIFFERENCE
ARITHMETIC_REVIEW_REQUIRED

Two further summary fields are also computed deterministically, never
by the LLM. See section 47.

## 19. Fieldwork date

Collect survey FIELDWORK END DATE where available.

Output format:

m/d/yyyy

or

mm/dd/yyyy

Example:

January 3-8, 2026
=> 1/8/2026

January 29-February 2, 2026
=> 2/2/2026

December 28, 2025-January 3, 2026
=> 1/3/2026

## 20. Missing exact fieldwork date

If only month and year are available and project rules allow imputation:

use the 15th.

January 2026
=> 1/15/2026

Mark:

IMPUTED_MONTH_MIDPOINT

Do not claim the 15th was an observed fieldwork date.

If neither exact date nor usable month/year exists:

FIELDWORK_DATE_UNKNOWN

Do not invent a date.

## 21. Publication date is not fieldwork date

Do not automatically substitute:

- page publication date
- article date
- report publication date
- upload date

for fieldwork date.

## 22. Sample size

Collect total relevant sample size when available.

It may appear as:

- N
- n
- sample size
- respondents
- interviews
- observations
- cases

Store as an integer where possible.

Example:

N = 1,204
=> 1204

Preserve raw wording.

Do not confuse:

- total N
- subsample N
- weighted N
- effective N
- respondents answering only one item

If ambiguous:

SAMPLE_SIZE_REVIEW_REQUIRED

A narrow, explicitly-flagged exception for filling an unconfirmed
sample size from an established firm pattern exists — see section 45.
It is never a substitute for confirming the actual figure when possible.

Sample_Size is an OPTIONAL/supporting field (section 49): collect it
whenever available, but its absence never by itself rejects an
otherwise valid, sourced observation. If the source explicitly does not
report a sample size (as opposed to extraction simply not having found
it yet), leave it null and note status SAMPLE_SIZE_NOT_FOUND. Never
infer a sample size just to fill the field.

Where the workbook or historical documentation refers to this same
field as "Total Count" (a survey-N field, semantically identical to
Sample_Size), treat it as the same field, never a second one — see
`config/schema_mapping.yaml`, which `python/apply_changes.py` reads to
recognize a "Total Count" column as Sample_Size. Do not rename an actual
production column to make this true; the alias handles it.

## 23. Pollster identity

Distinguish:

- polling firm
- sponsor
- media outlet
- publisher
- academic institution

Do not assume the website host is necessarily the pollster.

Pollster's primary role in this Skill is identifying, naming,
differentiating, and matching Series (sections 10-11) — pollster
identity, together with question wording, response scale, and
executive/institutional target, is core evidence for whether a new
observation continues an existing series. Pollster is NOT itself a
substantive measure of executive support, and it is an
OPTIONAL/supporting field (section 49): do not reject an otherwise
valid, sourced observation merely because pollster is temporarily
unavailable if the source and series can otherwise be established. If
pollster identity is genuinely required to determine series continuity
and cannot be established, use SERIES_REVIEW_REQUIRED rather than
fabricating a pollster name.

Question wording remains the strongest evidence for series identity
(section 10); pollster helps define/match a series but never replaces
question wording.

## 24. Multiple survey items

If one survey asks:

- approval
- satisfaction
- favorability

these are potentially three separate series.

Do not collapse them simply because they use the same sample and dates.

## 25. Government vs executive

Distinguish:

approval of Prime Minister X

from:

approval of the government

They may map to separate Country codes and series.

## 26. Executive changes

Do not automatically create a new series when an officeholder changes.

A recurring item may continue across administrations.

Likewise, do not assume continuity if wording or institutional target changes.

## 27. Duplicates

Before staging, compare:

- Country
- series
- pollster
- fieldwork date
- executive
- question wording
- positive
- negative
- neutral
- sample size
- source

Do not duplicate a poll because it appears on multiple pages.

Prefer original pollster provenance.

## 28. Charts

For chart-only results:

1. inspect chart title
2. identify series
3. identify dates
4. identify labels
5. identify response values
6. distinguish printed values from visually estimated values

Use flags:

EXACT_PRINTED_VALUE

VISUALLY_ESTIMATED_VALUE

Prefer underlying tables or downloadable data when available.

## 29. PDFs/documents & Wikis

Preserve:

- document URL
- document title
- page number
- relevant text/table context

Do not treat methodology text as polling results.

Extract website information from first column naming opinion polling firm and, where possible, use the hyperlink for WebFetching and domain validation. Match other information from the remaining columns as necessary.

## 30. Required structured candidate observation

Before Excel writing, create a structured candidate with fields equivalent to:

country
country_base
executive_type
executive_name
series
pollster
question_wording_original
question_wording_english
question_wording_status
source_language
positive
negative
neutral
response_categories
fieldwork_start_raw
fieldwork_end_raw
fieldwork_date_normalized
fieldwork_date_status
sample_size
sample_size_raw
source_url
source_title
source_domain
retrieved_at
evidence_text_original
evidence_text_english
source_verified
series_match_status
validation_status
validation_reason

Actual workbook column names must come from the Pollitik workbook.

Do not invent workbook columns.

## 31. Source verification rule

source_url must NEVER originate solely from model-generated text.

Before:

source_verified=true

the validator must confirm:

- source was actually fetched
- retrieval succeeded
- source domain is approved
- final resolved URL is recorded
- evidence appears in retrieved content

If not:

source_verified=false

and writing must be blocked.

## 32. Evidence-level validation

Every substantive value must have supporting evidence.

positive must have supporting response evidence.

negative must have supporting response evidence.

neutral must have supporting response evidence.

sample_size must have sample-size evidence.

fieldwork date must have fieldwork evidence or an explicit documented date-imputation rule.

Do not use one piece of evidence to justify unrelated fields.

## 33. Confidence is not evidence

Never approve a result just because the model reports high confidence.

Confidence may be metadata only.

Source evidence and deterministic validation decide whether a record is approved.

## 34. Statuses

Use:

APPROVED
REVIEW
REJECTED
NOT_FOUND

Reason codes may include:

NOT_FOUND_ON_APPROVED_SOURCES
SOURCE_VALIDATION_FAILED
UNVERIFIED_SOURCE_URL
SERIES_REVIEW_REQUIRED
RESPONSE_MAPPING_REVIEW_REQUIRED
SAMPLE_SIZE_REVIEW_REQUIRED
FIELDWORK_DATE_UNKNOWN
QUESTION_WORDING_UNKNOWN
ARITHMETIC_REVIEW_REQUIRED
SAMPLE_SIZE_INFERRED_FROM_PATTERN
DOMAIN_APPROVAL_REQUIRED
NEGATIVE_NOT_REPORTED
SAMPLE_SIZE_NOT_FOUND
SERIES_MATCH_EXACT
SERIES_MATCH_NORMALIZED
SERIES_MATCH_SUPPORTED
WORDING_INHERITED_FROM_SERIES_REFERENCE

DOMAIN_APPROVAL_REQUIRED is a discovery-time status (section 50), not a
validation_status - it means a candidate domain looks useful but is not
yet approved, so no fetch was attempted. NEGATIVE_NOT_REPORTED and
SAMPLE_SIZE_NOT_FOUND are informational field-level statuses the
extractor/matcher may set (section 49) when a source explicitly does
not report that optional value - neither blocks APPROVED on its own.
SERIES_MATCH_EXACT / _NORMALIZED / _SUPPORTED are informational
positive signals from comparing against the EAD reference workbook
(section 55) - never themselves a reason to approve; only
SERIES_REVIEW_REQUIRED from that same comparison affects
validation_status. WORDING_INHERITED_FROM_SERIES_REFERENCE is likewise
informational only, set once the validator's independent
`verify_wording.py` re-derivation (section 48) confirms a
matcher-proposed `INHERITED_FROM_SERIES_REFERENCE` wording status - it
never itself blocks APPROVED.

## 35. Write policy

Research agents MUST NOT directly edit production Pollitik Excel files.

Required workflow:

source discovery
-> WebFetch/approved retrieval
-> provenance capture
-> multilingual extraction
-> reference matching
-> normalization
-> deterministic validation
-> staging
-> approved write

Only APPROVED observations may be written automatically.

REVIEW, REJECTED, and NOT_FOUND must not be written as validated observations.

## 36. Existing-value conflicts

If an existing non-empty workbook value conflicts with a new value:

DO NOT silently overwrite it.

Create a conflict record containing:

- existing value
- proposed value
- existing source if available
- new source
- relevant date
- discrepancy reason

Mark REVIEW unless an explicit project rule authorizes replacement.

## 37. Preserve raw information

Never retain only normalized data.

Preserve whenever available:

- original text
- original language
- original response labels
- component percentages
- original date description
- raw sample-size wording
- exact retrieved URL

## 38. Human corrections

Human corrections to:

- Country
- series
- translation
- category mapping
- pollster identity
- date interpretation
- sample size

must be stored as reference examples for future tasks.

This is retrieval-based learning.

Do not call it retraining Claude.

Country-level research-strategy notes (which sources worked for a given
country, how a hard-to-find series was located) are worth preserving
the same way once there is a real per-country place to put them. That
structure does not exist yet in this repo — no real countries have been
researched yet — so do not invent one; note findings in your report in
the meantime.

## 39. Required workflow

For each research task:

A. inspect existing Pollitik examples

B. identify requested missing observations

C. discover candidate original sources

D. fetch source with WebFetch or approved retrieval

E. capture actual retrieval metadata

F. preserve raw evidence

G. translate if necessary

H. map Country and series

I. aggregate response categories

J. determine fieldwork date

K. determine sample size

L. validate source and arithmetic

M. duplicate-check

N. stage candidate

O. write only APPROVED records

## 40. Missing information

Missing is better than fabricated.

Use null plus appropriate status when:

- sample size unavailable
- question wording unavailable
- fieldwork unavailable
- source unavailable
- neutral does not exist
- Country mapping uncertain
- series mapping uncertain

Never guess merely to complete a row.

## 41. Final report

At the end of each research task summarize:

- countries researched
- executives researched
- pollsters found
- languages encountered
- sources fetched successfully
- source-fetch failures
- observations discovered
- observations approved
- observations requiring review
- observations rejected
- duplicates skipped
- requested observations not found
- fieldwork dates imputed
- unresolved Country mappings
- unresolved series mappings

## 42. Core academic rule

When forced to choose between:

A. maximizing database completeness

and

B. preserving academic validity and reproducibility

always choose B.

Another researcher must be able to trace each observation back to the original survey source and understand:

- who was evaluated
- what question was asked
- which responses became positive
- which responses became negative
- which responses became neutral
- when fieldwork occurred
- the survey sample size
- where the original source can be retrieved

No fabricated URL, unsupported number, invented wording, guessed series, or unexplained transformation is acceptable.

## 43. Vote-intention ("Sunday question") exclusion

Do not collect vote-intention items, e.g.:

"If the election were held this coming Sunday, which party would you vote for?"

This measures a potential behavior, not an attitude toward the executive.

Never combine a vote-intention item with an approval-style series, even
if asked in the same survey.

If a vote-intention series is ever explicitly authorized for collection,
prefix its series name with SUN, e.g.:

SUNGALLUP
SUNIPSOS

Record marginals for as many response options (parties) as available,
using multiple columns as needed.

This convention (and the exclusion itself) comes directly from the
source EAD Data Collection Manual (`docs/ead/EAD MANUAL.txt`, FAQ
section) — it is not a Pollitik-only addition, and must not be silently
dropped or reworded.

## 44. Continuous-scale grading questions

Questions asking respondents to grade the executive on a continuous
scale (e.g. 1-7, 1-10, 1-100) are excluded by default.

Narrow exception: if the continuous scale is combined with an
approval-disapproval prompt AND has clear approval-disapproval anchors,
it may be recorded like any other question — only with explicit
authorization. Do not make this judgment call silently.

## 45. Sample-size inference from an established firm/series pattern

Do not guess a sample size from general knowledge of a firm.

A narrow exception exists: if the exact sample size for a specific data
point cannot be confirmed, but `python/reference_lookup.py` shows the
same pollster/series actually recurring with a consistent sample size
elsewhere in the existing data, that value may be proposed.

Mark it:

sample_size_status: INFERRED_FROM_FIRM_PATTERN

This always routes to REVIEW (validate_record.py: SAMPLE_SIZE_INFERRED_FROM_PATTERN).

It is never silently APPROVED, and it is never based on assumed
knowledge of a firm's typical practices — only on a pattern actually
visible in this project's own reference data.

Only the matcher role may propose this status, and only after checking
reference_lookup.py itself.

## 46. Multi-wave survey-program naming convention

Some survey programs recur across many countries and field through
different firms across waves (e.g. Latinobarómetro, Eurobarometer,
CSES, the World Values Survey/European Social Survey).

When naming a series for such a program, use:

PROGRAM_ABBREVIATION + FirmName

Example: for Latinobarómetro fielded by different firms across waves,
name the series LB + the firm's name (e.g. LBGallup, LBMitofsky), even
if the fielding firm changes from wave to wave — group them under the
program's own naming convention.

Never invent a new naming scheme for a program if the workbook or
`config/country_rules.yaml` already establishes one for it.

**Legacy CSES/ESS naming caution**: the source EAD manual
(`docs/ead/EAD MANUAL.txt`) explicitly states that historical CSES and
ESS entries in the real dataset predate this convention and were never
backfilled to follow it. Do not treat an existing CSES/ESS series name
found via `reference_lookup.py` as a reliable model for how a *new*
CSES/ESS series should be named — matching wording/pollster/program to
an old, pre-convention CSES/ESS entry does not establish that its name
follows the `PROGRAM_ABBREVIATION + FirmName` pattern. When naming a new
CSES/ESS series, apply the convention directly rather than copying an
existing series name mechanically. If genuinely unsure whether an
existing CSES/ESS series should be treated as continuous with a new
data point, this is exactly the kind of ambiguity that gets
`SERIES_REVIEW_REQUIRED` (section 11) rather than a silent guess.

## 47. Net and App/App+Dis computed fields

Two summary fields are computed deterministically from positive and
negative, whenever both are present:

net = positive - negative

app_app_dis = positive / (positive + negative) * 100

Leave both blank if either positive or negative is missing.

These are computed by python/validate_record.py, never estimated by
the LLM, using the same deterministic-arithmetic principle as the
positive/negative/neutral totals in section 18.

## 48. Canonical wording inheritance from an established series reference

A new observation's own source does not always repeat the exact survey
question. Do not treat that alone as UNKNOWN_WORDING forever: a narrow
exception exists, parallel in spirit to section 45's sample-size
inference, using the EAD Series/Question-Wording reference workbook
(section 54; the project's canonical series/question reference,
distinct from the master workbook itself).

The canonical wording on record for an established series may be
inherited for a new observation only when ALL of the following hold:

- the candidate is confidently matched to an existing series (not
  `SERIES_REVIEW_REQUIRED`);
- the EAD reference file contains exactly one row for that exact
  (Country, Series) pair, with a non-blank Question Type and Question
  Wording;
- that row is an executive/individual-officeholder approval item
  applicable to the candidate (not a government-as-a-whole or
  issue-specific item — section 25 still applies: the exact-series
  match, not the pollster name, is what establishes this);
- nothing in the new observation's own source suggests the pollster
  added or changed the applicable question for this series.

Mark it:

question_wording_status: INHERITED_FROM_SERIES_REFERENCE

Distinguish this from wording confirmed directly in the new
observation's own source (EXACT_WORDING / PARTIAL_WORDING /
IMPLIED_WORDING): record `question_wording_source: EAD_SERIES_REFERENCE`
so the provenance of the wording text — reference file vs. the
individual poll release — stays traceable.

This status is never accepted on the matcher's assertion alone. It is
re-derived deterministically (`python/verify_wording.py`, called from
`python/validate_record.py`) against the actual EAD reference file: zero
matching rows, more than one matching row, or a row missing wording/type
text all fall back to QUESTION_WORDING_UNKNOWN regardless of what the
matcher proposed. This mirrors section 33 (confidence is not evidence)
and the same re-derivation principle already applied to source
provenance.

Do not inherit wording merely because the pollster name matches — the
exact (Country, Series) match, confirmed unique in the reference file,
is what licenses inheritance, not the firm's name alone.

Only the matcher role may propose `INHERITED_FROM_SERIES_REFERENCE`, and
only for a confidently-matched existing series. If the series match
itself is ambiguous, `SERIES_REVIEW_REQUIRED` still forces REVIEW
regardless of any wording status.

Unlike section 45's sample-size inference (which always routes to
REVIEW even when accepted), a successfully verified wording inheritance
does not by itself force REVIEW — it satisfies the wording requirement
for APPROVED status, same as directly-confirmed wording would, while
every other REVIEW reason (sample size, fieldwork date, arithmetic,
series ambiguity, source problems) is entirely unaffected by it.

This is a distinct mechanism from `ead_wording_match_status` (section
55): that field is the matcher's own comparison of a *directly-sourced*
proposed wording against the reference workbook (used to help resolve
series identity), whereas `INHERITED_FROM_SERIES_REFERENCE` is for when
the new observation's source has no wording to compare at all, and the
reference wording is adopted in its place. `SERIES_MATCH_EXACT` /
`_NORMALIZED` / `_SUPPORTED` / `SERIES_REVIEW_REQUIRED` remain exactly
as documented in section 55; this section does not change how the
validator interprets that field.

## 49. Optional fields: Negative and Sample_Size

Negative and Sample_Size are useful and should be collected whenever
available. Neither is strictly required for an otherwise valid Pollitik
observation (see `config/schema_mapping.yaml`:
`optional_supporting_fields`).

- Missing Negative must not automatically reject an observation.
- Missing Sample_Size must not automatically reject an observation.
- Both remain null/missing when unavailable — never infer either one
  simply to fill a field (the narrow, always-REVIEW sample-size
  exception in section 45 is the only exception, and it is never
  silent).
- When a source explicitly does not report a value (as opposed to
  extraction simply not having attempted it), preserve that as a
  status: NEGATIVE_NOT_REPORTED / SAMPLE_SIZE_NOT_FOUND. This is
  informational, not itself a validation_status.
- These fields may still trigger REVIEW when the context genuinely
  requires it (e.g. SAMPLE_SIZE_REVIEW_REQUIRED for an ambiguous, not
  simply absent, value) — absence alone is not that trigger.

Pollster is likewise optional/supporting (section 23, section 51) — see
that section for its specific REVIEW-not-REJECT handling
(SERIES_REVIEW_REQUIRED) when it cannot be established.

## 50. Domain-approval workflow

Discovery (WebSearch, model knowledge, citation trails in already-found
sources) may surface a domain that is not yet in
`config/allowed_domains.txt`. A search result or candidate URL is NEVER
evidence by itself, whether the domain is approved or not.

Before ANY retrieval from a domain not already in
`config/allowed_domains.txt`:

1. Identify the candidate domain.
2. Explain what data it may contain.
3. Explain why it may be useful for the requested observation.
4. Identify the country/pollster/survey program it relates to.
5. Request the project owner's explicit approval to add/access that
   domain.
6. Do NOT WebFetch the unapproved domain until approval is granted —
   `.claude/hooks/pollitik_guard.py` enforces this as a hard backstop,
   but the workflow is to ask first, not to attempt the fetch and let
   the hook deny it. `python3 python/check_domain.py --url <url>`
   reports APPROVED or DOMAIN_APPROVAL_REQUIRED deterministically,
   without any network call, so this can be checked before proposing a
   lead as usable.

Report a promising-but-unapproved lead with status
DOMAIN_APPROVAL_REQUIRED, separately from NOT_FOUND_ON_APPROVED_SOURCES
(which means nothing usable was found on domains that ARE already
approved).

Once the project owner approves a domain, add it through the existing
domain-configuration mechanism — `config/allowed_domains.txt` — one at a
time or as an explicit batch, per that file's own rules. Never add a
domain silently, and never broaden access globally (e.g. approving one
pollster's specific report page does not approve its entire parent
domain unless the owner says so, and does not approve a different
domain that merely looks similar).

After approval, the researcher may WebFetch the domain and use it for
actual evidence collection — subject to every other rule in this Skill
unchanged: real retrieval, source validation, evidence matching,
eligibility rules, staging, deterministic validation. A model-generated
URL is never valid provenance, approved domain or not (section 5).

**Candidate vs. approved domains are two different files with two
different meanings** — do not conflate them:

- `config/allowed_domains.txt` — the ONLY file
  `.claude/hooks/pollitik_guard.py` and `python/check_domain.py` treat
  as approved. A domain here may be WebFetched.
- `config/candidate_domains.txt` — discovery-tier only, never enforced.
  A domain being listed here (currently 381 entries, preserved from a
  2026-08-13 bulk workbook-derived batch that should never have been
  placed directly in the enforcement file — see that file's header for
  the full history) means it is a plausible lead worth reviewing, NOT
  that it is approved. Never treat presence in this file as
  authorization to fetch; promoting a specific entry to
  `config/allowed_domains.txt` still requires the project owner's
  explicit, per-domain (or explicit-batch) approval.

**Modular domain configuration.** `config/domains/` is a separate,
optional structure for recording WHY an *already-approved* domain was
approved and which country/pollster/program it belongs to (global vs.
country-specific) — see `config/domains/README.md`. It does not grant
access on its own either.

**Future source systems.** `config/source_systems.yaml` is the
documented registry for future databases/survey systems the researcher
may be pointed at (national polling archives, polling firms, academic
survey repositories, government survey systems, regional polling
databases, survey-program archives). It starts empty; consult it
alongside the "Where to look" guidance in the researcher agent, and
never register or treat a system as approved without the project
owner's explicit authorization — registering a system there is not
itself a domain approval (its domain(s) still need separate approval in
`config/allowed_domains.txt`).

## 51. Validator field requiredness

`config/schema_mapping.yaml` is the documented reference for which
fields are hard-required vs. optional for `python/validate_record.py`:

- **Core/required** (missing → REJECTED): Country, Series, verified
  Source/provenance.
- **Core/conditional** (missing → REVIEW, never an automatic REJECTED):
  Fieldwork_Date where available/derivable (sections 19-21), and the
  reported support measure(s), especially Positive when that is what
  the source reports.
- **Optional/supporting** (missing never rejects and never forces
  REVIEW by itself): Negative, Neutral (when the scale has none or it
  is not reported), Sample_Size, Pollster (when series identity can
  otherwise be established), Notes.

This classification does not override a stricter rule already
established elsewhere in this Skill or in the real EAD manual/schema —
if such a conflict is ever found, report it rather than silently
weakening the stricter existing requirement.

`Notes` (section 7's canonical field list) should preserve useful
methodological/contextual information that does not fit another
column — e.g. caveats about wording confidence or known discrepancies.

## 52. Future source-quality validation rules (placeholder)

`config/source_validation_rules.yaml` is the documented, currently-empty
home for source-authenticity/anti-fraud rules — source authenticity,
publisher identity, fake/copied websites, misleading domains,
impersonation sites, suspicious URL patterns, source credibility,
original-vs-secondary-source, and methodology transparency — to be
populated once the project owner supplies that guidance (referred to as
"Dr. Evans' PDF" as of this writing). Until then, none of those
categories are enforced beyond what sections 5-8 and 31 already require
(real retrieval + domain approval); do not invent rule content for that
file from general knowledge of what "fake site detection" usually
involves.

## 53. Global vs. country-specific configuration

This Skill and its supporting config (`config/allowed_domains.txt`,
`config/candidate_domains.txt`, `config/country_rules.yaml`,
`config/schema_mapping.yaml`, `config/source_systems.yaml`,
`python/*.py`) are GLOBAL — they apply to every country's research the
same way and must never be duplicated per country. A country-specific
Skill (e.g. `canada-pm-approval`) should extend this Skill by
reference, not restate it: it should load and follow this Skill in
full, then add ONLY genuinely country-specific facts and rules —
country coding conventions, PM/Gov distinctions, that country's
pollsters and survey series, that country's approved domains,
language/source notes, and documented country-specific exceptions (via
`config/country_rules.yaml`). If a country-specific Skill file contains
a restated copy of a global rule (source provenance, WebFetch
verification, positive/negative/neutral aggregation, staging,
validation, writer security, multilingual handling, fieldwork rules),
that is duplication to be removed in favor of a reference back to this
Skill, not preserved for convenience. `canada-pm-approval` (added
2026-08-13) already follows this pattern - see
`.claude/skills/canada-pm-approval/SKILL.md`, which loads this Skill
and `.claude/skills/pollitik-executive-support/references/canada.md`
rather than restating global rules; use it as the template for any
future country-specific Skill.

## 54. EAD Series/Question-Wording reference workbook

`docs/ead/reference/EAD Series and Question Wording.xlsx` (added
2026-08-14) is a second authoritative reference source, distinct from
the production master workbook. It catalogs known Series per Country
along with their Description, Question Type, Question Wording, and
fielding Method — the same six columns the source EAD manual's own
"EAD Series and Question Wording spreadsheet" section describes.

Source-of-truth hierarchy — do not blur these three:

- **Production Pollitik workbook** (`data/master/`) = canonical
  observation-level dataset. The only place an approved observation is
  actually recorded.
- **EAD Series/Question-Wording reference workbook** (this section) =
  authoritative reference for known Series/Question-Wording mappings —
  read-only, never modified by this project, and used to decide which
  existing Series a candidate continues.
- **DuckDB reference index** (`data/reference_index.duckdb`) =
  disposable derived lookup only, for both of the above (rebuild anytime
  with `python/build_reference_index.py` / `build_ead_reference_index.py`
  — they share the index file but each only ever rebuilds its own
  table). Never canonical for either source.

Like the master workbook (section 13), this reference workbook is NEVER
evidence that a new external polling observation occurred. It only
narrows which existing Series a genuinely-sourced candidate (real
retrieval, real evidence text, per sections 5-8) might belong to. An
observation with no independent verified source is not made valid by
matching this reference's wording.

Query it via `python3 python/ead_series_lookup.py` (built by
`python/build_ead_reference_index.py`) — never load the workbook
directly into an LLM context (token-efficiency principle, section 13).
`--wording-exact`/`--wording-contains` match on a normalized form
(case/whitespace/quote-insensitive; see
`pollitik_common.normalize_question_wording`) — the original wording in
both the reference and any candidate record is always preserved
unchanged alongside the normalized form used only for comparison.

This reference workbook has no dedicated Pollster or Executive_Type
column (confirmed by direct inspection, not assumed) — pollster/program
identity is embedded in its free-text Description field, and executive
type remains only implicit via the Country/Series suffix convention
already established in section 12. Do not invent a Pollster or
Executive_Type column for it.

## 55. Series matching with the EAD reference workbook

This extends, and does not replace, sections 10-11 (question wording is
still the strongest evidence for series identity). When resolving which
Series a candidate observation belongs to, work through these tiers in
order and stop at the first one that actually resolves it:

1. Exact question wording.
2. Normalized wording (case/whitespace/quote differences only).
3. The EAD Series/Question-Wording reference workbook (section 54).
4. Pollster/survey-program continuity.
5. Historical rows in the master-workbook reference index.
6. Semantic judgment — only once the deterministic tiers above are
   exhausted.

Never invent an existing-series relationship that none of these tiers
actually supports. If nothing resolves it: `SERIES_REVIEW_REQUIRED` —
this is true both for a genuinely new series and for one that is merely
ambiguous (section 11); do not auto-create a series either way.

Record the comparison against the reference workbook specifically as
`ead_wording_match_status`:

SERIES_MATCH_EXACT
SERIES_MATCH_NORMALIZED
SERIES_MATCH_SUPPORTED
SERIES_REVIEW_REQUIRED

The reference workbook's own inspection found real evidence for why
tier ordering matters: the same exact question wording (case) appears
under multiple genuinely different Series in dozens of cases (e.g. a
generic Spanish-language image-question template shared by nine
distinct Mexican pollster series) — an exact wording match alone is
sometimes not sufficient to pick a single Series, which is exactly why
pollster/program continuity (tier 4) and historical rows (tier 5) exist
as fallback tiers rather than treating wording as dispositive on its
own.

**Multilingual wording**: the reference workbook preserves each
Series's wording in its own original/vernacular language where known
(verified by inspection - e.g. Mexican entries are recorded in Spanish,
not translated to English), consistent with section 9. Compare a
candidate's `question_wording_original` against the reference's
`Question Wording` first; only fall back to comparing
`question_wording_english` against the reference when the reference
entry's own language differs from the candidate's original language.
Never fabricate a translation in either direction just to force a
match — an unresolved language mismatch is `SERIES_REVIEW_REQUIRED`,
not a guess. `question_wording_original` must always be preserved
regardless of which language the match was made in.

A missing or absent `ead_wording_match_status` is never itself a
reason to reject an otherwise valid, sourced observation — this
reference not having wording on file for a given Series (a known gap;
roughly 12% of its rows have no recorded wording) does not mean the
Series or the observation is invalid.
