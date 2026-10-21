"""Tests for python/generate_visualization.py - the Pollitik
recommend-then-choose graph workflow driven by
config/visualization_rules.yaml.

2026-08-21 workflow change: the tool no longer auto-picks a single
chart. With no --graph it ranks up to 3 eligible graph types and stops
(nothing is generated); the student then re-runs with --graph <type> to
generate exactly that chart. See docs/visualization_rules.md.

Real subprocess invocations against isolated tmp_path fixtures, same
pattern as the rest of this suite (see tests/conftest.py): no real
Pollitik data (data/master/, data/staging/) is ever touched by these
tests, and each test supplies its own small config/CSV so it does not
depend on the real repo's config/visualization_rules.yaml staying
byte-for-byte identical over time.
"""

import csv
import datetime
import json
import os
import re
import subprocess
import sys

import yaml

from .conftest import REPO_ROOT

SCRIPT = REPO_ROOT / "python" / "generate_visualization.py"

# tests/conftest.py already puts <repo>/python on sys.path - used below
# for direct, precise unit tests of the pure gap-splitting/rolling-trend
# logic (no subprocess needed for that part).
import generate_visualization as gv  # noqa: E402

CSV_FIELDS = ["Date", "Approval", "Prime Minister", "Party", "Series", "Source", "Status"]

SAMPLE_CONFIG = {
    "graph_types": {
        "approval_over_time": {
            "requires": {"executives": 1, "min_observations": 8, "min_distinct_dates": 2},
            "design": {
                "trend_line": {
                    "enabled": True,
                    "window_days": 30,
                    "min_points_required": 8,
                    "max_gap_days": 45,
                }
            },
        },
        "leader_comparison_grid": {"requires": {"executives_min": 2}},
        "snapshot_comparison": {"requires": {"min_series": 2}},
        "series_spread": {"requires": {"min_series": 2}},
    },
    "recommendation": {
        "priority_order": [
            "leader_comparison_grid",
            "approval_over_time",
            "series_spread",
            "snapshot_comparison",
        ],
        "max_recommendations": 3,
        "reasons": {
            "leader_comparison_grid": "Best for comparing approval trends across multiple leaders side by side.",
            "approval_over_time": "Best for showing how {executive} approval changes over time.",
            "series_spread": "Useful for showing differences across polling firms.",
            "snapshot_comparison": "Useful for comparing pollsters at a selected/latest point, when the data supports a fair comparison.",
        },
    },
    "style": {
        "brand_colors": {
            "amber": "#FFB400",
            "blue": "#00A6ED",
            "orange_red": "#F6511D",
            "off_white": "#FBFBF2",
        }
    },
    "data_quality": {
        "excluded_statuses": ["REVIEW", "REJECTED"],
        "never_invent": ["prime_minister", "party", "date", "value", "source"],
    },
}


def write_config(tmp_path, config=None):
    path = tmp_path / "visualization_rules.yaml"
    path.write_text(yaml.safe_dump(config or SAMPLE_CONFIG), encoding="utf-8")
    return path


def write_csv(tmp_path, rows, name="input.csv", fields=CSV_FIELDS):
    path = tmp_path / name
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def make_row(date, approval, pm="Mark Carney", party="Liberal", series="LEGER",
             source="https://example.test/poll", status="APPROVED"):
    return {
        "Date": date, "Approval": approval, "Prime Minister": pm, "Party": party,
        "Series": series, "Source": source, "Status": status,
    }


def run_cli(tmp_path, args):
    cmd = [sys.executable, str(SCRIPT)] + args
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(tmp_path))


def canada_like_rows(n=29):
    """29 single-executive, 5-series, irregular-date rows - same shape as
    the real data/processed/canada_pm_approval_main.csv, without
    depending on that file's exact contents."""
    series_cycle = ["LEGER", "LIAISON", "RESEARCHCO", "ANGUSREID", "IPSOS"]
    rows = []
    for i in range(n):
        month = 1 + (i * 2) % 12
        day = 1 + (i * 3) % 27
        rows.append(make_row(
            date="{}/{}/2026".format(month, day),
            approval=str(50 + (i % 15)),
            series=series_cycle[i % len(series_cycle)],
        ))
    return rows


# --------------------------------------------------------------------
# 1. Canada-shaped data: 3 ranked recommendations, in the right order,
#    with leader_comparison_grid excluded (single executive).
# --------------------------------------------------------------------

def test_canada_shaped_data_returns_three_ranked_recommendations(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))

    result = run_cli(tmp_path, ["--input", str(csv_path), "--config", str(config)])

    assert result.returncode == 0, result.stderr
    out = result.stdout
    # Ranked, in order, with only the top pick flagged "recommended".
    idx_aot = out.index("1. Approval Over Time - recommended")
    idx_spread = out.index("2. Series Spread")
    idx_snapshot = out.index("3. Snapshot Comparison")
    assert idx_aot < idx_spread < idx_snapshot
    assert "Leader Comparison Grid" not in out
    assert "Best for showing how Mark Carney approval changes over time." in out
    assert "Useful for showing differences across polling firms." in out
    # Student-facing reply instructions - numbers + display names + a
    # natural description + "all three", never an internal graph type id.
    assert "You can reply with 1, 2, 3, the graph name, a natural description, or 'all three'." in out
    assert "approval_over_time" not in out
    assert "series_spread" not in out
    assert "snapshot_comparison" not in out
    assert "--graph" not in out


def test_real_canada_csv_recommendation_matches(tmp_path):
    """Sanity-check against the actual repo-resident Canada dataset, read
    only (never written to)."""
    real_csv = REPO_ROOT / "data" / "processed" / "canada_pm_approval_main.csv"
    real_config = REPO_ROOT / "config" / "visualization_rules.yaml"
    if not real_csv.exists():
        return  # nothing to check yet in a fresh checkout

    result = run_cli(tmp_path, ["--input", str(real_csv), "--config", str(real_config)])

    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "1. Approval Over Time - recommended" in out
    assert "2. Series Spread" in out
    assert "3. Snapshot Comparison" in out
    assert "Leader Comparison Grid" not in out


