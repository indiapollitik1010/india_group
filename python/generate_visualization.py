#!/usr/bin/env python3
"""Pollitik automated visualization generator (Skill: visualization_rules).

Reads a Pollitik "visualization-ready" CSV (the kind produced downstream
of the staging/validation pipeline, columns: Date, Approval, Prime
Minister, Party, Series, Source, Status) and config/visualization_rules.yaml,
then runs one of two modes:

  --graph not supplied  -> RECOMMEND mode (also the default with no flags,
                            and what --recommend explicitly requests): rank
                            up to `recommendation.max_recommendations`
                            eligible approved graph types with a one-line
                            reason each, print them, and stop. No file is
                            written.
  --graph <type> supplied -> the student's choice. The type is checked for
                            eligibility against this data's shape (never
                            just accepted blindly), then rendered
                            automatically with full Pollitik styling - the
                            student sets no axes/colors/legend/formatting.
  --select-option N       -> same as --graph, but the type is resolved
                            deterministically from a prior RECOMMEND run's
                            saved state (--state-file) instead of being
                            named directly - the "generate graph option N"
                            follow-up. Requires --state-file.
  --reply TEXT            -> same idea as --select-option, but resolves a
                            student's free-text reply (an option number, a
                            graph name, an unambiguous natural description,
                            or "all <count>") against the saved state via
                            resolve_student_choice() below, instead of
                            requiring the internal graph type id. An
                            unresolved/ambiguous reply prints a short,
                            human-readable clarification (never an internal
                            graph type id) and generates nothing. Requires
                            --state-file.

The student never gets a chart forced on them, and never hand-configures
one either: Codex ranks, the student names one type (by type or by ranked
option number), Codex builds it.

  --resolve-request TEXT  -> a separate, earlier-stage entry point for the
                            student's very first free-text graph request,
                            before any recommendation has been shown (so
                            there is no --state-file yet for
                            resolve_student_choice() to resolve against).
                            Classifies TEXT via resolve_request() into one
                            of: recommend, approval_over_time,
                            series_spread, snapshot_comparison,
                            leader_comparison_grid, all, or
                            unsupported:<key> - prints that token (and,
                            for an unsupported:<key> result only, a
                            second line with a short, student-friendly
                            reason) and exits; nothing else is read or
                            generated. Codex must call this before
                            deciding whether to run recommend mode or
                            generate a chart directly, rather than judging
                            "vague vs specific" itself - a vague request
                            always resolves to "recommend", and a request
                            naming an analytically inappropriate chart
                            form (pie chart, donut chart, word cloud)
                            resolves to "unsupported:<key>" rather than
                            being generated or silently redirected.

RECOMMEND mode also accepts --state-file: if given, the ranked
recommendation list is persisted to that local JSON path so a later,
separate invocation can resolve "option N" deterministically (see
resolve_option()/write_recommendation_state() below) rather than relying
on conversation memory. This script never chooses that path itself - the
caller decides where it lives and must keep it out of version control.

This script never reads or writes the production workbook, the staging
file, or any file under data/master/ - it only knows about whatever CSV
path is passed via --input and whatever HTML/PNG path is passed via
--output. It has no dependency on python/pollitik_common.py on purpose,
so it cannot accidentally resolve a production path.

Data-quality rules enforced here (see docs/visualization_rules.md):
  - only rows with Status == "APPROVED" are ever plotted; REVIEW/REJECTED
    rows are counted and reported, never rendered.
  - never invents a missing value - a required column or a required
    per-row field that is missing causes a clear, controlled failure
    (VisualizationDataError -> non-zero exit, no traceback), not a
    guess and not a silent skip.

Charting is done with hand-written, dependency-free inline SVG (no
matplotlib/plotly in this project's requirements.txt) so the HTML output
is fully self-contained and needs nothing installed beyond this repo's
existing pandas/PyYAML dependencies. PNG export is attempted only if a
suitable SVG rasterizer (e.g. cairosvg) is importable in the current
environment; otherwise it is skipped with a clear, reported reason
rather than failing the whole run or silently doing nothing.
"""

import argparse
import csv
import datetime
import html
import json
import os
import re
import statistics
import sys
from collections import OrderedDict, defaultdict

import yaml

REQUIRED_COLUMNS = ["Date", "Approval", "Prime Minister", "Party", "Series", "Source", "Status"]
ROW_PLOT_FIELDS = ("Date", "Approval", "Prime Minister", "Series")
APPROVED_STATUS = "APPROVED"

DEFAULT_CONFIG_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "visualization_rules.yaml")
)

# Confirmed Pollitik brand colors (config/visualization_rules.yaml ->
# style.brand_colors). #FBFBF2 is the page/plot background, not usable
# as a mark color against itself, so only 3 of the 4 are usable as point
# colors. A dataset with more than 3 Series needs colors beyond the
# confirmed brand set; FALLBACK_MARK_COLORS below are clearly-flagged
# non-brand extensions used only when the brand set runs out, pending a
# real extended-palette decision from the project owner.
BRAND_MARK_COLORS = ["#FFB400", "#00A6ED", "#F6511D"]
FALLBACK_MARK_COLORS = ["#5C4B8A", "#2E2E2E", "#1F7A4C", "#B23A6E", "#6B4A2A"]
TREND_LINE_COLOR = "#333333"
# Deliberately thin + translucent relative to the point marks (stroke-width
# 4.5 circles): the trend line is a secondary read, individual polls are
# the primary evidence. See render_approval_over_time.
TREND_LINE_STROKE_WIDTH = 1.5
TREND_LINE_OPACITY = 0.55
GRID_COLOR = "#E4E4DA"
AXIS_TEXT_COLOR = "#3A3A34"
BACKGROUND_COLOR = "#FBFBF2"

# Series with this many or fewer APPROVED observations get a reader-facing
# caution note on the Series Spread chart (see render_series_spread): a
# 1-2 point series can't show a real distribution or a stable house
# effect, and this chart's uneven per-Series counts (e.g. a 1-poll firm
# next to a 16-poll firm) make that easy to misread at a glance.
SPARSE_SERIES_MAX_OBSERVATIONS = 4


class VisualizationDataError(Exception):
    """A clearly-reportable data/config/schema problem. Always caught in
    main() and printed as a single clean error line - never an unhandled
    traceback, and never a silent guess."""


# --------------------------------------------------------------------
# Loading + validation
# --------------------------------------------------------------------

