# Australia Reference Profile

**Status:** Read-only reconnaissance profile for the Australian **Prime
Minister** approval/satisfaction/performance assignment. Compiled from
four sources only, all inspected directly (never invented):

1. `countries/australia/data/australia_reference_snapshot.csv` — the
   tracked, read-only export of Australia's existing reference
   observations (`Series, Date, Total Count, Positive, Neutral,
   Negative, Source, Country`).
2. `data/master/EAD Series and Question Wording.xlsx` — the canonical
   Series/Question Type/Question Wording reference (via
   `python/report_country_ead_coverage.py --country Australia`, and a
   direct read of the Australia rows for the actual wording text).
3. `https://www.pm.gov.au/about-prime-minister` — the official Prime
   Minister of Australia government website, actually retrieved via
   WebFetch on 2026-08-25 — **authoritative provenance for the Morrison
   -> Albanese transition (2022-05-23) only**. See "Prime Minister
   officeholder timeline" below.
4. Wikipedia (`en.wikipedia.org`) — used only as a **discovery aid** for
   candidate Prime Minister officeholder dates, never as final
   provenance. Every date other than the Morrison -> Albanese
   transition above is still marked **UNVERIFIED** — a real attempt to
   replace those with authoritative Australian government/parliamentary
   provenance did not succeed (network/access failures on the approved
   government domains tried), and this pass deliberately did not
   repeat those attempts for older officeholders (see the timeline
   section for what was and wasn't retrievable).

**Country field value in workbook/snapshot:** `Australia` (EAD stores it
with one trailing space, `"Australia "` — a whitespace-only variant,
correctly normalized by `pollitik_common.normalize_identifier()`, not a
different country).

**Totals:** 16 unique raw `Series` values in the tracked snapshot, 1,836
Australia records, dates spanning 1968-08-15 to 2026-02-15 (~58 years).
A 17th series name, `NEWSPOLL/PYXIS`, exists only in the EAD workbook
with zero matching rows in the current Master snapshot (see "EAD-only
series" below).

## Assignment scope reminder

This profile supports the **Prime Minister** assignment only: general
job approval, job satisfaction, overall performance, favorable/
unfavorable opinion, positive/negative image, or general
approval/sympathy toward the Australian PM **specifically**, not the
Government as a whole, not an issue-specific approval, and not a
generic "leadership of this country" measure unless the question
wording itself confirms it targets the PM. See
`.claude/skills/australia-pm-approval/SKILL.md` for the full scope
statement.

## Series table — classification for the PM assignment

Columns: EAD Description / EAD Question Type come only from the EAD
workbook, exactly as populated there (typos and trailing spaces
preserved verbatim, e.g. "Freshwater Stategy"). "Wording" is quoted
verbatim from the EAD workbook when populated; "not populated" means
the EAD cell itself is blank, not that no wording exists anywhere.

### In scope — confident (wording or description names the PM specifically)

| Series (raw) | Records | Earliest | Latest | EAD Description | EAD Question Type | Question Wording (verbatim where populated) |
|---|---|---|---|---|---|---|
| NEWSPOLL | 812 | 1985-01-12 | 2025-11-20 | Prime Minister Satisfaction | Satisfaction | "Are you satisfied or dissatisfied with the way [name] is doing his/her job as Prime Minister?" |
| MORGAN | 331 | 1968-08-15 | 2004-09-23 | Prime Minister Approval | Approval | "Do you approve or disapprove of the way [name] is handling his/her job as Prime Minister?" |
| MorningConsult | 247 | 2019-08-06 | 2026-02-15 | Morning Consult Global Leader Approval Tracker | Approval | Not populated in EAD — description names it a leader-approval tracker; same low-confidence caution Canada's own profile applies to this program (see "Cautions" below) |
| ESSENTIALRESEARCH | 140 | 2010-07-19 | 2025-12-20 | Prime Minister Satisfaction | Satisfaction | "Do you approve or disapprove of the way [name] is handling his/her job as Prime Minister?" |
| ACNIELSEN | 113 | 1996-05-05 | 2008-11-15 | AC Nielsen Approval | Approval | "Prime Minister Approval (approve or disapprove)" |
| NIELSEN | 26 | 2009-05-15 | 2011-07-15 | Formerly ACNIELSEN, measures approval | Approval | "Question of Approval" (EAD notes this is ACNIELSEN's direct continuation) |
| YouGov | 23 | 2023-09-28 | 2025-04-30 | YouGov | Satisfaction | "Thinking now about the leaders of the major parties. Are you satisfied or dissatisfied with the way Anthony Albanese is doing his job as Prime Minister?" |
| IPSOS | 35 | 2007-11-21 | 2022-05-18 | Prime Minister Satisfaction | Satisfaction | "Question of Satisfaction" (generic placeholder text, but EAD Description explicitly names PM Satisfaction) |
| Resolve Strategic | 49 | 2021-04-15 | 2025-12-20 | Resolve Strategic | Performance | "How would you rate Scott Morrison's performance as Prime Minister in recent weeks?" — a specific-officeholder snapshot of the wording; per canonical Skill section 26, an officeholder change does not by itself break series continuity, so later Resolve Strategic waves about Albanese are not assumed to be a different series without further evidence, but are also not assumed to use the identical name-swapped wording without it |
| NEWSPOLL/YouGov *(raw master spelling)* | 10 | 2022-09-02 | 2023-07-14 | *(EAD spells this `NEWSPOLL/YOUGOV`, see below)* | Satisfaction | "Thinking now about the leaders of the parties. Are you satisfied or dissatisfied with the way Anthony Albanese is doing his job as Prime Minister?" |

### EAD-only series — no matching Master rows yet

| Series | EAD Description | EAD Question Type | Question Wording |
|---|---|---|---|
| NEWSPOLL/PYXIS | NEWSPOLL/PYXIS | Satisfaction | "On balance, and while you may have no strong feelings either way, would you be more inclined to say you have been satisfied or dissatisfied with the way Anthony Albanese is doing his job as Prime Minister?" |

`NEWSPOLL/PYXIS` is real EAD metadata — a defined series with confirmed
PM-satisfaction wording — that currently has **zero** matching
observations in the Australia Master/reference snapshot. This is not a
merge candidate for `NEWSPOLL` or `NEWSPOLL/YouGov` (different raw
name, kept separate per this task's explicit no-auto-merge instruction)
and not a data-quality problem — it is simply a known series with no
recorded data yet. Treat any future NEWSPOLL/Pyxis-branded source as
this series, not as plain `NEWSPOLL`.

### Out of scope — clearly not the PM individually

| Series | Records | EAD Description | EAD Question Type | Question Wording | Why excluded |
|---|---|---|---|---|---|
| CSES | 3 | Comparative Study of Electoral Systems | Performance | "Now thinking about the performance of the [government in [CAPITAL]/president] in general, how good or bad a job do you think the [government/president in [CAPITAL]] has done..." | The program's own question wording branches to **government-as-a-whole** (or president) performance, not the Prime Minister individually — canonical Skill section 25 excludes government-as-a-whole approval from a PM-specific assignment. Do not record new Australia CSES observations against this PM assignment. |

### Requires human/research verification before use

| Series (raw) | Records | EAD Description | EAD Question Type | Question Wording | Why flagged |
|---|---|---|---|---|---|
| FOX&HEDGEHOG | 1 | "MIGUEL RESEARCH & ADD QUESTION WORDING" | *(blank)* | *(blank)* | The EAD Description field is itself an unfinished internal placeholder/to-do note, not a real description. Question Type and Question Wording are both blank. The single Master row (2026-01-06, 33/48) has approval-shaped numbers but nothing confirms the target is the PM. Do not treat as PM-eligible or as excluded until a human resolves the EAD placeholder. |
| FreshwaterStrategy | 22 | Freshwater Stategy *(sic, EAD typo preserved)* | Satisfaction | "Below are a list of figures in Australian Politics and culture. For each say whether you have heard of them, and if so, whether you have a favourable, unfavourable, or neutral view of them?" | This is a generic multi-figure favorability battery across Australian political/cultural figures, not a wording that names the PM specifically. Master Source URLs for this series point at `pollbludger.net`'s PM-leader-tracking page, suggesting the *recorded* observations are the PM slice of this battery, but the EAD wording itself does not confirm that for every row. Route new observations to REVIEW until the specific figure asked about is confirmed per source. |
| Freshwater Strategy *(raw master spelling, with a space)* | 4 | *(no separate EAD row — `series_skeleton` alias match against `FreshwaterStrategy` only, per `python/report_country_ead_coverage.py`)* | — | — | Per this task's explicit instruction, **not** auto-merged with `FreshwaterStrategy` despite the alias match. Same favorability-battery caution as above applies if it is later confirmed to be the same underlying program. |
| GALLUPWORLD_LSHP | 19 | Gallup World Poll (leadership) | Approval | "Do you approve or disapprove of the job performance of the leadership of this country?" | International multi-country program; "leadership of this country" is not the same as a question that names "Prime Minister." Canada's own reference profile applies the identical low-confidence caution to this series. |
| GALLUPWORLD_LDR | 1 | Gallup World Poll (leader) | Approval | "Do you approve or disapprove of the way the leader/head/President of this country is handling his/her job as leader/head/President?" | Same international-program caution as `GALLUPWORLD_LSHP`, plus single-record status (least corroborated row in the table). |

## Naming conventions observed

- Plain pollster/program name generally *does* encode PM target for
  Australia (unlike Canada, where plain names like `ANGUSREID`/`IPSOS`
  do not) — most Australia series' EAD **Description** field explicitly
  says "Prime Minister Approval" or "Prime Minister Satisfaction."
  Confirm via the table above rather than assuming this holds for a
  brand-new series.
- `NEWSPOLL/<partner>` naming (`NEWSPOLL/YouGov`, `NEWSPOLL/PYXIS`) marks
  a Newspoll wave fielded through a specific partner firm — each is its
  own series, not a `NEWSPOLL` variant, and not interchangeable with
  each other.
- Casing/spacing is **not** normalized between the Master snapshot and
  EAD for two series — flagged for human review, never auto-merged
  (per `python/report_country_ead_coverage.py`'s `normalized_case_matches`/
  `alias_candidates`, and this task's explicit instruction):
  - `NEWSPOLL/YouGov` (Master) vs `NEWSPOLL/YOUGOV` (EAD) — same
    normalized identifier, different raw casing.
  - `FreshwaterStrategy` vs `Freshwater Strategy` — same alnum skeleton,
    different raw spelling/spacing.

## Prime Minister officeholder timeline (for date-based leader assignment)

**Status: the Morrison -> Albanese transition is now VERIFIED from
authoritative Australian government provenance. Every other date below
remains UNVERIFIED** (candidate values only, discovered via Wikipedia
but not yet independently confirmed from an authoritative source).

### Morrison -> Albanese transition — VERIFIED 2022-05-23

Directly retrieved and inspected via WebFetch on 2026-08-25:

- **`https://www.pm.gov.au/about-prime-minister`** (retrieval
  succeeded) — verbatim quote: *"The Hon Anthony Albanese MP was sworn
  in as Australia's 31st Prime Minister on 23 May 2022."* This is the
  Prime Minister's own official government website — direct,
  authoritative provenance for the exact date.

Two further sources were named by the user as corroborating this same
date but could **not** be independently retrieved this session, so they
are recorded here as user-supplied corroboration only, not as
independently-verified provenance (this project's rule that a source is
valid only once actually retrieved still applies — see `CLAUDE.md`):

- `https://www.gg.gov.au/about-governor-general/governor-generals-program/canberra-australian-capital-territory-429`
  (Governor-General of Australia — described as recording the
  Governor-General receiving Scott Morrison's resignation and
  administering the oath/affirmation to Anthony Albanese on 23 May
  2022) — WebFetch timed out on every attempt (both this session and
  the prior one); domain is approved but unreachable in practice from
  this environment.
- `https://www.aph.gov.au/About_Parliament/Parliamentary_departments/Parliamentary_Library/Research/Chronologies/2022-23/Parliamentin2022`
  (Parliament of Australia / Parliamentary Library chronology —
  described as recording Albanese and four senior frontbenchers being
  sworn in on 23 May 2022) — WebFetch returned HTTP 403 (bot-blocked)
  on every attempt.

**Because one authoritative government source (`pm.gov.au`) was
actually retrieved and directly quotes the exact date, the Morrison ->
Albanese transition — 2022-05-23 — is treated as VERIFIED.** The date
value itself is unchanged from the prior (Wikipedia-discovered)
candidate value; only its provenance status changed, per this task's
instruction never to change a date without first verifying it. If
`gg.gov.au` or the `aph.gov.au` chronology becomes retrievable in a
future session, fetching them would add further independent
corroboration but is not required to treat this date as verified now.

### All other officeholder dates — still UNVERIFIED

Per this task's explicit instruction, this pass does not repeatedly
attempt the blocked `aph.gov.au`/`gg.gov.au`/`naa.gov.au` pages for
older Prime Ministers. Every date below other than the Morrison ->
Albanese transition remains a Wikipedia-discovered candidate value
only, requiring a future authoritative-source verification pass:

| Prime Minister | Party | Term start | Term end | Status |
|---|---|---|---|---|
| Harold Holt | Liberal | 1966-01-26 | 1967-12-17 (died in office) | UNVERIFIED |
| John McEwen *(caretaker)* | Country | 1967-12-19 | 1968-01-10 | UNVERIFIED |
| John Gorton | Liberal | 1968-01-10 | 1971-03-10 | UNVERIFIED |
| William McMahon | Liberal | 1971-03-10 | 1972-12-05 | UNVERIFIED |
| Gough Whitlam | Labor | 1972-12-05 | 1975-11-11 | UNVERIFIED |
| Malcolm Fraser | Liberal | 1975-11-11 | 1983-03-11 | UNVERIFIED |
| Bob Hawke | Labor | 1983-03-11 | 1991-12-20 | UNVERIFIED |
| Paul Keating | Labor | 1991-12-20 | 1996-03-11 | UNVERIFIED |
| John Howard | Liberal | 1996-03-11 | 2007-12-03 | UNVERIFIED |
| Kevin Rudd *(1st term)* | Labor | 2007-12-03 | 2010-06-24 | UNVERIFIED |
| Julia Gillard | Labor | 2010-06-24 | 2013-06-27 | UNVERIFIED |
| Kevin Rudd *(2nd term)* | Labor | 2013-06-27 | 2013-09-18 | UNVERIFIED |
| Tony Abbott | Liberal | 2013-09-18 | 2015-09-15 | UNVERIFIED |
| Malcolm Turnbull | Liberal | 2015-09-15 | 2018-08-24 | UNVERIFIED |
| Scott Morrison | Liberal | 2018-08-24 | **2022-05-23** | end date VERIFIED (see above); start date (2018-08-24) UNVERIFIED |
| Anthony Albanese | Labor | **2022-05-23** | incumbent (as of 2026-08-25) | start date VERIFIED (see above) |

**Discovery-aid sources (not provenance) for the UNVERIFIED rows:**
`en.wikipedia.org/wiki/List_of_prime_ministers_of_Australia` and
`en.wikipedia.org/wiki/Anthony_Albanese`, retrieved via WebFetch on
2026-08-25 for candidate values only — never treated as authoritative
provenance. Each successor's term is recorded as starting the same
calendar day the predecessor's ended (no gap requiring a null-PM period
in this data's range) — this continuity pattern is also still
unverified for every row except the Morrison -> Albanese boundary
itself.

## In-scope observation counts by Prime Minister (Albanese boundary now verified)

Computed by assigning every row in the "In scope — confident" series
above to the PM whose term range contains that row's Date (the 15 rows
in the "requires verification" series and the 3 CSES rows are excluded
from this count, not silently assigned to any PM). The Anthony Albanese
total below now rests on a verified start-date boundary (2022-05-23,
`pm.gov.au`); every other PM's count still rests on an unverified
candidate boundary and remains provisional.

| Prime Minister | In-scope rows |
|---|---|
| John Gorton | 7 |
| William McMahon | 14 |
| Gough Whitlam | 30 |
| Malcolm Fraser | 88 |
| Bob Hawke | 187 |
| Paul Keating | 157 |
| John Howard | 440 |
| Kevin Rudd (1st term) | 76 |
| Julia Gillard | 98 |
| Kevin Rudd (2nd term) | 10 |
| Tony Abbott | 39 |
| Malcolm Turnbull | 114 |
| Scott Morrison | 284 |
| **Anthony Albanese** | **242** |

Total: 1,786 in-scope rows (1,836 total snapshot rows, minus 47 rows in
the five "requires verification" series, minus 3 CSES rows).

## Approved-source domains relevant to Australia's existing data

Derived by matching each Source-column URL's hostname in the Australia
snapshot against `config/allowed_domains.txt` (that file's own header
documents its rule: every domain tied to a Master data point dated
2024-01-01 or later was approved; nothing older was auto-approved).

**Already approved** (present in `config/allowed_domains.txt` today):
`pollbludger.net`, `morningconsult.com`, `pro.morningconsult.com`,
`ipsos.com`, `docs.google.com`, `drive.google.com`, `archive.ph`,
`statista.com`.

**Seen in Australia's historical data but NOT currently approved**
(their observations pre-date the 2024-01-01 cutoff, so no fetch from
them was ever approved — do not fetch these domains for new research
without explicit new approval, even though the historical data point
already sitting in the snapshot is fine to reference as existing data):
`roymorgan.com`, `essentialvision.com.au`, `essentialreport.com.au`,
`theage.com.au`, `theguardian.com`, `angus-reid.com`,
`analyticscampus.gallup.com` / `analyticscampus-gallup-com.proxyiub.uits.iu.edu`,
`newspoll.com.au`, `polling.newspoll.com.au.tmp.anchor.net.au`.

## Cautions — inferred vs. established meaning

- **EAD wording/description is the authority where populated** (per
  `CLAUDE.md`), but several rows have it only partially populated
  (`MorningConsult` has no wording text; `IPSOS`'s wording field is a
  generic placeholder, "Question of Satisfaction," not the actual
  question) — the Description field, not the Question Wording field, is
  what establishes PM-target confidence for those two.
- **`MorningConsult`, `GALLUPWORLD_LSHP`, `GALLUPWORLD_LDR`** are
  international multi-country tracking programs, same caution Canada's
  own profile applies: what exactly is asked of Australian respondents
  within the program is not independently verifiable from this
  reference material alone.
- **Single-record series** (`GALLUPWORLD_LDR`, `FOX&HEDGEHOG`) have
  essentially no in-snapshot context to corroborate any inference.
- **This profile reflects the snapshot/EAD workbook as inspected on
  2026-08-25.** It has not been cross-checked against every individual
  source URL, and the "requires verification" rows above are exactly
  that — starting points for a human/research pass, not settled
  classifications.
- **The PM officeholder timeline determines leader assignment, never
  series recency.** A row's Date must be compared against the table
  above; do not infer "this looks like a recent series so it must be
  Albanese."
- **Only the Morrison -> Albanese transition (2022-05-23) is VERIFIED**
  (as of 2026-08-25, via `pm.gov.au`, actually retrieved and directly
  quoted). Every other date in the officeholder timeline — including
  Scott Morrison's own start date and every earlier PM — remains
  UNVERIFIED: repeated attempts to confirm them from authoritative
  Australian government sources failed for environmental reasons (see
  the timeline section's attempt log), not because the dates were found
  to be wrong. Do not describe any row other than the Morrison ->
  Albanese boundary as "verified" until an authoritative
  government/parliamentary source is actually retrieved and inspected
  for it specifically.