# --------------------------------------------------------------------
# 2. leader_comparison_grid IS recommended (top) once there are >= 2
#    executives, proving the exclusion above is data-driven, not hardcoded.
# --------------------------------------------------------------------

def test_multiple_executives_recommends_leader_comparison_grid_first(tmp_path):
    rows = canada_like_rows(15)
    rows += [make_row("{}/1/2026".format(m), str(50 + m), pm="Other Leader", series="LEGER")
             for m in range(1, 6)]
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, rows)

    result = run_cli(tmp_path, ["--input", str(csv_path), "--config", str(config)])

    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "1. Leader Comparison Grid - recommended" in out


# --------------------------------------------------------------------
# 3. Student can choose approval_over_time (and it is generated with
#    Pollitik styling, no manual axis/color/legend configuration).
# --------------------------------------------------------------------

def test_student_can_choose_approval_over_time(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    out_path = tmp_path / "out.html"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config),
        "--output", str(out_path), "--graph", "approval_over_time",
    ])

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["graph_type"] == "approval_over_time"
    assert summary["selected_by"] == "student"
    assert summary["records_approved"] == 29
    assert out_path.exists()
    svg_text = out_path.read_text(encoding="utf-8")
    assert "<svg" in svg_text
    assert "#FFB400" in svg_text or "#00A6ED" in svg_text or "#F6511D" in svg_text
    assert 'text-anchor="middle">Trend' not in svg_text or "rolling avg" in svg_text


def test_student_can_choose_series_spread(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    out_path = tmp_path / "out.html"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config),
        "--output", str(out_path), "--graph", "series_spread",
    ])

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["graph_type"] == "series_spread"
    assert out_path.exists()


# --------------------------------------------------------------------
# 4. Invalid/inappropriate graph choice fails clearly (no chart written).
# --------------------------------------------------------------------

def test_unknown_graph_type_fails_clearly(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    out_path = tmp_path / "out.html"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config),
        "--output", str(out_path), "--graph", "bogus_type",
    ])

    assert result.returncode != 0
    assert "ERROR" in result.stderr
    assert "not an approved graph type" in result.stderr
    assert not out_path.exists()


def test_inappropriate_graph_choice_for_data_fails_clearly(tmp_path):
    """Single-executive Canada-shaped data: leader_comparison_grid is not
    eligible and must be refused, not silently generated."""
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    out_path = tmp_path / "out.html"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config),
        "--output", str(out_path), "--graph", "leader_comparison_grid",
    ])

    assert result.returncode != 0
    assert "ERROR" in result.stderr
    assert "not appropriate for this data" in result.stderr
    assert "1 executive" in result.stderr
    assert not out_path.exists()


def test_graph_choice_without_output_fails_clearly(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config), "--graph", "approval_over_time",
    ])

    assert result.returncode != 0
    assert "--output is required" in result.stderr


# --------------------------------------------------------------------
# 5. REVIEW/REJECTED rows do not affect recommendations.
# --------------------------------------------------------------------

def test_review_and_rejected_rows_do_not_affect_recommendations(tmp_path):
    config = write_config(tmp_path)

    baseline_rows = canada_like_rows(29)
    baseline_csv = write_csv(tmp_path, baseline_rows, name="baseline.csv")
    baseline_result = run_cli(tmp_path, ["--input", str(baseline_csv), "--config", str(config)])
    assert baseline_result.returncode == 0, baseline_result.stderr

    polluted_rows = baseline_rows + [
        # A REVIEW/REJECTED-only 6th "series" and a 2nd "executive" that
        # would change the ranking (add leader_comparison_grid, push
        # series_spread eligibility differently) if they leaked in.
        make_row("1/1/2026", "99", pm="Someone Else", series="ROGUE_SERIES", status="REVIEW"),
        make_row("1/2/2026", "1", pm="Someone Else", series="ROGUE_SERIES", status="REJECTED"),
    ]
    polluted_csv = write_csv(tmp_path, polluted_rows, name="polluted.csv")
    polluted_result = run_cli(tmp_path, ["--input", str(polluted_csv), "--config", str(config)])
    assert polluted_result.returncode == 0, polluted_result.stderr

    # The excluded-count line legitimately differs (0 vs 2 REVIEW/REJECTED
    # reported) - what must NOT differ is the ranked recommendation list
    # itself, which is everything from "1. " onward.
    def ranking_section(text):
        return text[text.index("1. "):]

    assert ranking_section(baseline_result.stdout) == ranking_section(polluted_result.stdout)
    assert "29 APPROVED observations; 0 REVIEW/REJECTED excluded" in baseline_result.stdout
    assert "29 APPROVED observations; 2 REVIEW/REJECTED excluded" in polluted_result.stdout
    assert "Someone Else" not in polluted_result.stdout
    assert "Leader Comparison Grid" not in polluted_result.stdout


# --------------------------------------------------------------------
# 6. No graph is generated before the student chooses.
# --------------------------------------------------------------------

def test_no_graph_generated_before_student_chooses(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    out_path = tmp_path / "should_not_exist.html"

    # Neither --graph nor --recommend passed: must still just recommend,
    # never silently pick a chart - even if an --output path is given.
    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config), "--output", str(out_path),
    ])

    assert result.returncode == 0, result.stderr
    assert "Recommended Pollitik visualizations" in result.stdout
    assert not out_path.exists()

    # --recommend explicitly: same guarantee.
    result2 = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config), "--recommend",
    ])
    assert result2.returncode == 0, result2.stderr
    assert not out_path.exists()


# --------------------------------------------------------------------
# 7. Schema/row-level validation still fails clearly (unaffected by the
#    recommend/choose workflow change - runs before either branch).
# --------------------------------------------------------------------

def test_missing_required_column_fails_safely(tmp_path):
    config = write_config(tmp_path)
    fields_without_approval = [c for c in CSV_FIELDS if c != "Approval"]
    csv_path = write_csv(tmp_path, canada_like_rows(9), fields=fields_without_approval)

    result = run_cli(tmp_path, ["--input", str(csv_path), "--config", str(config)])

    assert result.returncode != 0
    assert "Approval" in result.stderr
    assert "ERROR" in result.stderr


