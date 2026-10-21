# Canada Reference Profile

**Status:** Read-only reconnaissance profile. Compiled from the existing
master workbook / derived reference index only. No web research was
performed to produce this file.

**Country field value in workbook:** `Canada` (exact spelling as stored)

**Source of this analysis:**
- Master workbook: `data/master/pollitik_master.xlsx`
- Derived index: `data/reference_index.duckdb`
- Snapshot basis: index build timestamp 2026-08-13T15:00:57Z

**Totals:** 30 unique `Series` values, 1,444 Canada records, dates
spanning 1957-09-15 to 2026-02-28 (~68 years).

## Naming conventions observed

These are patterns inferred from the series names and their date ranges
in-workbook, not documentation found elsewhere:

- `PM` suffix — series appears to target the Prime Minister specifically
  (e.g. `ABACUSJOBPM`, `EKOSPM`, `FORUMPM`).
- `GOV` suffix — series appears to target the Government generally,
  rather than the PM individually (e.g. `DecimaGOV`, `EnvironicsGOV`,
  `ANGUSREIDGOV`).
- `FAV` — favorability framing, distinct from approval/job framing
  (e.g. `ANGUSREIDFAV`).
- `IMPRESSION` — personal impression framing, distinct from job
  approval (e.g. `ABACUSIMPRESSIONPM`).
- Plain pollster name with no suffix (e.g. `ANGUSREID`, `IPSOS`,
  `LEGER`, `NANOS`) — target (PM vs. government) is not distinguishable
  from the series name alone; see cautions below.
- Records generally carry a sentiment-style breakdown (Positive /
  Neutral / Negative), consistent across series, which is the basis for
  reading these as approval/favorability measures rather than
  vote-intention or other series types.

## Series table