def load_config(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except OSError as exc:
        raise VisualizationDataError("Could not read config file '{}': {}".format(path, exc))

    if not isinstance(config, dict):
        raise VisualizationDataError("Config file '{}' did not parse to a mapping.".format(path))

    for key in ("graph_types", "recommendation", "style", "data_quality"):
        if key not in config:
            raise VisualizationDataError(
                "Config file '{}' is missing required top-level key '{}'.".format(path, key)
            )
    return config


def load_csv_rows(path):
    if not os.path.exists(path):
        raise VisualizationDataError("Input CSV '{}' does not exist.".format(path))
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        missing = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
        if missing:
            raise VisualizationDataError(
                "Input CSV '{}' is missing required column(s): {}. Expected columns: {}.".format(
                    path, ", ".join(missing), ", ".join(REQUIRED_COLUMNS)
                )
            )
        rows = list(reader)
    if not rows:
        raise VisualizationDataError("Input CSV '{}' has no data rows.".format(path))
    return rows


def filter_approved(rows):
    """Never plot REVIEW/REJECTED - split and count instead of dropping
    silently, so the caller can report what was excluded and why."""
    approved = []
    excluded = defaultdict(int)
    for row in rows:
        status = (row.get("Status") or "").strip()
        if status == APPROVED_STATUS:
            approved.append(row)
        else:
            excluded[status or "(blank)"] += 1
    if not approved:
        raise VisualizationDataError(
            "No rows with Status == 'APPROVED' were found - nothing eligible to plot. "
            "REVIEW/REJECTED rows are never plotted, per Pollitik data-quality rules."
        )
    return approved, dict(excluded)


def validate_row_fields(rows, required=ROW_PLOT_FIELDS):
    """Fail clearly (not a guess, not a silent skip, not a bare
    traceback) if an APPROVED row lacks a field needed to plot it."""
    problems = []
    for i, row in enumerate(rows):
        for field in required:
            if not (row.get(field) or "").strip():
                problems.append("row {} (1-indexed data row): missing '{}'".format(i + 1, field))
    if problems:
        raise VisualizationDataError(
            "APPROVED row(s) are missing required field(s) needed to plot - refusing to "
            "invent a value:\n  " + "\n  ".join(problems)
        )


def parse_date(value):
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise VisualizationDataError(
        "Could not parse date '{}' (expected M/D/YYYY or YYYY-MM-DD).".format(value)
    )


def parse_approval(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        raise VisualizationDataError("Could not parse Approval value '{}' as a number.".format(value))


def format_date_readable(d):
    """Native, reader-facing date format (e.g. 'Aug 7, 2026') - never a
    raw serial/ISO string on a visible chart. Windows' strftime has no
    '%-d' (no leading-zero day); '%#d' is the Windows equivalent."""
    return d.strftime("%b %-d, %Y") if os.name != "nt" else d.strftime("%b %#d, %Y")


# --------------------------------------------------------------------
# Graph-type eligibility + ranked recommendation (config-driven).
#
# Codex never forces a single chart: this section answers "which of the
# 4 approved types could honestly be built from this data" (eligibility)
# and "which up-to-3 of those should be suggested, in what order, with
# what one-line reason" (recommendation). The student's own --graph
# choice is checked with the same eligibility function, so a choice that
# isn't appropriate for the data fails with the same reason a
# recommendation would have excluded it for.
# --------------------------------------------------------------------

DISPLAY_NAMES = {
    "approval_over_time": "Approval Over Time",
    "leader_comparison_grid": "Leader Comparison Grid",
    "snapshot_comparison": "Snapshot Comparison",
    "series_spread": "Series Spread",
}


def compute_data_shape(rows):
    executives = sorted({
        (r.get("Prime Minister") or "").strip()
        for r in rows if (r.get("Prime Minister") or "").strip()
    })
    dates = {(r.get("Date") or "").strip() for r in rows if (r.get("Date") or "").strip()}
    series = sorted({
        (r.get("Series") or "").strip()
        for r in rows if (r.get("Series") or "").strip()
    })
    return {"executives": executives, "dates": dates, "series": series, "n": len(rows)}


def graph_eligibility(graph_type, shape, config):
    """Returns (eligible: bool, reason_if_not: str|None). `reason_if_not`
    is always a plain sentence naming the actual vs. required numbers -
    never a bare true/false the caller has to re-explain."""
    graph_types = config["graph_types"]
    if graph_type not in graph_types:
        return False, "'{}' is not one of the approved graph types ({}).".format(
            graph_type, ", ".join(sorted(graph_types))
        )
    requires = graph_types[graph_type].get("requires") or {}

    if graph_type == "leader_comparison_grid":
        needed = requires.get("executives_min", 2)
        n_exec = len(shape["executives"])
        if n_exec >= needed:
            return True, None
        return False, "only {} executive(s) present (needs >= {}).".format(n_exec, needed)

    if graph_type == "approval_over_time":
        needed_execs = requires.get("executives", 1)
        min_obs = requires.get("min_observations", 8)
        min_dates = requires.get("min_distinct_dates", 2)
        problems = []
        if len(shape["executives"]) != needed_execs:
            problems.append(
                "expects exactly {} executive(s), found {}".format(needed_execs, len(shape["executives"]))
            )
        if shape["n"] < min_obs:
            problems.append("needs >= {} observations, found {}".format(min_obs, shape["n"]))
        if len(shape["dates"]) < min_dates:
            problems.append("needs >= {} distinct dates, found {}".format(min_dates, len(shape["dates"])))
        if problems:
            return False, "; ".join(problems) + "."
        return True, None

    if graph_type in ("series_spread", "snapshot_comparison"):
        min_series = requires.get("min_series", 2)
        n_series = len(shape["series"])
        if n_series >= min_series:
            return True, None
        return False, "only {} polling Series present (needs >= {}).".format(n_series, min_series)

    return False, "no eligibility rule is defined for '{}'.".format(graph_type)


def recommend_graphs(rows, config):
    """Ranked, capped list of eligible graph types with reasons. Always
    computed from `rows` as given - callers must pass APPROVED-only rows
    so REVIEW/REJECTED can never influence the ranking."""
    shape = compute_data_shape(rows)
    rec_config = config.get("recommendation", {})
    priority = rec_config.get("priority_order") or list(config["graph_types"])
    max_recs = rec_config.get("max_recommendations", 3)
    reason_templates = rec_config.get("reasons", {})
    executive = shape["executives"][0] if len(shape["executives"]) == 1 else "this executive"

    recommendations = []
    for graph_type in priority:
        eligible, _ = graph_eligibility(graph_type, shape, config)
        if not eligible:
            continue
        reason = reason_templates.get(graph_type, "").format(executive=executive)
        recommendations.append({"graph_type": graph_type, "reason": reason})
        if len(recommendations) >= max_recs:
            break
    return recommendations, shape


def format_recommendation_text(recommendations, approved_count, excluded, shape):
    excluded_total = sum(excluded.values())
    lines = [
        "Recommended Pollitik visualizations for this dataset "
        "({} APPROVED observations; {} REVIEW/REJECTED excluded):".format(
            approved_count, excluded_total
        ),
        "",
    ]
    if not recommendations:
        lines.append(
            "No approved graph type is eligible for this data shape "
            "(executives={}, observations={}, distinct dates={}, distinct series={}).".format(
                len(shape["executives"]), shape["n"], len(shape["dates"]), len(shape["series"])
            )
        )
        return "\n".join(lines)

    for i, rec in enumerate(recommendations, start=1):
        label = DISPLAY_NAMES.get(rec["graph_type"], rec["graph_type"])
        # ASCII "-" on purpose (not an em-dash): this string is printed
        # straight to the console, and a Windows terminal without UTF-8
        # configured can mangle/replace non-ASCII characters here.
        suffix = " - recommended" if i == 1 else ""
        lines.append("{}. {}{}".format(i, label, suffix))
        lines.append("   {}".format(rec["reason"]))
        lines.append("")

    lines.append(_reply_instructions_sentence(recommendations))
    lines.append("")
    lines.append(
        "Codex applies all Pollitik styling automatically once you choose - "
        "you do not set axes, colors, legends, or formatting yourself."
    )
    return "\n".join(lines)


# --------------------------------------------------------------------
# Student reply resolution — a vague/ambiguous recommend-mode reply from
# a student ("1", "Approval Over Time", "make the trend graph", "all
# three", ...) is resolved deterministically against the just-shown
# ranked list, never guessed by the model and never requiring the
# internal graph_type id (approval_over_time/series_spread/
# snapshot_comparison/leader_comparison_grid) the student was never
# shown. Mirrors resolve_option()'s "deterministic, not inferred"
# contract, but for free text instead of a bare option number.
# --------------------------------------------------------------------

_COUNT_WORDS = {1: "one", 2: "two", 3: "three", 4: "four"}

# Order matters only in that each graph type's keywords are checked
# independently - a reply matching exactly one recommended type's
# keywords resolves; matching more than one (or none) is ambiguous.
GRAPH_TYPE_KEYWORDS = OrderedDict([
    ("approval_over_time", ("trend", "over time")),
    ("series_spread", ("spread", "dispersion", "house effect")),
    ("snapshot_comparison", ("comparison", "compare", "snapshot", "latest")),
])

_ALL_REPLY_WORDS = ("all", "all of them", "everything", "all of these")


def _count_word(n):
    return _COUNT_WORDS.get(n, str(n))


def _reply_instructions_sentence(recommendations):
    """The one line telling a student how they may answer a ranked list -
    numbers, the graph name, or a natural description; internal graph
    type ids are never mentioned."""
    option_numbers = ", ".join(str(i) for i in range(1, len(recommendations) + 1))
    items = [option_numbers, "the graph name", "a natural description"]
    if len(recommendations) > 1:
        items.append("'all {}'".format(_count_word(len(recommendations))))
    if len(items) == 1:
        return "You can reply with {}.".format(items[0])
    return "You can reply with {}, or {}.".format(", ".join(items[:-1]), items[-1])


def format_student_options(recommendations):
    """Short, standalone student-facing options list ('I can create: 1.
    ... 2. ... You can reply with ...'), independent of the fuller
    format_recommendation_text() report. Never mentions an internal
    graph_type id."""
    if not recommendations:
        return "No eligible graph options are available for this dataset yet."
    lines = ["I can create:", ""]
    for i, rec in enumerate(recommendations, start=1):
        label = DISPLAY_NAMES.get(rec["graph_type"], rec["graph_type"])
        lines.append("{}. {} - {}".format(i, label, rec["reason"]))
    lines.append("")
    lines.append(_reply_instructions_sentence(recommendations))
    return "\n".join(lines)


def resolve_student_choice(reply, recommendations):
    """Deterministically resolve a student's free-text reply to a
    recommend-mode ranked list (the same list format
    write_recommendation_state() persists: [{"option", "graph_type",
    "reason"}, ...]) onto one or more of that list's graph types.

    Returns (graph_types, clarification):
      - a resolved single choice or "all <count>" -> (list_of_graph_types, None)
      - unresolved/ambiguous/out-of-range           -> (None, clarification_text)

    clarification_text is always the same human-readable, numbered
    options a student was already shown - never an internal graph_type
    id - so a caller can print it straight back to the student instead
    of guessing.
    """
    if not recommendations:
        return None, format_student_options(recommendations)

    text = (reply or "").strip().lower()
    if not text:
        return None, format_student_options(recommendations)

    by_type = OrderedDict((r["graph_type"], r) for r in recommendations)
    display_by_type = {gt: DISPLAY_NAMES.get(gt, gt) for gt in by_type}

    if text in _ALL_REPLY_WORDS or re.fullmatch(r"all\s+(?:\d+|one|two|three|four)", text):
        return [r["graph_type"] for r in recommendations], None

    option_match = re.fullmatch(r"(?:option\s*#?|#)?\s*(\d+)", text)
    if option_match:
        n = int(option_match.group(1))
        if 1 <= n <= len(recommendations):
            return [recommendations[n - 1]["graph_type"]], None
        return None, format_student_options(recommendations)

    for graph_type, label in display_by_type.items():
        if text == label.lower():
            return [graph_type], None

    normalized = text.replace(" ", "_")
    if normalized in by_type:
        return [by_type[normalized]["graph_type"]], None

    matched = [
        graph_type for graph_type, keywords in GRAPH_TYPE_KEYWORDS.items()
        if graph_type in by_type and any(keyword in text for keyword in keywords)
    ]
    if len(matched) == 1:
        return matched, None

    return None, format_student_options(recommendations)


# --------------------------------------------------------------------
# Initial-request routing — a student's very first free-text graph
# request ("Generate a graph of the Canada results.", "Make the trend
# graph.", "Compare these leaders.", ...) arrives before any
# recommendation has been shown, so there is no saved state for
# resolve_student_choice() to resolve against yet. Codex must not decide
# "vague vs specific" itself by reading prose - resolve_request() below
# is the single deterministic entry point for that decision.
#
# 2026-08-25: a flat "compare"/"comparison" keyword used to route to
# snapshot_comparison unconditionally (see GRAPH_TYPE_KEYWORDS above,
# still used unchanged by resolve_student_choice() for replies to an
# already-shown, already-eligible list). That conflated two structurally
# different comparisons this project actually has - comparing
# executives (leader_comparison_grid) vs. comparing polling Series
# (series_spread/snapshot_comparison) - so "Compare these leaders."
# could resolve to a pollster chart. resolve_request() now checks the
# comparison *subject* (leader vs. pollster wording) before falling back
# to the flat keyword table, entirely separately from
# resolve_student_choice()'s existing, unmodified behavior.
#
# A request naming no specific graph type (or naming more than one,
# ambiguously) always resolves to "recommend" - Codex must show the
# ranked options and stop, never guess a chart just because one type
# happens to rank first.
# --------------------------------------------------------------------

_ALL_REQUEST_PATTERN = re.compile(r"\ball\b")

# Comparison-subject wording, checked only by resolve_request()'s
# *initial* free-text classification (never by resolve_student_choice(),
# which matches a reply against an already-narrowed, already-eligible
# list via GRAPH_TYPE_KEYWORDS above and needs no subject disambiguation
# - there's rarely more than one plausible pollster-comparison option
# left in that shown list). leader_comparison_grid is the only
# leader-comparison family that exists, so any leader-subject wording -
# with or without "over time" also present - resolves to it; the
# eligibility check downstream (graph_eligibility) is what actually
# decides whether it's usable for this data (e.g. only 1 executive
# present), not this routing step.
_LEADER_SUBJECT_WORDS = ("leader", "leaders", "candidate", "candidates")
_POLLSTER_SUBJECT_WORDS = (
    "pollster", "pollsters", "polling firm", "polling firms",
    "polling-firm", "polling-firms", "firm", "firms",
)

# Keyword fallback for resolve_request() once subject-based routing
# doesn't apply - deliberately narrower than GRAPH_TYPE_KEYWORDS above:
# it omits the bare "comparison"/"compare" keywords (that's exactly the
# ambiguous case the subject check above exists to resolve) and keeps
# only the keywords that already name one specific, unambiguous chart
# concept on their own.
_INITIAL_REQUEST_KEYWORDS = OrderedDict([
    ("approval_over_time", ("trend", "over time")),
    ("series_spread", ("spread", "dispersion", "house effect")),
    ("snapshot_comparison", ("snapshot", "latest")),
])

# Chart forms that are never analytically appropriate for Pollitik's
# approval-polling time-series data, regardless of what the data
# actually contains - explained plainly and refused, never silently
# generated and never silently redirected to a recommendation with no
# acknowledgment of what was actually asked for. Keys are internal
# identifiers only (never shown to a student as-is; see
# format_unsupported_graph_message()). Checked before every other
# routing rule, since an inappropriate chart-form request should be
# refused even if it also happens to contain "all" or a subject word.
UNSUPPORTED_GRAPH_FORMS = OrderedDict([
    ("pie_chart", {
        "phrases": ("pie chart", "pie graph"),
        "display_name": "pie chart",
        "reason": "these are repeated approval observations over time, not parts of one total",
    }),
    ("donut_chart", {
        "phrases": ("donut chart", "doughnut chart"),
        "display_name": "donut chart",
        "reason": "these are repeated approval observations over time, not parts of one total",
    }),
    ("word_cloud", {
        "phrases": ("word cloud",),
        "display_name": "word cloud",
        "reason": "these are numeric approval percentages over time, not text to count",
    }),
])


def _match_unsupported_graph_form(normalized):
    for key, spec in UNSUPPORTED_GRAPH_FORMS.items():
        if any(phrase in normalized for phrase in spec["phrases"]):
            return key
    return None


def format_unsupported_graph_message(key):
    """Short, student-friendly, data-grounded explanation for why a
    named chart form was declined - never a bare refusal. Ends by
    pointing at the recommendation step (a separate invocation, same
    pattern as every other resolve_request() outcome) rather than
    listing eligible types itself, since this function never reads the
    student's actual data."""
    spec = UNSUPPORTED_GRAPH_FORMS[key]
    return (
        "A {name} is not appropriate for these approval observations because "
        "{reason}. Here are the graph types that fit your validated data instead:"
    ).format(name=spec["display_name"], reason=spec["reason"])


def resolve_request(text):
    """Deterministically classify a student's initial free-text graph
    request into exactly one of: "recommend", "approval_over_time",
    "series_spread", "snapshot_comparison", "leader_comparison_grid",
    "all", or "unsupported:<key>". Pure text classification - no
    CSV/config/state file is read, so this can run before anything else
    in the workflow. Returns "recommend" for any empty, vague, or
    ambiguous (matches more than one graph concept) request - the safe
    default that shows options instead of guessing.
    """
    normalized = (text or "").strip().lower()
    if not normalized:
        return "recommend"

    unsupported_key = _match_unsupported_graph_form(normalized)
    if unsupported_key:
        return "unsupported:{}".format(unsupported_key)

    if _ALL_REQUEST_PATTERN.search(normalized):
        return "all"

    if any(word in normalized for word in _LEADER_SUBJECT_WORDS):
        return "leader_comparison_grid"

    if any(word in normalized for word in _POLLSTER_SUBJECT_WORDS):
        if "latest" in normalized or "snapshot" in normalized:
            return "snapshot_comparison"
        if any(w in normalized for w in ("compare", "comparison", "spread", "dispersion", "house effect")):
            return "series_spread"

    matched = [
        graph_type for graph_type, keywords in _INITIAL_REQUEST_KEYWORDS.items()
        if any(keyword in normalized for keyword in keywords)
    ]
    if len(matched) == 1:
        return matched[0]
    return "recommend"


# --------------------------------------------------------------------
# Deterministic pooled trend (documented rolling method, no ML/LOESS)
# --------------------------------------------------------------------

def compute_rolling_trend(points, window_days, min_points_required=1):
    """points: list of (date, approval) tuples, any order, pooled across
    every Series. For each unique date present in the data, the trend
    value is the mean Approval of every point (any series) whose date
    falls within window_days/2 of that date - a centered, time-based
    rolling average. Deterministic, no fitted model, no hidden
    parameters: window_days is the only knob and it comes straight from
    config/visualization_rules.yaml.
    """
    if len(points) < min_points_required:
        return []
    sorted_points = sorted(points, key=lambda p: p[0])
    half = datetime.timedelta(days=window_days / 2.0)
    trend = OrderedDict()
    unique_dates = sorted({d for d, _ in sorted_points})
    for d in unique_dates:
        window_vals = [a for (pd, a) in sorted_points if abs(pd - d) <= half]
        trend[d] = statistics.mean(window_vals)
    return list(trend.items())


def split_trend_segments(trend_points, max_gap_days):
    """trend_points: (date, value) pairs, one per unique observation
    date, sorted ascending (as returned by compute_rolling_trend).

    Splits into a list of segments so the trend line is never drawn -
    never interpolated - across a gap of more than max_gap_days between
    two consecutive trend-supporting dates. A long silence in the
    polling data stays a visible gap in the line, not a smoothed-over
    guess. A segment of a single point produces no visible line (a lone
    point can't imply a trend on its own).
    """
    if not trend_points:
        return []
    segments = [[trend_points[0]]]
    for prev, curr in zip(trend_points, trend_points[1:]):
        gap_days = (curr[0] - prev[0]).days
        if gap_days > max_gap_days:
            segments.append([])
        segments[-1].append(curr)
    return segments


# --------------------------------------------------------------------
# Color assignment
# --------------------------------------------------------------------

def assign_series_colors(series_names):
    """Fixed categorical order (alphabetical, so it's stable across runs
    and across future countries) - identity, not rank-based, and never
    cycled: brand colors first, then clearly-flagged fallback colors."""
    palette = BRAND_MARK_COLORS + FALLBACK_MARK_COLORS
    ordered = sorted(set(series_names))
    if len(ordered) > len(palette):
        raise VisualizationDataError(
            "{} distinct Series values but only {} mark colors (brand + fallback) are "
            "defined - add more fallback colors before plotting this many series.".format(
                len(ordered), len(palette)
            )
        )
    return OrderedDict((name, palette[i]) for i, name in enumerate(ordered))


# --------------------------------------------------------------------
# SVG/HTML rendering helpers
# --------------------------------------------------------------------

def _svg_escape(text):
    return html.escape(str(text), quote=True)


def _html_shell(title, body, footer_note, meta_tags=None):
    """meta_tags: optional {name: content} dict rendered as <meta> tags -
    for methodology/provenance detail that belongs in the document's
    metadata rather than the visible, reader-facing footer text."""
    meta_html = "".join(
        '<meta name="{}" content="{}">\n'.format(_svg_escape(k), _svg_escape(v))
        for k, v in (meta_tags or {}).items()
    )
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
{meta}<style>
  body {{ background: {bg}; color: {axis}; font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 24px; }}
  .pollitik-chart-wrap {{ max-width: 960px; margin: 0 auto; }}
  h1 {{ font-size: 1.25rem; margin: 0 0 4px 0; }}
  .pollitik-footer {{ font-size: 0.75rem; color: {axis}; opacity: 0.85; margin-top: 10px; line-height: 1.4; }}
  .pollitik-legend {{ display: flex; flex-wrap: wrap; gap: 14px; justify-content: center; margin-top: 8px; font-size: 0.8rem; }}
  .pollitik-legend-item {{ display: flex; align-items: center; gap: 6px; }}
  .swatch {{ width: 12px; height: 12px; border-radius: 3px; display: inline-block; }}
  .swatch-line {{ width: 16px; height: 3px; border-radius: 2px; display: inline-block; }}
</style>
</head>
<body>
<div class="pollitik-chart-wrap">
{body}
<div class="pollitik-footer">{footer}</div>
</div>
</body>
</html>
""".format(
        title=_svg_escape(title), meta=meta_html, bg=BACKGROUND_COLOR, axis=AXIS_TEXT_COLOR,
        body=body, footer=footer_note
    )


def render_approval_over_time(rows, config, country=None, trend_config=None):
    color_map = assign_series_colors([r["Series"].strip() for r in rows])

    points = []
    for r in rows:
        d = parse_date(r["Date"])
        a = parse_approval(r["Approval"])
        points.append({
            "date": d,
            "approval": a,
            "series": r["Series"].strip(),
            "source": (r.get("Source") or "").strip(),
        })

    executive = rows[0]["Prime Minister"].strip()
    party = (rows[0].get("Party") or "").strip()

    dates = [p["date"] for p in points]
    approvals = [p["approval"] for p in points]
    min_date, max_date = min(dates), max(dates)
    y_min = max(0, 5 * ((min(approvals) - 5) // 5))
    y_max = min(100, 5 * ((max(approvals) + 9) // 5))
    if y_max <= y_min:
        y_max = y_min + 10

    width, height = 900, 460
    margin = {"top": 60, "right": 30, "bottom": 60, "left": 50}
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]

    date_span_days = max((max_date - min_date).days, 1)

    def x_of(d):
        return margin["left"] + plot_w * ((d - min_date).days / date_span_days)

    def y_of(v):
        return margin["top"] + plot_h * (1 - (v - y_min) / (y_max - y_min))

    svg_parts = [
        '<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" role="img" '
        'aria-label="Approval over time chart">'.format(w=width, h=height),
        '<rect x="0" y="0" width="{w}" height="{h}" fill="{bg}"/>'.format(w=width, h=height, bg=BACKGROUND_COLOR),
    ]

    # Y gridlines + labels (percentage axis)
    n_y_ticks = 5
    for i in range(n_y_ticks + 1):
        v = y_min + (y_max - y_min) * i / n_y_ticks
        y = y_of(v)
        svg_parts.append(
            '<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{c}" stroke-width="1"/>'.format(
                x1=margin["left"], x2=width - margin["right"], y=round(y, 1), c=GRID_COLOR
            )
        )
        svg_parts.append(
            '<text x="{x}" y="{y}" font-size="11" fill="{c}" text-anchor="end" '
            'dominant-baseline="middle">{v}%</text>'.format(
                x=margin["left"] - 8, y=round(y, 1), c=AXIS_TEXT_COLOR, v=int(round(v))
            )
        )

    # X ticks: up to 8 evenly spaced month-ish labels across the date span
    n_x_ticks = min(8, max(2, date_span_days // 30 + 1))
    for i in range(n_x_ticks + 1):
        frac = i / n_x_ticks
        d = min_date + datetime.timedelta(days=round(date_span_days * frac))
        x = x_of(d)
        svg_parts.append(
            '<line x1="{x}" y1="{y1}" x2="{x}" y2="{y2}" stroke="{c}" stroke-width="1"/>'.format(
                x=round(x, 1), y1=margin["top"], y2=height - margin["bottom"], c=GRID_COLOR
            )
        )
        svg_parts.append(
            '<text x="{x}" y="{y}" font-size="10" fill="{c}" text-anchor="middle">{label}</text>'.format(
                x=round(x, 1), y=height - margin["bottom"] + 18, c=AXIS_TEXT_COLOR,
                label=_svg_escape(d.strftime("%b %Y"))
            )
        )

    # Trend line (only if the method is explicitly configured/enabled).
    # Deliberately thinner/more translucent than the point marks (see
    # TREND_LINE_STROKE_WIDTH/TREND_LINE_OPACITY) so it reads as a
    # secondary, at-a-glance summary - individual polls stay the primary
    # evidence. Broken into separate <path> segments wherever the gap
    # between consecutive trend-supporting dates exceeds max_gap_days:
    # never interpolated across a long silence in the polling data.
    trend_note = "not shown (no trend method configured)"
    trend_points = []
    trend_segments = []
    if trend_config and trend_config.get("enabled"):
        window_days = trend_config.get("window_days", 30)
        min_points = trend_config.get("min_points_required", 1)
        max_gap_days = trend_config.get("max_gap_days", 45)
        trend_points = compute_rolling_trend(
            [(p["date"], p["approval"]) for p in points], window_days, min_points
        )
        if trend_points:
            trend_segments = split_trend_segments(trend_points, max_gap_days)
            for segment in trend_segments:
                if len(segment) < 2:
                    continue  # a lone point can't draw a line - no interpolation
                path_d = "M " + " L ".join(
                    "{:.1f},{:.1f}".format(x_of(d), y_of(v)) for d, v in segment
                )
                svg_parts.append(
                    '<path d="{d}" fill="none" stroke="{c}" stroke-width="{sw}" '
                    'stroke-opacity="{op}"/>'.format(
                        d=path_d, c=TREND_LINE_COLOR, sw=TREND_LINE_STROKE_WIDTH, op=TREND_LINE_OPACITY
                    )
                )
            trend_note = (
                "{window}-day centered pooled rolling average across all Series; "
                "line breaks (not interpolated) wherever the gap between "
                "consecutive trend-supporting dates exceeds {gap} days "
                "(deterministic, no fitted model)"
            ).format(window=window_days, gap=max_gap_days)

    # Points, grouped/colored by Series, never connected within a series
    for p in points:
        cx, cy = x_of(p["date"]), y_of(p["approval"])
        color = color_map[p["series"]]
        tooltip = "{series} | {date} | {approval:.0f}% | {source}".format(
            series=p["series"], date=p["date"].isoformat(), approval=p["approval"], source=p["source"]
        )
        svg_parts.append(
            '<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4.5" fill="{color}" fill-opacity="0.9" '
            'stroke="{bg}" stroke-width="1"><title>{tt}</title></circle>'.format(
                cx=cx, cy=cy, color=color, bg=BACKGROUND_COLOR, tt=_svg_escape(tooltip)
            )
        )

    # Title (in-SVG)
    title_text = "{} — Prime Minister Approval Over Time{}".format(
        executive, " ({})".format(country) if country else ""
    )
    svg_parts.append(
        '<text x="{x}" y="24" font-size="18" font-weight="600" fill="{c}">{t}</text>'.format(
            x=margin["left"], c=AXIS_TEXT_COLOR, t=_svg_escape(title_text)
        )
    )
    # Reader-facing subtitle: just the validated poll count and date
    # range, in plain readable dates - no internal pipeline/status
    # wording (e.g. "APPROVED") belongs on the visible chart.
    subtitle = "{n} polls • {start} – {end}".format(
        n=len(points),
        start=format_date_readable(min_date),
        end=format_date_readable(max_date),
    )
    svg_parts.append(
        '<text x="{x}" y="42" font-size="12" fill="{c}">{t}</text>'.format(
            x=margin["left"], c=AXIS_TEXT_COLOR, t=_svg_escape(subtitle)
        )
    )

    svg_parts.append("</svg>")
    svg = "\n".join(svg_parts)

    legend_items = "".join(
        '<div class="pollitik-legend-item"><span class="swatch" style="background:{c}"></span>{s}</div>'.format(
            c=color, s=_svg_escape(series)
        )
        for series, color in color_map.items()
    )
    trend_drawn = any(len(seg) >= 2 for seg in trend_segments)
    if trend_drawn:
        legend_items += (
            '<div class="pollitik-legend-item">'
            '<span class="swatch-line" style="background:{c};opacity:{op}"></span>Trend ({w}-day rolling avg)</div>'
        ).format(c=TREND_LINE_COLOR, op=TREND_LINE_OPACITY, w=trend_config.get("window_days", 30))

    body = "{svg}\n<div class=\"pollitik-legend\">{legend}</div>".format(svg=svg, legend=legend_items)

    # Visible footer stays short and reader-facing: source organizations
    # (the same Series names shown in the legend, not raw URLs/domains)
    # plus the one caveat a reader needs (REVIEW/REJECTED excluded).
    # Full methodology/provenance (exact trend method, generator credit)
    # lives in <meta> tags instead - see meta_tags below.
    footer_note = (
        "Sources: {series_list}. REVIEW/REJECTED records are excluded from this chart."
    ).format(series_list=_svg_escape(", ".join(color_map.keys())))

    meta_tags = {
        "pollitik-generator": "python/generate_visualization.py",
        "pollitik-trend-method": trend_note,
        "pollitik-records-approved": str(len(points)),
    }

    html_doc = _html_shell(title_text, body, footer_note, meta_tags=meta_tags)
    report = {
        "executive": executive,
        "party": party,
        "series_count": len(color_map),
        "date_range": [min_date.isoformat(), max_date.isoformat()],
        "trend_method": trend_note,
    }
    return html_doc, report


def render_snapshot_comparison(rows, config, country=None, trend_config=None):
    by_series = defaultdict(list)
    for r in rows:
        by_series[r["Series"].strip()].append(r)
    latest = {}
    for series, series_rows in by_series.items():
        latest[series] = max(series_rows, key=lambda r: parse_date(r["Date"]))

    color_map = assign_series_colors(list(latest.keys()))
    width, height = 900, 400
    margin = {"top": 78, "right": 30, "bottom": 90, "left": 50}
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]

    names = sorted(latest.keys())
    values = [parse_approval(latest[n]["Approval"]) for n in names]
    y_max = min(100, 10 * ((max(values) + 9) // 10)) if values else 100
    bar_w = plot_w / max(len(names), 1) * 0.6
    slot_w = plot_w / max(len(names), 1)

    svg_parts = [
        '<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" role="img" '
        'aria-label="Snapshot comparison chart">'.format(w=width, h=height),
        '<rect x="0" y="0" width="{w}" height="{h}" fill="{bg}"/>'.format(w=width, h=height, bg=BACKGROUND_COLOR),
    ]
    for i, name in enumerate(names):
        v = parse_approval(latest[name]["Approval"])
        x = margin["left"] + slot_w * i + (slot_w - bar_w) / 2
        bar_h = plot_h * (v / y_max) if y_max else 0
        y = margin["top"] + plot_h - bar_h
        color = color_map[name]
        obs_date = parse_date(latest[name]["Date"])
        date_label = format_date_readable(obs_date)
        svg_parts.append(
            '<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{c}"><title>{t}</title></rect>'.format(
                x=x, y=y, w=bar_w, h=bar_h, c=color,
                t=_svg_escape("{} | {} | {:.0f}%".format(name, date_label, v))
            )
        )
        # Each pollster's latest value shows its own observation date -
        # different Series can have different "latest" dates, so the
        # value alone would otherwise imply a fair same-day comparison
        # that isn't actually there.
        svg_parts.append(
            '<text x="{x:.1f}" y="{y:.1f}" font-size="10" fill="{c}" text-anchor="middle">{d}</text>'.format(
                x=x + bar_w / 2, y=y - 20, c=AXIS_TEXT_COLOR, d=_svg_escape(date_label)
            )
        )
        svg_parts.append(
            '<text x="{x:.1f}" y="{y:.1f}" font-size="12" fill="{c}" text-anchor="middle">{v:.0f}%</text>'.format(
                x=x + bar_w / 2, y=y - 6, c=AXIS_TEXT_COLOR, v=v
            )
        )
        svg_parts.append(
            '<text x="{x:.1f}" y="{y}" font-size="11" fill="{c}" text-anchor="middle">{name}</text>'.format(
                x=x + bar_w / 2, y=margin["top"] + plot_h + 16, c=AXIS_TEXT_COLOR, name=_svg_escape(name)
            )
        )

    executive = rows[0]["Prime Minister"].strip()
    title_text = "{} — Latest Approval by Polling Series{}".format(
        executive, " ({})".format(country) if country else ""
    )
    svg_parts.append(
        '<text x="{x}" y="24" font-size="18" font-weight="600" fill="{c}">{t}</text>'.format(
            x=margin["left"], c=AXIS_TEXT_COLOR, t=_svg_escape(title_text)
        )
    )
    svg_parts.append(
        '<text x="{x}" y="42" font-size="12" fill="{c}">{t}</text>'.format(
            x=margin["left"], c=AXIS_TEXT_COLOR,
            t=_svg_escape("Each Series' most recent reading - dates differ by pollster, shown above each bar.")
        )
    )
    svg_parts.append("</svg>")
    svg = "\n".join(svg_parts)
    body = svg

    # Visible footer: readable Series names (not raw domains), no
    # generator filename, plain REVIEW/REJECTED phrasing. This is a
    # deliberately student-selected chart (--graph/--select-option), so
    # the footer explains what it shows rather than calling it a
    # fallback. Full provenance stays in <meta> tags below.
    footer_note = (
        "Sources: {series_list}. REVIEW/REJECTED records are excluded from this chart."
    ).format(series_list=_svg_escape(", ".join(names)))

    meta_tags = {
        "pollitik-generator": "python/generate_visualization.py",
        "pollitik-series-compared": str(len(names)),
    }

    html_doc = _html_shell(title_text, body, footer_note, meta_tags=meta_tags)
    report = {"executives": [rows[0]["Prime Minister"].strip()], "series_compared": names}
    return html_doc, report


def render_leader_comparison_grid(rows, config, country=None, trend_config=None):
    by_exec = defaultdict(list)
    for r in rows:
        by_exec[r["Prime Minister"].strip()].append(r)

    panels = []
    color_map = assign_series_colors([r["Series"].strip() for r in rows])
    panel_w, panel_h = 860, 220
    margin = {"top": 36, "right": 20, "bottom": 30, "left": 50}
    plot_w = panel_w - margin["left"] - margin["right"]
    plot_h = panel_h - margin["top"] - margin["bottom"]

    executives = sorted(by_exec.keys())
    for executive in executives:
        exec_rows = by_exec[executive]
        points = [
            (parse_date(r["Date"]), parse_approval(r["Approval"]), r["Series"].strip())
            for r in exec_rows
        ]
        dates = [d for d, _, _ in points]
        approvals = [a for _, a, _ in points]
        min_date, max_date = min(dates), max(dates)
        span = max((max_date - min_date).days, 1)
        y_min = max(0, 5 * ((min(approvals) - 5) // 5))
        y_max = min(100, 5 * ((max(approvals) + 9) // 5))
        if y_max <= y_min:
            y_max = y_min + 10

        def x_of(d, _min=min_date, _span=span):
            return margin["left"] + plot_w * ((d - _min).days / _span)

        def y_of(v, _ymin=y_min, _ymax=y_max):
            return margin["top"] + plot_h * (1 - (v - _ymin) / (_ymax - _ymin))

        parts = [
            '<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" role="img" '
            'aria-label="{ex} approval panel">'.format(w=panel_w, h=panel_h, ex=_svg_escape(executive)),
            '<rect x="0" y="0" width="{w}" height="{h}" fill="{bg}"/>'.format(w=panel_w, h=panel_h, bg=BACKGROUND_COLOR),
            '<text x="{x}" y="18" font-size="14" font-weight="600" fill="{c}">{t}</text>'.format(
                x=margin["left"], c=AXIS_TEXT_COLOR, t=_svg_escape(executive)
            ),
        ]
        for d, a, series in points:
            parts.append(
                '<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="{c}" fill-opacity="0.9" '
                'stroke="{bg}" stroke-width="1"><title>{t}</title></circle>'.format(
                    cx=x_of(d), cy=y_of(a), c=color_map[series], bg=BACKGROUND_COLOR,
                    t=_svg_escape("{} | {} | {:.0f}%".format(series, d.isoformat(), a))
                )
            )
        parts.append("</svg>")
        panels.append("\n".join(parts))

    title_text = "Leader Comparison{}".format(" ({})".format(country) if country else "")
    body = "<h1>{}</h1>\n{}".format(_svg_escape(title_text), "\n".join(panels))
    legend_items = "".join(
        '<div class="pollitik-legend-item"><span class="swatch" style="background:{c}"></span>{s}</div>'.format(
            c=color, s=_svg_escape(series)
        )
        for series, color in color_map.items()
    )
    body += '<div class="pollitik-legend">{}</div>'.format(legend_items)
    footer_note = (
        "{n} executives compared, small multiples. REVIEW/REJECTED records are excluded from this chart."
    ).format(n=len(executives))
    meta_tags = {"pollitik-generator": "python/generate_visualization.py"}
    html_doc = _html_shell(title_text, body, footer_note, meta_tags=meta_tags)
    report = {"executives": executives}
    return html_doc, report


def render_series_spread(rows, config, country=None, trend_config=None):
    """Secondary/diagnostic chart: a strip plot of Approval by Series -
    every APPROVED point plotted (never a connecting line, since this
    chart's job is dispersion/house-effects, not a trend), with a short
    mean tick per series. See docs/visualization_rules.md section 1
    (`series_spread`) for when this is/isn't appropriate."""
    by_series = defaultdict(list)
    for r in rows:
        by_series[r["Series"].strip()].append(parse_approval(r["Approval"]))

    color_map = assign_series_colors(list(by_series.keys()))
    names = sorted(by_series.keys())
    all_values = [v for vals in by_series.values() for v in vals]
    y_min = max(0, 5 * ((min(all_values) - 5) // 5))
    y_max = min(100, 5 * ((max(all_values) + 9) // 5))
    if y_max <= y_min:
        y_max = y_min + 10

    width, height = 900, 440
    # top=92 (vs. the other charts' 60) leaves room for the two always-on
    # explanation lines plus the sparse-series caution line when present -
    # see the subtitle block below.
    margin = {"top": 92, "right": 30, "bottom": 70, "left": 50}
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]
    slot_w = plot_w / max(len(names), 1)

    def y_of(v):
        return margin["top"] + plot_h * (1 - (v - y_min) / (y_max - y_min))

    svg_parts = [
        '<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" role="img" '
        'aria-label="Series spread chart">'.format(w=width, h=height),
        '<rect x="0" y="0" width="{w}" height="{h}" fill="{bg}"/>'.format(w=width, h=height, bg=BACKGROUND_COLOR),
    ]

    n_y_ticks = 5
    for i in range(n_y_ticks + 1):
        v = y_min + (y_max - y_min) * i / n_y_ticks
        y = y_of(v)
        svg_parts.append(
            '<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{c}" stroke-width="1"/>'.format(
                x1=margin["left"], x2=width - margin["right"], y=round(y, 1), c=GRID_COLOR
            )
        )
        svg_parts.append(
            '<text x="{x}" y="{y}" font-size="11" fill="{c}" text-anchor="end" '
            'dominant-baseline="middle">{v}%</text>'.format(
                x=margin["left"] - 8, y=round(y, 1), c=AXIS_TEXT_COLOR, v=int(round(v))
            )
        )

    for i, name in enumerate(names):
        vals = sorted(by_series[name])
        n = len(vals)
        cx_center = margin["left"] + slot_w * i + slot_w / 2
        color = color_map[name]
        max_jitter = min(10.0, slot_w * 0.35)
        for j, v in enumerate(vals):
            offset = 0.0 if n == 1 else (j / (n - 1) - 0.5) * 2 * max_jitter
            cx = cx_center + offset
            cy = y_of(v)
            svg_parts.append(
                '<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="{c}" fill-opacity="0.85" '
                'stroke="{bg}" stroke-width="1"><title>{t}</title></circle>'.format(
                    cx=cx, cy=cy, c=color, bg=BACKGROUND_COLOR,
                    t=_svg_escape("{} | {:.0f}%".format(name, v))
                )
            )
        mean_v = statistics.mean(vals)
        mean_y = y_of(mean_v)
        svg_parts.append(
            '<line x1="{x1:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y:.1f}" stroke="{c}" '
            'stroke-width="2.5"><title>{t}</title></line>'.format(
                x1=cx_center - max_jitter - 6, x2=cx_center + max_jitter + 6, y=mean_y,
                c=AXIS_TEXT_COLOR, t=_svg_escape("{} mean: {:.1f}%".format(name, mean_v))
            )
        )
        svg_parts.append(
            '<text x="{x:.1f}" y="{y}" font-size="11" fill="{c}" text-anchor="middle">{name} (n={n})</text>'.format(
                x=cx_center, y=margin["top"] + plot_h + 20, c=AXIS_TEXT_COLOR,
                name=_svg_escape(name), n=n
            )
        )

    executive = rows[0]["Prime Minister"].strip()
    title_text = "{} — Approval Spread by Polling Series{}".format(
        executive, " ({})".format(country) if country else ""
    )
    svg_parts.append(
        '<text x="{x}" y="24" font-size="18" font-weight="600" fill="{c}">{t}</text>'.format(
            x=margin["left"], c=AXIS_TEXT_COLOR, t=_svg_escape(title_text)
        )
    )
    svg_parts.append(
        '<text x="{x}" y="42" font-size="12" fill="{c}">{t}</text>'.format(
            x=margin["left"], c=AXIS_TEXT_COLOR,
            t=_svg_escape("Compares the observed values reported by each polling Series ({} observations "
                          "across {} Series) — dark tick = each Series' mean.".format(len(rows), len(names)))
        )
    )
    svg_parts.append(
        '<text x="{x}" y="58" font-size="12" fill="{c}">{t}</text>'.format(
            x=margin["left"], c=AXIS_TEXT_COLOR,
            t=_svg_escape("Diagnostic/secondary chart: this alone does not prove a stable pollster house effect.")
        )
    )
    # Reader-facing caution, shown only when it's actually relevant to this
    # data: this chart's per-Series counts can be highly uneven (e.g. a
    # 1-poll firm plotted next to a 16-poll firm), and a 1-2 point series
    # can't show a real distribution or a stable house effect on its own.
    sparse_names = sorted(
        name for name in names if len(by_series[name]) <= SPARSE_SERIES_MAX_OBSERVATIONS
    )
    if sparse_names:
        svg_parts.append(
            '<text x="{x}" y="74" font-size="12" fill="{c}">{t}</text>'.format(
                x=margin["left"], c=AXIS_TEXT_COLOR,
                t=_svg_escape(
                    "Interpret with caution: {} {} very few observations (n <= {}) - too few to show "
                    "a real distribution or a stable pattern.".format(
                        ", ".join(sparse_names),
                        "has" if len(sparse_names) == 1 else "have",
                        SPARSE_SERIES_MAX_OBSERVATIONS,
                    )
                )
            )
        )
    svg_parts.append("</svg>")
    svg = "\n".join(svg_parts)
    body = svg

    # Visible footer: readable Series names (not raw domains), no
    # generator filename, plain REVIEW/REJECTED phrasing. Full
    # provenance/methodology stays in <meta> tags below.
    footer_note = (
        "Sources: {series_list}. REVIEW/REJECTED records are excluded from this chart."
    ).format(series_list=_svg_escape(", ".join(names)))

    meta_tags = {
        "pollitik-generator": "python/generate_visualization.py",
        "pollitik-role": "secondary_diagnostic_only",
        "pollitik-sparse-series": ", ".join(sparse_names) if sparse_names else "none",
    }

    html_doc = _html_shell(title_text, body, footer_note, meta_tags=meta_tags)
    report = {"executive": executive, "series_count": len(names), "sparse_series": sparse_names}
    return html_doc, report


RENDERERS = {
    "approval_over_time": render_approval_over_time,
    "snapshot_comparison": render_snapshot_comparison,
    "leader_comparison_grid": render_leader_comparison_grid,
    "series_spread": render_series_spread,
}


# --------------------------------------------------------------------
# Standalone SVG export (no new dependencies - the fragment already
# exists in memory from rendering) + optional PNG export
# --------------------------------------------------------------------

def extract_svg_fragment(html_doc):
    """The rendered chart's own <svg>...</svg> markup, or None if none
    is found. Note: a small-multiples renderer (leader_comparison_grid)
    concatenates one <svg> per panel into the HTML body: this returns
    only the first panel, same limitation try_write_png() already has
    for PNG export below - full multi-panel export is follow-up work,
    not part of this pass."""
    start = html_doc.find("<svg")
    if start == -1:
        return None
    end = html_doc.find("</svg>", start)
    if end == -1:
        return None
    return html_doc[start:end + len("</svg>")]


def write_svg_sidecar(output_path, html_doc):
    """Writes the chart's own <svg> markup as a standalone, self-
    contained .svg file next to the HTML output (same basename, .svg
    extension) - usable directly as a publication/Substack graphic
    without opening the HTML. The fragment already carries its own
    xmlns and brand styling inline (see render_* functions), so no
    further processing is needed. Returns the written path, or None if
    the HTML had no <svg> element (never happens for a current
    renderer, but this never fails the whole run if it did)."""
    fragment = extract_svg_fragment(html_doc)
    if fragment is None:
        return None
    svg_doc = '<?xml version="1.0" encoding="UTF-8"?>\n' + fragment + "\n"
    svg_path = os.path.splitext(output_path)[0] + ".svg"
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_doc)
    return svg_path


def try_write_png(html_path):
    """Best-effort PNG export next to the HTML output. Only attempted if
    a suitable SVG rasterizer is importable; never fails the run, never
    silently no-ops without saying so."""
    try:
        import cairosvg  # type: ignore
    except ImportError:
        return {"written": False, "reason": "no SVG rasterizer (e.g. cairosvg) installed in this environment"}

    with open(html_path, "r", encoding="utf-8") as f:
        doc = f.read()
    start = doc.find("<svg")
    end = doc.find("</svg>") + len("</svg>")
    if start == -1 or end == -1:
        return {"written": False, "reason": "no <svg> element found in generated HTML"}
    svg_fragment = doc[start:end]
    png_path = os.path.splitext(html_path)[0] + ".png"
    try:
        cairosvg.svg2png(bytestring=svg_fragment.encode("utf-8"), write_to=png_path)
    except Exception as exc:  # pragma: no cover - depends on optional dep
        return {"written": False, "reason": "cairosvg failed: {}".format(exc)}
    return {"written": True, "path": png_path}


# --------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------

def write_recommendation_state(state_path, country, input_path, recommendations):
    """Persist the just-computed ranked recommendation list to a small
    local JSON file so a later, separate invocation ("generate graph
    option 1") can resolve the option number deterministically instead
    of relying on the model recalling its own prior printed output.
    Written atomically (tmp file + os.replace) so a reader never sees a
    torn/partial file. Caller is responsible for keeping this path under
    a gitignored location (e.g. data/processed/recommendation_state/) -
    this function has no opinion on where it lives, matching this
    script's existing rule of never resolving repo/production paths
    implicitly (see module docstring)."""
    state = {
        "country": country,
        "input": os.path.abspath(input_path),
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "recommendations": [
            {"option": i + 1, "graph_type": r["graph_type"], "reason": r["reason"]}
            for i, r in enumerate(recommendations)
        ],
    }
    out_dir = os.path.dirname(os.path.abspath(state_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    tmp_path = state_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, state_path)
    return state


def resolve_option(state_path, option):
    """Deterministic lookup of a student's "generate graph option N" against
    the recommendation state a prior --recommend run wrote with
    write_recommendation_state(). Never guesses from conversation text."""
    if not os.path.isfile(state_path):
        raise VisualizationDataError(
            "No saved recommendation state found at '{}'. Run this script without "
            "--graph/--select-option first to generate and save ranked recommendations, "
            "then select an option.".format(state_path)
        )
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise VisualizationDataError("Could not read recommendation state '{}': {}.".format(state_path, exc))

    recommendations = state.get("recommendations") or []
    if not (1 <= option <= len(recommendations)):
        raise VisualizationDataError(
            "--select-option {} is out of range - the saved recommendation state at '{}' "
            "has {} option(s) (1-{}).".format(option, state_path, len(recommendations), len(recommendations))
        )
    chosen = recommendations[option - 1]
    return chosen["graph_type"], state


def generate_chosen_graph(approved, config, graph_type, output_path, country, excluded, total_rows,
                           selected_by="student", selected_option=None):
    """The student has named exactly one approved graph type - verify it
    actually fits this data (same eligibility check recommend_graphs
    uses), then render it with full Pollitik styling. Raises
    VisualizationDataError (never generates a misleading chart) if the
    choice is unknown or not eligible for this data's shape."""
    if graph_type not in RENDERERS:
        raise VisualizationDataError(
            "'{}' is not an approved graph type. Approved types: {}.".format(
                graph_type, ", ".join(sorted(RENDERERS))
            )
        )
    if not output_path:
        raise VisualizationDataError("--output is required when --graph is supplied.")

    shape = compute_data_shape(approved)
    eligible, reason = graph_eligibility(graph_type, shape, config)
    if not eligible:
        recommendations, _ = recommend_graphs(approved, config)
        rec_list = ", ".join(r["graph_type"] for r in recommendations) or "none eligible"
        raise VisualizationDataError(
            "'{}' is not appropriate for this data: {} Recommended options for this "
            "dataset: {}.".format(graph_type, reason, rec_list)
        )

    trend_config = None
    if graph_type == "approval_over_time":
        trend_config = config["graph_types"]["approval_over_time"]["design"].get("trend_line")

    renderer = RENDERERS[graph_type]
    html_doc, report = renderer(approved, config, country=country, trend_config=trend_config)

    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_doc)

    svg_path = write_svg_sidecar(output_path, html_doc)
    png_result = try_write_png(output_path)

    output_formats = ["HTML"] + (["SVG"] if svg_path else [])
    summary = {
        "graph_type": graph_type,
        "selected_by": selected_by,
        "records_input_total": total_rows,
        "records_approved": len(approved),
        "records_excluded_by_status": excluded,
        "output_html": os.path.abspath(output_path),
        "output_svg": os.path.abspath(svg_path) if svg_path else None,
        "output_formats": output_formats,
        "student_summary": "Your graph was generated as {}.".format(" and ".join(output_formats)),
        "png": png_result,
    }
    if selected_option is not None:
        summary["selected_option"] = selected_option
    summary.update(report)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Rank suitable Pollitik graph types for a country's APPROVED "
            "executive-approval CSV, then generate the one the student picks. "
            "Run with no --graph to see the ranked recommendations; nothing is "
            "generated until you pass --graph <type>."
        )
    )
    parser.add_argument(
        "--resolve-request", default=None, metavar="TEXT",
        help=(
            "Deterministically classify a student's initial free-text graph request "
            "(before any recommendation has been shown) into one of: recommend, "
            "approval_over_time, series_spread, snapshot_comparison, "
            "leader_comparison_grid, all, or unsupported:<key>. Prints that token (plus "
            "a short student-facing reason on a second line for an unsupported:<key> "
            "result) and exits 0 - no --input/--config is read and nothing is "
            "generated. Codex must route every incoming graph request through this "
            "first and only call --recommend / --graph itself based on the result; a "
            "'recommend' result (or an 'unsupported:<key>' result, after relaying its "
            "reason) means show the ranked options and stop."
        )
    )
    parser.add_argument("--input", default=None, help="Path to a Pollitik visualization-ready CSV.")
    parser.add_argument(
        "--output", default=None,
        help="Path to write the HTML visualization to. Required when --graph is supplied; unused otherwise."
    )
    parser.add_argument(
        "--config", default=DEFAULT_CONFIG_PATH,
        help="Path to visualization_rules.yaml (default: repo config/visualization_rules.yaml)."
    )
    parser.add_argument(
        "--country", default=None,
        help="Optional country label for the chart title (the CSV schema itself has no Country column)."
    )
    parser.add_argument(
        "--recommend", action="store_true",
        help="Print the ranked recommendation list. This is also the default behavior when --graph is omitted."
    )
    choice_group = parser.add_mutually_exclusive_group()
    choice_group.add_argument(
        "--graph", default=None, metavar="TYPE",
        help=(
            "The student's chosen graph type (e.g. approval_over_time, series_spread, "
            "snapshot_comparison, leader_comparison_grid). Generates that chart "
            "automatically with full Pollitik styling. Omit to see recommendations instead."
        )
    )
    choice_group.add_argument(
        "--select-option", default=None, type=int, metavar="N",
        help=(
            "Resolve option N (1-based) from the most recently saved recommendation "
            "state (see --state-file) and generate that chart. Deterministic alternative "
            "to --graph for a follow-up 'generate graph option N' request - requires "
            "--state-file to point at the same state file the prior --recommend run wrote."
        )
    )
    choice_group.add_argument(
        "--reply", default=None, metavar="TEXT",
        help=(
            "The student's free-text reply to a saved recommendation list - an option "
            "number, the graph name, an unambiguous natural description, or 'all "
            "<count>'. Resolved deterministically via resolve_student_choice() against "
            "--state-file; never requires the internal graph type id. An unresolved or "
            "ambiguous reply prints a short human-readable clarification and generates "
            "nothing (exit 0)."
        )
    )
    parser.add_argument(
        "--state-file", default=None,
        help=(
            "Path to a local JSON file used to persist/resolve ranked recommendations "
            "across separate invocations. In recommend mode (no --graph/--select-option), "
            "if given, the ranked recommendation list is saved here. With --select-option, "
            "required: the option number is resolved from this file. This script never "
            "picks a default location for it (see module docstring) - the caller decides "
            "where it lives and must keep it out of version control."
        )
    )
    args = parser.parse_args(argv)

    if args.resolve_request is not None:
        result = resolve_request(args.resolve_request)
        print(result)
        if result.startswith("unsupported:"):
            key = result.split(":", 1)[1]
            print(format_unsupported_graph_message(key))
        return 0

    if not args.input:
        parser.error("--input is required unless --resolve-request is supplied.")

    try:
        config = load_config(args.config)
        rows = load_csv_rows(args.input)
        approved, excluded = filter_approved(rows)
        validate_row_fields(approved)

        if args.select_option is not None:
            if not args.state_file:
                raise VisualizationDataError("--state-file is required when --select-option is supplied.")
            graph_type, state = resolve_option(args.state_file, args.select_option)
            summary = generate_chosen_graph(
                approved, config, graph_type, args.output, args.country, excluded, len(rows),
                selected_by="student_option", selected_option=args.select_option,
            )
            summary["resolved_from_state_file"] = os.path.abspath(args.state_file)
            summary["dataset_matches_recommendation_input"] = (
                os.path.abspath(args.input) == state.get("input")
            )
        elif args.graph:
            summary = generate_chosen_graph(
                approved, config, args.graph, args.output, args.country, excluded, len(rows)
            )
        elif args.reply is not None:
            if not args.state_file:
                raise VisualizationDataError("--state-file is required when --reply is supplied.")
            if not os.path.isfile(args.state_file):
                raise VisualizationDataError(
                    "No saved recommendation state found at '{}'. Run this script without "
                    "--graph/--select-option/--reply first to generate and save ranked "
                    "recommendations, then reply with a choice.".format(args.state_file)
                )
            try:
                with open(args.state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                raise VisualizationDataError("Could not read recommendation state '{}': {}.".format(
                    args.state_file, exc
                ))
            saved_recommendations = state.get("recommendations") or []
            resolved_types, clarification = resolve_student_choice(args.reply, saved_recommendations)
            if resolved_types is None:
                print(clarification)
                return 0
            if not args.output:
                raise VisualizationDataError("--output is required when --reply resolves to a graph choice.")
            if len(resolved_types) == 1:
                summary = generate_chosen_graph(
                    approved, config, resolved_types[0], args.output, args.country, excluded, len(rows),
                    selected_by="student_reply",
                )
                summary["resolved_from_state_file"] = os.path.abspath(args.state_file)
            else:
                base, ext = os.path.splitext(args.output)
                ext = ext or ".html"
                graph_summaries = []
                for graph_type in resolved_types:
                    per_output = "{}_{}{}".format(base, graph_type, ext)
                    graph_summaries.append(generate_chosen_graph(
                        approved, config, graph_type, per_output, args.country, excluded, len(rows),
                        selected_by="student_reply_all",
                    ))
                summary = {
                    "graphs": graph_summaries,
                    "resolved_from_state_file": os.path.abspath(args.state_file),
                }
        else:
            # Neither --graph nor --select-option: recommend and stop.
            # This is the ONLY path when neither was passed - the tool
            # never silently picks a chart for the student.
            recommendations, shape = recommend_graphs(approved, config)
            text = format_recommendation_text(recommendations, len(approved), excluded, shape)
            if args.state_file:
                write_recommendation_state(args.state_file, args.country, args.input, recommendations)
                text += "\n\nRecommendation state saved to {} (used to resolve 'generate graph option N').".format(
                    os.path.abspath(args.state_file)
                )
            print(text)
            return 0
    except VisualizationDataError as exc:
        print("generate_visualization.py: ERROR: {}".format(exc), file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