def test_missing_required_row_value_fails_safely(tmp_path):
    rows = canada_like_rows(9)
    rows[3]["Date"] = ""  # one APPROVED row silently missing its Date
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, rows)

    result = run_cli(tmp_path, ["--input", str(csv_path), "--config", str(config)])

    assert result.returncode != 0
    assert "Date" in result.stderr
    assert "ERROR" in result.stderr


def test_no_approved_rows_fails_safely(tmp_path):
    rows = [make_row("1/1/2026", "50", status="REVIEW") for _ in range(9)]
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, rows)

    result = run_cli(tmp_path, ["--input", str(csv_path), "--config", str(config)])

    assert result.returncode != 0
    assert "APPROVED" in result.stderr


# --------------------------------------------------------------------
# 8. Output is created without touching production data.
# --------------------------------------------------------------------

def test_output_created_without_touching_production_data(tmp_path):
    master = REPO_ROOT / "data" / "master" / "pollitik_master.xlsx"
    staging = REPO_ROOT / "data" / "staging" / "candidates.jsonl"
    before = {
        p: (os.path.getmtime(p), os.path.getsize(p)) for p in (master, staging) if p.exists()
    }

    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    out_path = tmp_path / "nested" / "canada_pm_approval.html"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config),
        "--output", str(out_path), "--graph", "approval_over_time",
    ])

    assert result.returncode == 0, result.stderr
    assert out_path.exists()

    after = {
        p: (os.path.getmtime(p), os.path.getsize(p)) for p in (master, staging) if p.exists()
    }
    assert before == after, "generate_visualization.py must never touch master/staging files"


# --------------------------------------------------------------------
# 9. approval_over_time trend rendering: the 45-day gap rule.
#
# Direct unit tests of the pure gap-splitting logic (precise, no
# subprocess needed), plus CLI-level tests that the *rendered* chart
# actually has the right number of trend <path> segments and that the
# points themselves are completely unaffected by any of this.
# --------------------------------------------------------------------

def d(s):
    return datetime.date.fromisoformat(s)


def test_split_trend_segments_breaks_when_gap_exceeds_45_days():
    trend_points = [
        (d("2026-01-01"), 50.0),
        (d("2026-01-20"), 52.0),
        (d("2026-03-07"), 60.0),  # 46 days after 2026-01-20 - must break here
        (d("2026-03-25"), 58.0),
    ]
    segments = gv.split_trend_segments(trend_points, max_gap_days=45)
    assert [len(s) for s in segments] == [2, 2]
    assert segments[0] == trend_points[:2]
    assert segments[1] == trend_points[2:]


def test_split_trend_segments_does_not_break_at_exactly_45_days():
    trend_points = [
        (d("2026-01-01"), 50.0),
        (d("2026-01-20"), 52.0),
        (d("2026-03-06"), 60.0),  # exactly 45 days after 2026-01-20 - stays joined
    ]
    segments = gv.split_trend_segments(trend_points, max_gap_days=45)
    assert len(segments) == 1
    assert segments[0] == trend_points


def test_split_trend_segments_multiple_breaks_and_isolated_point():
    trend_points = [
        (d("2026-01-01"), 50.0),
        (d("2026-01-10"), 51.0),
        (d("2026-03-01"), 55.0),   # isolated - big gaps on both sides
        (d("2026-05-01"), 60.0),
        (d("2026-05-05"), 61.0),
    ]
    segments = gv.split_trend_segments(trend_points, max_gap_days=45)
    assert [len(s) for s in segments] == [2, 1, 2]


def test_split_trend_segments_empty_input():
    assert gv.split_trend_segments([], max_gap_days=45) == []


def _svg_path_count(svg_text):
    return len(re.findall(r'<path d="[^"]*" fill="none" stroke="#333333"', svg_text))


def _svg_circle_count(svg_text):
    return len(re.findall(r"<circle ", svg_text))


def _rows_with_gap(before_dates, after_dates):
    rows = []
    for i, date_str in enumerate(before_dates):
        rows.append(make_row(date_str, str(50 + i), series="LEGER"))
    for i, date_str in enumerate(after_dates):
        rows.append(make_row(date_str, str(55 + i), series="LIAISON"))
    return rows


def test_generated_chart_breaks_trend_line_at_46_day_gap(tmp_path):
    rows = _rows_with_gap(
        ["1/1/2026", "1/5/2026", "1/10/2026", "1/15/2026", "1/20/2026"],
        ["3/7/2026", "3/10/2026", "3/15/2026", "3/20/2026", "3/25/2026"],  # 46 days after 1/20
    )
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, rows)
    out_path = tmp_path / "out.html"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config),
        "--output", str(out_path), "--graph", "approval_over_time",
    ])

    assert result.returncode == 0, result.stderr
    svg_text = out_path.read_text(encoding="utf-8")
    assert _svg_path_count(svg_text) == 2
    assert _svg_circle_count(svg_text) == len(rows) == 10


def test_generated_chart_keeps_trend_line_continuous_within_45_days(tmp_path):
    rows = _rows_with_gap(
        ["1/1/2026", "1/5/2026", "1/10/2026", "1/15/2026", "1/20/2026"],
        ["3/6/2026", "3/10/2026", "3/15/2026", "3/20/2026", "3/25/2026"],  # exactly 45 days after 1/20
    )
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, rows)
    out_path = tmp_path / "out.html"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config),
        "--output", str(out_path), "--graph", "approval_over_time",
    ])

    assert result.returncode == 0, result.stderr
    svg_text = out_path.read_text(encoding="utf-8")
    assert _svg_path_count(svg_text) == 1
    assert _svg_circle_count(svg_text) == len(rows) == 10


def test_trend_line_is_visually_less_dominant_than_points(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    out_path = tmp_path / "out.html"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config),
        "--output", str(out_path), "--graph", "approval_over_time",
    ])

    assert result.returncode == 0, result.stderr
    svg_text = out_path.read_text(encoding="utf-8")

    trend_path = re.search(r'<path d="[^"]*" fill="none" stroke="#333333" stroke-width="([\d.]+)" stroke-opacity="([\d.]+)"', svg_text)
    assert trend_path, "expected at least one trend <path> in a 29-point canada-shaped dataset"
    trend_stroke_width = float(trend_path.group(1))
    trend_opacity = float(trend_path.group(2))

    point_stroke_width = float(re.search(r'<circle[^>]*stroke-width="([\d.]+)"', svg_text).group(1))
    point_fill_opacity = float(re.search(r'<circle[^>]*fill-opacity="([\d.]+)"', svg_text).group(1))

    assert trend_stroke_width < 4.5  # thinner than the point radius
    assert trend_opacity < point_fill_opacity  # more translucent than the points