| Series | Earliest | Latest | Records | What it appears to measure (workbook evidence) |
|---|---|---|---|---|
| ABACUSIMPRESSIONPM | 2014-03-15 | 2026-02-10 | 165 | PM personal impression/favorability (Abacus Data) — source URLs reference "personal numbers"; Pos/Neutral/Neg structure |
| ABACUSJOBPM | 2015-01-15 | 2026-02-26 | 142 | PM job approval (Abacus Data) — "JOB" in series name |
| ANGUSREID | 1991-01-24 | 2026-01-26 | 131 | PM/Government approval (Angus Reid) — longest-running series, 35 years |
| ANGUSREIDFAV | 2021-01-27 | 2024-04-15 | 16 | PM favorability (Angus Reid) — concentrated around 2021/2024 election periods |
| ANGUSREIDGOV | 1994-03-22 | 1995-09-01 | 4 | Government approval (Angus Reid, 1990s) — "GOV" suffix |
| CAMPAIGNRESEARCHPM | 2017-02-06 | 2019-10-10 | 25 | PM approval/support during election campaigns (Campaign Research Group) — confined to 2017-2019 election window |
| CSES | 1997-02-15 | 2019-11-21 | 4 | Canadian Election Study survey data — academic election survey (modern cycles) |
| CanadianElectionStudy | 1972-07-15 | 1972-09-15 | 2 | Canadian Election Study survey data — historical 1972 election data point |
| CultMTL | 2025-12-23 | 2025-12-23 | 1 | Single 2025 data point; source not resolvable from index alone |
| DecimaGOV | 1980-09-15 | 1995-03-15 | 56 | Government approval ratings (Decima Research) — "GOV" suffix, 15-year historical series |
| EKOSPM | 2009-01-17 | 2026-01-14 | 49 | PM approval tracking (EKOS Research) — long-running contemporary series |
| EnvironicsGOV | 1978-06-15 | 2009-09-15 | 122 | Government approval ratings (Environics Research) — earliest "GOV" series in the set |
| EnvironicsPM | 1985-11-15 | 2009-03-15 | 83 | PM approval/favorability ratings (Environics Research) |
| FORUMPM | 2013-04-15 | 2019-10-16 | 76 | PM approval ratings (Forum Research) — concentrated 2015-2019 |
| GALLUPCANADA | 1957-09-15 | 2000-12-15 | 109 | Canadian PM/leadership approval (Gallup) — **earliest data in the whole Canada set** |
| GALLUPWORLD_LDR | 2025-06-30 | 2025-06-30 | 1 | Global Gallup leadership favorability database — single 2025 data point for Canada |
| GALLUPWORLD_LSHP | 2007-09-15 | 2025-06-20 | 19 | Global Gallup leadership favorability scores — international dataset |
| INSIGHTSWESTPM | 2017-10-26 | 2017-10-26 | 1 | PM approval/polling data (InsightsWest Research) — single 2017 data point |
| IPSOS | 1994-02-15 | 2025-09-08 | 81 | PM/Government approval ratings (Ipsos) — long-running commercial pollster |
| LAPOP | 2010-05-11 | 2021-07-07 | 6 | Latin American Public Opinion Project — Canada component of a regional survey project |
| LEGER | 2004-11-14 | 2025-09-15 | 21 | PM approval/favorability (Leger Research) |
| LIAISON | 2025-05-08 | 2026-02-28 | 27 | PM approval ratings (Liaison Research) — most recent/ongoing series |
| MAINSTREETPM | 2016-10-06 | 2017-08-31 | 7 | PM approval ratings (Mainstreet Research) — campaign-period polling |
| MorningConsult | 2019-08-11 | 2026-01-04 | 253 | **Largest series** — frequent PM approval tracking (Morning Consult), global leader approval database |
| NANOS | 2008-06-15 | 2017-06-15 | 10 | PM approval tracking (Nanos Research) — daily tracker series |
| RESEARCHCO | 2019-07-17 | 2025-07-02 | 11 | PM approval/favorability (ResearchCo) |
| SESSUN | 2004-01-29 | 2005-02-02 | 5 | PM approval polling — small historical series |
| STRATCOUN | 2006-04-09 | 2006-09-17 | 3 | Strategic polling data — small 2006 series |
| SparkInsights | 2025-06-17 | 2026-01-18 | 12 | PM approval tracking (Spark Insights) |
| ZOGBY | 2004-05-07 | 2005-05-15 | 2 | PM approval (Zogby International) — small historical series |

## Cautions — inferred vs. established meaning

- **"What it measures" is inferred, not documented.** These
  interpretations come from series-name suffixes (`PM`/`GOV`/`FAV`/
  `IMPRESSION`), date clustering (e.g. around election periods), and
  incidental source-URL wording spotted in the index (e.g. Abacus
  "personal numbers"). No codebook or field explicitly states the
  target or question wording for any series.
- **Plain-name series (`ANGUSREID`, `IPSOS`, `LEGER`, `NANOS`, `LAPOP`,
  `CSES`, `CanadianElectionStudy`, `SESSUN`, `STRATCOUN`, `ZOGBY`,
  `CultMTL`, `INSIGHTSWESTPM` excepted) do not encode PM-vs-Government
  target in the name itself** — labeling them "PM/Government approval"
  above is a best-effort read, not a confirmed classification.
- **Single-record series** (`CultMTL`, `GALLUPWORLD_LDR`,
  `INSIGHTSWESTPM`) have essentially no in-workbook context to
  corroborate the inference — treat these as the least confident rows
  in the table.
- **`GALLUPWORLD_LDR` / `GALLUPWORLD_LSHP` / `LAPOP`** are
  international/regional survey programs where the Canada row is one
  slice of a larger multi-country dataset; what exactly is asked of
  Canadian respondents within that program is not verifiable from this
  index alone.
- **Sentiment-structure basis (Positive/Neutral/Negative) was observed
  across series** and used to support "approval/favorability" as the
  general category, but this does not confirm exact question wording
  or scale per series.
- This profile reflects the index as of the build timestamp noted
  above. It has not been re-verified against source URLs or
  cross-checked with any external documentation, and should be treated
  as a starting point for matching/classification, not ground truth.