def test_points_unchanged_by_trend_rendering_change(tmp_path):
    """Every APPROVED row still produces exactly one unconnected,
    full-opacity, brand/fallback-colored point - unaffected by the trend
    gap-breaking change."""
    rows = canada_like_rows(29)
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, rows)
    out_path = tmp_path / "out.html"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config),
        "--output", str(out_path), "--graph", "approval_over_time",
    ])

    assert result.returncode == 0, result.stderr
    svg_text = out_path.read_text(encoding="utf-8")
    assert _svg_circle_count(svg_text) == len(rows)
    assert svg_text.count('r="4.5"') == len(rows)
    assert svg_text.count('fill-opacity="0.9"') == len(rows)
    # No line ever directly joins two <circle> points (points stay unconnected;
    # only <path> elements, which are the trend layer, draw connecting lines).
    assert "<polyline" not in svg_text


# --------------------------------------------------------------------
# 10. Reader-facing cleanup: subtitle/footer/meta.
# --------------------------------------------------------------------

def test_subtitle_has_no_internal_pipeline_wording(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    out_path = tmp_path / "out.html"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config),
        "--output", str(out_path), "--graph", "approval_over_time",
    ])

    assert result.returncode == 0, result.stderr
    svg_text = out_path.read_text(encoding="utf-8")
    assert "APPROVED" not in svg_text
    assert "29 polls" in svg_text


# --------------------------------------------------------------------
# 11. Persisted recommendation state + --select-option ("generate graph
#     option N" resolved deterministically, not from conversation memory).
# --------------------------------------------------------------------

def test_recommend_mode_persists_state_when_state_file_given(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    state_path = tmp_path / "state" / "canada.json"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config), "--country", "Canada",
        "--state-file", str(state_path),
    ])

    assert result.returncode == 0, result.stderr
    assert "Recommendation state saved to" in result.stdout
    assert state_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["country"] == "Canada"
    assert [r["option"] for r in state["recommendations"]] == list(range(1, len(state["recommendations"]) + 1))
    assert state["recommendations"][0]["graph_type"] == "approval_over_time"


def test_recommend_mode_without_state_file_writes_nothing(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))

    result = run_cli(tmp_path, ["--input", str(csv_path), "--config", str(config)])

    assert result.returncode == 0, result.stderr
    assert "Recommendation state saved" not in result.stdout
    assert not (tmp_path / "state").exists()


def test_select_option_resolves_and_generates_same_as_named_graph(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    state_path = tmp_path / "state" / "canada.json"
    out_path = tmp_path / "out.html"

    recommend_result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config), "--country", "Canada",
        "--state-file", str(state_path),
    ])
    assert recommend_result.returncode == 0, recommend_result.stderr

    select_result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config), "--country", "Canada",
        "--state-file", str(state_path), "--select-option", "1", "--output", str(out_path),
    ])
    assert select_result.returncode == 0, select_result.stderr
    summary = json.loads(select_result.stdout)
    assert summary["graph_type"] == "approval_over_time"
    assert summary["selected_by"] == "student_option"
    assert summary["selected_option"] == 1
    assert summary["dataset_matches_recommendation_input"] is True
    assert out_path.exists()


def test_select_option_second_choice_resolves_series_spread(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    state_path = tmp_path / "state" / "canada.json"
    out_path = tmp_path / "out.html"

    run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config), "--country", "Canada",
        "--state-file", str(state_path),
    ])
    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config), "--country", "Canada",
        "--state-file", str(state_path), "--select-option", "2", "--output", str(out_path),
    ])
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["graph_type"] == "series_spread"
    assert summary["selected_option"] == 2


def test_select_option_out_of_range_fails_clearly(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    state_path = tmp_path / "state" / "canada.json"
    out_path = tmp_path / "out.html"

    run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config), "--country", "Canada",
        "--state-file", str(state_path),
    ])
    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config), "--country", "Canada",
        "--state-file", str(state_path), "--select-option", "99", "--output", str(out_path),
    ])
    assert result.returncode != 0
    assert "ERROR" in result.stderr
    assert "out of range" in result.stderr
    assert not out_path.exists()


def test_select_option_without_prior_state_fails_clearly(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    state_path = tmp_path / "state" / "never_written.json"
    out_path = tmp_path / "out.html"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config), "--country", "Canada",
        "--state-file", str(state_path), "--select-option", "1", "--output", str(out_path),
    ])
    assert result.returncode != 0
    assert "No saved recommendation state found" in result.stderr


def test_select_option_without_state_file_flag_fails_clearly(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    out_path = tmp_path / "out.html"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config),
        "--select-option", "1", "--output", str(out_path),
    ])
    assert result.returncode != 0
    assert "--state-file is required" in result.stderr


def test_graph_and_select_option_are_mutually_exclusive(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    out_path = tmp_path / "out.html"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config),
        "--graph", "approval_over_time", "--select-option", "1", "--output", str(out_path),
    ])
    assert result.returncode != 0
    assert "not allowed with argument" in result.stderr


# --------------------------------------------------------------------
# 11b. resolve_student_choice() - a student's free-text reply to a
#      ranked recommendation list resolves deterministically to a graph
#      type (or "all <count>" of them), never requiring the internal
#      graph_type id (approval_over_time/series_spread/
#      snapshot_comparison) the student was never shown. Covers the
#      2026-08-23 Codex acceptance-test cleanup (issue 2).
# --------------------------------------------------------------------

CANADA_RECOMMENDATIONS = [
    {"option": 1, "graph_type": "approval_over_time", "reason": "Best for showing how Mark Carney approval changes over time."},
    {"option": 2, "graph_type": "series_spread", "reason": "Useful for showing differences across polling firms."},
    {"option": 3, "graph_type": "snapshot_comparison", "reason": "Useful for comparing pollsters at a selected/latest point, when the data supports a fair comparison."},
]


def test_resolve_student_choice_option_number_resolves_to_approval_over_time():
    resolved, clarification = gv.resolve_student_choice("1", CANADA_RECOMMENDATIONS)
    assert resolved == ["approval_over_time"]
    assert clarification is None


def test_resolve_student_choice_option_number_with_whitespace_and_prefix():
    assert gv.resolve_student_choice(" 2 ", CANADA_RECOMMENDATIONS) == (["series_spread"], None)
    assert gv.resolve_student_choice("option 3", CANADA_RECOMMENDATIONS) == (["snapshot_comparison"], None)


def test_resolve_student_choice_human_readable_names_resolve():
    assert gv.resolve_student_choice("Approval Over Time", CANADA_RECOMMENDATIONS) == (["approval_over_time"], None)
    assert gv.resolve_student_choice("series spread", CANADA_RECOMMENDATIONS) == (["series_spread"], None)
    assert gv.resolve_student_choice("Snapshot Comparison", CANADA_RECOMMENDATIONS) == (["snapshot_comparison"], None)


def test_resolve_student_choice_natural_descriptions_resolve_where_unambiguous():
    assert gv.resolve_student_choice("make the trend graph", CANADA_RECOMMENDATIONS) == (["approval_over_time"], None)
    assert gv.resolve_student_choice("make the pollster comparison", CANADA_RECOMMENDATIONS) == (["snapshot_comparison"], None)
    assert gv.resolve_student_choice("latest pollster comparison", CANADA_RECOMMENDATIONS) == (["snapshot_comparison"], None)


def test_resolve_student_choice_all_three_resolves_to_all_eligible_graphs():
    resolved, clarification = gv.resolve_student_choice("all three", CANADA_RECOMMENDATIONS)
    assert resolved == ["approval_over_time", "series_spread", "snapshot_comparison"]
    assert clarification is None


def test_resolve_student_choice_ambiguous_reply_asks_clarification_without_internal_ids():
    resolved, clarification = gv.resolve_student_choice("graph", CANADA_RECOMMENDATIONS)
    assert resolved is None
    assert clarification is not None
    assert "Approval Over Time" in clarification
    assert "approval_over_time" not in clarification
    assert "series_spread" not in clarification
    assert "snapshot_comparison" not in clarification


def test_resolve_student_choice_out_of_range_option_asks_clarification():
    resolved, clarification = gv.resolve_student_choice("9", CANADA_RECOMMENDATIONS)
    assert resolved is None
    assert clarification is not None


def test_format_recommendation_text_uses_numbered_human_readable_names_not_ids():
    text = gv.format_recommendation_text(CANADA_RECOMMENDATIONS, 29, {"REVIEW": 0, "REJECTED": 0}, {
        "executives": ["Mark Carney"], "dates": {"2026-01-01", "2026-02-01"}, "series": ["A", "B"], "n": 29,
    })
    assert "1. Approval Over Time - recommended" in text
    assert "2. Series Spread" in text
    assert "3. Snapshot Comparison" in text
    assert "You can reply with 1, 2, 3, the graph name, a natural description, or 'all three'." in text
    assert "approval_over_time" not in text
    assert "series_spread" not in text
    assert "snapshot_comparison" not in text


def test_reply_flag_resolves_option_number_and_generates_same_as_named_graph(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    state_path = tmp_path / "state" / "canada.json"
    out_path = tmp_path / "out.html"

    recommend_result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config), "--country", "Canada",
        "--state-file", str(state_path),
    ])
    assert recommend_result.returncode == 0, recommend_result.stderr

    reply_result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config), "--country", "Canada",
        "--state-file", str(state_path), "--reply", "make the trend graph", "--output", str(out_path),
    ])
    assert reply_result.returncode == 0, reply_result.stderr
    summary = json.loads(reply_result.stdout)
    assert summary["graph_type"] == "approval_over_time"
    assert summary["selected_by"] == "student_reply"
    assert out_path.exists()


def test_reply_flag_all_three_generates_all_eligible_graphs(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    state_path = tmp_path / "state" / "canada.json"
    out_path = tmp_path / "out.html"

    run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config), "--country", "Canada",
        "--state-file", str(state_path),
    ])
    reply_result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config), "--country", "Canada",
        "--state-file", str(state_path), "--reply", "all three", "--output", str(out_path),
    ])
    assert reply_result.returncode == 0, reply_result.stderr
    summary = json.loads(reply_result.stdout)
    assert {g["graph_type"] for g in summary["graphs"]} == {
        "approval_over_time", "series_spread", "snapshot_comparison"
    }
    assert (tmp_path / "out_approval_over_time.html").exists()
    assert (tmp_path / "out_series_spread.html").exists()
    assert (tmp_path / "out_snapshot_comparison.html").exists()


def test_reply_flag_ambiguous_reply_prints_clarification_and_generates_nothing(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    state_path = tmp_path / "state" / "canada.json"
    out_path = tmp_path / "out.html"

    run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config), "--country", "Canada",
        "--state-file", str(state_path),
    ])
    reply_result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config), "--country", "Canada",
        "--state-file", str(state_path), "--reply", "graph", "--output", str(out_path),
    ])
    assert reply_result.returncode == 0, reply_result.stderr
    assert "I can create:" in reply_result.stdout
    assert "approval_over_time" not in reply_result.stdout
    assert not out_path.exists()


# --------------------------------------------------------------------
# 11c. resolve_request() - deterministic routing of a student's very
#      first free-text graph request (before any recommendation has
#      been shown / before any --state-file exists). Covers the
#      2026-08-23 Codex acceptance-test bug: a vague request must always
#      resolve to "recommend" and never silently pick a chart just
#      because Approval Over Time ranks first.
# --------------------------------------------------------------------

def test_resolve_request_vague_generate_graph_of_results_recommends():
    assert gv.resolve_request("Generate a graph of the Canada results.") == "recommend"


def test_resolve_request_vague_make_a_graph_for_assignment_recommends():
    assert gv.resolve_request("Make a graph for this assignment.") == "recommend"


def test_resolve_request_vague_show_me_a_visualization_recommends():
    assert gv.resolve_request("Show me a visualization.") == "recommend"


def test_resolve_request_specific_approval_over_time_phrase():
    assert gv.resolve_request("Generate a graph showing approval over time.") == "approval_over_time"


def test_resolve_request_specific_trend_graph_phrase():
    assert gv.resolve_request("Make the trend graph.") == "approval_over_time"


def test_resolve_request_specific_series_spread_phrase():
    assert gv.resolve_request("Show the polling-firm spread.") == "series_spread"


def test_resolve_request_specific_snapshot_comparison_phrase():
    assert gv.resolve_request("Compare the latest pollster readings.") == "snapshot_comparison"


def test_resolve_request_explicit_all_graphs():
    assert gv.resolve_request("Generate all graphs.") == "all"


def test_resolve_request_explicit_all_three():
    assert gv.resolve_request("Make all three.") == "all"


def test_resolve_request_empty_text_recommends():
    assert gv.resolve_request("") == "recommend"
    assert gv.resolve_request(None) == "recommend"


def test_resolve_request_cli_prints_token_and_requires_no_input(tmp_path):
    """--resolve-request is a standalone fast path - no --input/--config
    needed, nothing generated, exit 0."""
    result = run_cli(tmp_path, ["--resolve-request", "Generate a graph of the Canada results."])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "recommend"


def test_resolve_request_cli_specific_type(tmp_path):
    result = run_cli(tmp_path, ["--resolve-request", "Make the trend graph."])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "approval_over_time"


def test_no_graph_file_created_for_vague_request_end_to_end(tmp_path):
    """A vague initial request must resolve to 'recommend' and, when that
    result is what Codex then runs, no graph file is ever created."""
    resolved = run_cli(tmp_path, ["--resolve-request", "Generate a graph of the Canada results."])
    assert resolved.returncode == 0, resolved.stderr
    assert resolved.stdout.strip() == "recommend"

    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    out_path = tmp_path / "should_not_exist.html"

    # Codex, having resolved "recommend", runs recommend mode - never
    # --graph - so no --output is even passed here in practice; confirm
    # recommend mode itself never writes a file even if one were given.
    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config), "--output", str(out_path),
    ])
    assert result.returncode == 0, result.stderr
    assert "Recommended Pollitik visualizations" in result.stdout
    assert not out_path.exists()


def test_footer_uses_series_names_not_raw_urls_and_drops_generator_credit(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    out_path = tmp_path / "out.html"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config),
        "--output", str(out_path), "--graph", "approval_over_time",
    ])

    assert result.returncode == 0, result.stderr
    html_text = out_path.read_text(encoding="utf-8")
    footer = re.search(r'<div class="pollitik-footer">(.*?)</div>', html_text, re.S).group(1)

    assert "http://" not in footer and "https://" not in footer
    assert "Generated by" not in footer
    assert "LEGER" in footer or "LIAISON" in footer  # Series names, not domains

    # Methodology/provenance moved to <meta>, not the visible footer.
    assert "Generated by" not in html_text.split("<body>")[1]
    assert '<meta name="pollitik-generator" content="python/generate_visualization.py">' in html_text
    assert '<meta name="pollitik-trend-method"' in html_text


# --------------------------------------------------------------------
# 12. Series Spread: sparse-series caution note (n <= 4), data-driven -
#     present only when a Series actually has few observations.
# --------------------------------------------------------------------

def _rows_with_series_counts(counts, pm="Mark Carney"):
    """counts: {series_name: n}. Builds n distinct-date rows per series so
    each observation is its own row (series_spread doesn't require
    distinct dates, but distinct rows keep this realistic)."""
    rows = []
    day = 1
    for series, n in counts.items():
        for i in range(n):
            month = 1 + (day % 12)
            d = 1 + (day % 27)
            rows.append(make_row("{}/{}/2026".format(month, d), str(50 + i), pm=pm, series=series))
            day += 1
    return rows


def test_series_spread_sparse_caution_appears_when_series_has_few_observations(tmp_path):
    config = write_config(tmp_path)
    rows = _rows_with_series_counts({
        "ANGUSREID": 2, "IPSOS": 1, "LEGER": 6, "LIAISON": 16, "RESEARCHCO": 4,
    })
    csv_path = write_csv(tmp_path, rows)
    out_path = tmp_path / "out.html"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config),
        "--output", str(out_path), "--graph", "series_spread",
    ])

    assert result.returncode == 0, result.stderr
    html_text = out_path.read_text(encoding="utf-8")
    assert "Interpret with caution" in html_text
    assert "ANGUSREID" in html_text and "IPSOS" in html_text and "RESEARCHCO" in html_text
    # LEGER (n=6) and LIAISON (n=16) are not sparse and must not be
    # listed in the caution sentence specifically.
    caution_line = re.search(r"Interpret with caution:[^<]*", html_text).group(0)
    assert "LEGER" not in caution_line
    assert "LIAISON" not in caution_line
    summary = json.loads(result.stdout)
    assert sorted(summary["sparse_series"]) == ["ANGUSREID", "IPSOS", "RESEARCHCO"]


def test_series_spread_no_sparse_caution_when_all_series_well_observed(tmp_path):
    config = write_config(tmp_path)
    rows = _rows_with_series_counts({"LEGER": 6, "LIAISON": 16, "RESEARCHCO": 5})
    csv_path = write_csv(tmp_path, rows)
    out_path = tmp_path / "out.html"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config),
        "--output", str(out_path), "--graph", "series_spread",
    ])

    assert result.returncode == 0, result.stderr
    html_text = out_path.read_text(encoding="utf-8")
    assert "Interpret with caution" not in html_text
    summary = json.loads(result.stdout)
    assert summary["sparse_series"] == []


def test_series_spread_explanation_wording_present(tmp_path):
    """Grounding text for the 'explain this graph' workflow: comparison
    framing, diagnostic/secondary role, and the house-effect caveat."""
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    out_path = tmp_path / "out.html"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config),
        "--output", str(out_path), "--graph", "series_spread",
    ])

    assert result.returncode == 0, result.stderr
    html_text = out_path.read_text(encoding="utf-8")
    assert "Compares the observed values reported by each polling Series" in html_text
    assert "Diagnostic/secondary" in html_text
    assert "does not prove a stable pollster house effect" in html_text


# --------------------------------------------------------------------
# 13. Snapshot Comparison: each Series' latest value shows its own
#     observation date, and no longer claims to be a "Fallback chart".
# --------------------------------------------------------------------

def test_snapshot_comparison_shows_each_series_latest_observation_date(tmp_path):
    config = write_config(tmp_path)
    rows = [
        make_row("8/7/2026", "59", series="RESEARCHCO"),
        make_row("2/26/2026", "58", series="ANGUSREID"),
        make_row("8/8/2026", "57", series="LIAISON"),
    ]
    csv_path = write_csv(tmp_path, rows)
    out_path = tmp_path / "out.html"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config),
        "--output", str(out_path), "--graph", "snapshot_comparison",
    ])

    assert result.returncode == 0, result.stderr
    html_text = out_path.read_text(encoding="utf-8")
    # Actual dates from the data, dynamically formatted - not hardcoded.
    assert "Aug 7, 2026" in html_text
    assert "Feb 26, 2026" in html_text
    assert "Aug 8, 2026" in html_text
    assert "59%" in html_text and "58%" in html_text and "57%" in html_text


def test_snapshot_comparison_does_not_say_fallback_chart(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    out_path = tmp_path / "out.html"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config),
        "--output", str(out_path), "--graph", "snapshot_comparison",
    ])

    assert result.returncode == 0, result.stderr
    html_text = out_path.read_text(encoding="utf-8")
    assert "Fallback" not in html_text
    assert "fallback" not in html_text.lower()


# --------------------------------------------------------------------
# 14. Footer consistency: Series Spread and Snapshot Comparison must not
#     expose raw domains or the generator filename in the visible footer
#     (same rule already enforced for Approval Over Time above).
# --------------------------------------------------------------------

def test_series_spread_and_snapshot_footers_have_no_generator_or_domains(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))

    for graph_type in ("series_spread", "snapshot_comparison"):
        out_path = tmp_path / "out_{}.html".format(graph_type)
        result = run_cli(tmp_path, [
            "--input", str(csv_path), "--config", str(config),
            "--output", str(out_path), "--graph", graph_type,
        ])
        assert result.returncode == 0, result.stderr
        html_text = out_path.read_text(encoding="utf-8")
        footer = re.search(r'<div class="pollitik-footer">(.*?)</div>', html_text, re.S).group(1)

        assert "http://" not in footer and "https://" not in footer
        assert "example.test" not in footer
        assert "Generated by" not in footer
        assert "LEGER" in footer or "LIAISON" in footer  # Series names, not domains

        # Generator credit still recorded, just moved to <meta>.
        assert '<meta name="pollitik-generator" content="python/generate_visualization.py">' in html_text


# --------------------------------------------------------------------
# 15. 2026-08-25 routing fix: resolve_request() disambiguates "compare"
#     by subject (leaders vs. pollsters) instead of routing every
#     "compare"/"comparison" phrase to snapshot_comparison.
#     resolve_student_choice() (replies to an already-shown list) is
#     deliberately untouched - these tests only cover the initial
#     free-text classifier.
# --------------------------------------------------------------------

def test_resolve_request_compare_these_leaders_is_not_pollster_comparison():
    result = gv.resolve_request("Compare these leaders.")
    assert result == "leader_comparison_grid"
    assert result != "snapshot_comparison"
    assert result != "series_spread"


def test_resolve_request_compare_leaders_over_time_is_leader_family():
    assert gv.resolve_request("Compare leaders over time.") == "leader_comparison_grid"


def test_resolve_request_compare_polling_firms_resolves_to_series_spread():
    assert gv.resolve_request("Compare polling firms.") == "series_spread"


def test_resolve_request_compare_latest_polling_firm_readings_resolves_to_snapshot():
    assert gv.resolve_request("Compare the latest polling-firm readings.") == "snapshot_comparison"


def test_resolve_request_show_approval_over_time_still_resolves_correctly():
    assert gv.resolve_request("Show approval over time.") == "approval_over_time"


def test_resolve_request_vague_results_request_still_recommends():
    assert gv.resolve_request("Generate a graph of my results.") == "recommend"


def test_resolve_request_cli_leader_vs_pollster_end_to_end(tmp_path):
    leaders_result = run_cli(tmp_path, ["--resolve-request", "Compare these leaders."])
    assert leaders_result.returncode == 0, leaders_result.stderr
    assert leaders_result.stdout.strip() == "leader_comparison_grid"

    pollsters_result = run_cli(tmp_path, ["--resolve-request", "Compare polling firms."])
    assert pollsters_result.returncode == 0, pollsters_result.stderr
    assert pollsters_result.stdout.strip() == "series_spread"


def test_leader_comparison_grid_request_not_eligible_explains_and_lists_alternatives(tmp_path):
    """'Compare these leaders' resolves to leader_comparison_grid, but a
    single-executive (Canada-shaped) dataset isn't eligible for it - the
    existing eligibility system must explain why and name what IS
    eligible, never silently generate a misleading chart."""
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    out_path = tmp_path / "out.html"

    resolved = run_cli(tmp_path, ["--resolve-request", "Compare these leaders."])
    assert resolved.stdout.strip() == "leader_comparison_grid"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config),
        "--output", str(out_path), "--graph", resolved.stdout.strip(),
    ])
    assert result.returncode != 0
    assert "not appropriate for this data" in result.stderr
    assert "1 executive" in result.stderr
    assert "approval_over_time" in result.stderr  # named as a recommended alternative
    assert not out_path.exists()


# --------------------------------------------------------------------
# 16. Unsupported graph forms (pie chart / donut chart / word cloud):
#     refused with a short, data-grounded reason, never generated, and
#     the student is still pointed at eligible recommendations.
# --------------------------------------------------------------------

def test_resolve_request_pie_chart_is_unsupported():
    assert gv.resolve_request("Make a pie chart.") == "unsupported:pie_chart"


def test_resolve_request_donut_chart_is_unsupported():
    assert gv.resolve_request("Make a donut chart.") == "unsupported:donut_chart"


def test_resolve_request_word_cloud_is_unsupported():
    assert gv.resolve_request("Make a word cloud.") == "unsupported:word_cloud"


def test_unsupported_graph_form_is_never_an_approved_renderer_type():
    assert "pie_chart" not in gv.RENDERERS
    assert "donut_chart" not in gv.RENDERERS
    assert "word_cloud" not in gv.RENDERERS


def test_pie_chart_graph_type_fails_clearly_if_ever_passed_directly(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    out_path = tmp_path / "out.html"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config),
        "--output", str(out_path), "--graph", "pie_chart",
    ])
    assert result.returncode != 0
    assert "not an approved graph type" in result.stderr
    assert not out_path.exists()


def test_resolve_request_cli_pie_chart_prints_reason_and_no_input_needed(tmp_path):
    result = run_cli(tmp_path, ["--resolve-request", "Make a pie chart."])
    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip("\n").splitlines()
    assert lines[0] == "unsupported:pie_chart"
    assert "not appropriate for these approval observations" in result.stdout
    assert "parts of one total" in result.stdout
    assert "pie chart" in result.stdout.lower()


def test_unsupported_request_still_leads_to_eligible_recommendations(tmp_path):
    """End-to-end: Codex resolves 'Make a pie chart.', relays the short
    explanation, then (a separate invocation, same as every other
    resolve_request() outcome) runs recommend mode - which must still
    show the student's real eligible options, and must not generate a
    graph file."""
    resolved = run_cli(tmp_path, ["--resolve-request", "Make a pie chart."])
    assert resolved.returncode == 0, resolved.stderr
    assert resolved.stdout.strip().startswith("unsupported:pie_chart")

    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    out_path = tmp_path / "should_not_exist.html"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config), "--output", str(out_path),
    ])
    assert result.returncode == 0, result.stderr
    assert "Recommended Pollitik visualizations" in result.stdout
    assert "1. Approval Over Time - recommended" in result.stdout
    assert not out_path.exists()


# --------------------------------------------------------------------
# 17. Standalone SVG sidecar output: every successful render writes both
#     .html and .svg, and the summary reports both formats without
#     leaking internal implementation details.
# --------------------------------------------------------------------

def test_successful_graph_writes_both_html_and_svg(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    out_path = tmp_path / "out.html"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config),
        "--output", str(out_path), "--graph", "approval_over_time",
    ])

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    svg_path = tmp_path / "out.svg"
    assert out_path.exists()
    assert svg_path.exists()
    assert summary["output_svg"] == str(svg_path.resolve())
    assert summary["output_formats"] == ["HTML", "SVG"]
    assert summary["student_summary"] == "Your graph was generated as HTML and SVG."

    svg_text = svg_path.read_text(encoding="utf-8")
    assert svg_text.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<svg" in svg_text and "</svg>" in svg_text
    assert 'xmlns="http://www.w3.org/2000/svg"' in svg_text
    # The standalone SVG is self-contained and publication-facing, same
    # rules as the HTML: no internal pipeline wording, no bare filename.
    assert "APPROVED" not in svg_text
    assert "generate_visualization.py" not in svg_text


def test_svg_sidecar_written_for_every_graph_type(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))

    for graph_type in ("approval_over_time", "series_spread", "snapshot_comparison"):
        out_path = tmp_path / "out_{}.html".format(graph_type)
        result = run_cli(tmp_path, [
            "--input", str(csv_path), "--config", str(config),
            "--output", str(out_path), "--graph", graph_type,
        ])
        assert result.returncode == 0, result.stderr
        svg_path = tmp_path / "out_{}.svg".format(graph_type)
        assert svg_path.exists(), "expected {} to produce a standalone SVG".format(graph_type)


def test_reply_all_generates_html_and_svg_for_each_graph(tmp_path):
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, canada_like_rows(29))
    state_path = tmp_path / "state" / "canada.json"
    out_path = tmp_path / "out.html"

    run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config), "--country", "Canada",
        "--state-file", str(state_path),
    ])
    reply_result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config), "--country", "Canada",
        "--state-file", str(state_path), "--reply", "all three", "--output", str(out_path),
    ])
    assert reply_result.returncode == 0, reply_result.stderr
    for graph_type in ("approval_over_time", "series_spread", "snapshot_comparison"):
        assert (tmp_path / "out_{}.html".format(graph_type)).exists()
        assert (tmp_path / "out_{}.svg".format(graph_type)).exists()


def test_extract_svg_fragment_returns_none_when_no_svg_present():
    assert gv.extract_svg_fragment("<html><body>no chart here</body></html>") is None


# --------------------------------------------------------------------
# 18. Regression: existing Canada Approval Over Time trend behavior is
#     completely unaffected by the routing/SVG changes above (same
#     assertions as section 9's gap-breaking tests, run again against
#     the current module to confirm no drift).
# --------------------------------------------------------------------

def test_approval_over_time_trend_calculation_unchanged_after_routing_and_svg_changes(tmp_path):
    rows = _rows_with_gap(
        ["1/1/2026", "1/5/2026", "1/10/2026", "1/15/2026", "1/20/2026"],
        ["3/7/2026", "3/10/2026", "3/15/2026", "3/20/2026", "3/25/2026"],  # 46 days after 1/20
    )
    config = write_config(tmp_path)
    csv_path = write_csv(tmp_path, rows)
    out_path = tmp_path / "out.html"

    result = run_cli(tmp_path, [
        "--input", str(csv_path), "--config", str(config),
        "--output", str(out_path), "--graph", "approval_over_time",
    ])

    assert result.returncode == 0, result.stderr
    svg_text = out_path.read_text(encoding="utf-8")
    assert _svg_path_count(svg_text) == 2  # still breaks into 2 trend segments at the 46-day gap
    assert _svg_circle_count(svg_text) == len(rows) == 10

    # Same chart also produced a standalone SVG with the identical trend markup.
    sidecar = tmp_path / "out.svg"
    assert sidecar.exists()
    assert _svg_path_count(sidecar.read_text(encoding="utf-8")) == 2
